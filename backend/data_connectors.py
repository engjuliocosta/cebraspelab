"""
Infraestrutura de Conectores de Dados (File System Local, Pastas de Rede, Google Drive, Dropbox e Nuvem)
e Ingestão Multi-Formato (`PDF`, `JSON`, `CSV`, `XML`, `TXT`, `MD`) com Rastreamento, Relacionamento
Conceitual e Geração Automática de Questões Cebraspe (`data_connectors.py`).

Funcionalidades:
1. Cadastro e gerenciamento de conexões (`storage_connections`) para:
   - File System Local (`local_fs`): ex. `Downloads`, `Documents`, `Desktop` ou qualquer caminho local.
   - Pastas de Rede (`network_share`): caminhos UNC (`\\\\servidor\\compartilhamento`) ou drives mapeados.
   - Google Drive (`google_drive`): cadastro de `api_key`, `access_token`, `folder_id` e espelho local opcional.
   - Dropbox (`dropbox`): cadastro de `access_token`, `app_key`, `folder_path` e espelho local opcional.
   - Nuvem Customizada (`cloud_custom`): S3 / WebDAV / OneDrive via endpoint + token.
2. Varredura e descoberta de arquivos de estudo suportados (`.pdf`, `.json`, `.csv`, `.xml`, `.txt`, `.md`),
   calculando hash `SHA-256` e rastreando cada arquivo em SQL (`discovered_study_files`) e NoSQL (`discovered_files_catalog`).
3. Parseamento inteligente multi-formato (`PDF`, `JSON`, `CSV`, `XML`, `TXT`, `MD`) extraindo:
   - Páginas/blocos de texto para estudo;
   - Tópicos, subtópicos e períodos sintáticos;
   - Questões preexistentes (quando presentes em JSON, CSV, XML ou PDF);
   - Relacionamentos na árvore `Tópico -> Subtópico -> Conceito -> Subconceito`.
4. Ingestão automática ou sob demanda que salva o arquivo no Vault híbrido, cria o material de estudo,
   registra os relacionamentos conceituais e gera imediatamente uma Bateria de Questões Cebraspe (Certo/Errado)
   pronta para ser apresentada ao aluno.
"""

import csv
import hashlib
import io
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import database
import spaced_review
from gemini_service import analyze_pdf_recurrence, generate_cebraspe_assertions
from pdf_processor import extract_pdf_pages, extract_questions_heuristic
from storage_manager import (
    NoSQLDocumentStore,
    save_material_knowledge_tree_nosql,
    store_uploaded_file,
)
from topic_parser import (
    extract_assertions_from_subtopics,
    parse_pdf_topics_and_subtopics,
    split_into_periods,
)

SUPPORTED_STUDY_EXTENSIONS = {".pdf", ".json", ".csv", ".xml", ".txt", ".md"}

# Limite de tamanho por arquivo (evita carregar vídeos/ISOs renomeados ou PDFs gigantes na memória)
MAX_STUDY_FILE_SIZE_BYTES = 60 * 1024 * 1024  # 60 MB

# Diretórios ignorados durante a varredura recursiva (dependências, caches e pastas de sistema)
IGNORED_DIR_NAMES = {
    "node_modules", ".git", ".venv", "venv", "__pycache__", "$recycle.bin",
    "appdata", ".cache", "dist", "build", "pdf_vault",
}

PROVIDER_TYPES = {
    "local_fs": {
        "id": "local_fs",
        "name": "File System Local (Downloads, Documentos, Pastas Locais)",
        "requires_credentials": False,
        "description": "Busca arquivos PDF, JSON, CSV, XML, TXT e MD diretamente em pastas locais do computador.",
    },
    "network_share": {
        "id": "network_share",
        "name": "Pasta de Rede (SMB / UNC / Drive Mapeado)",
        "requires_credentials": False,
        "description": "Conecta a diretórios compartilhados em rede local (ex: \\\\servidor\\estudos ou Z:\\Concursos).",
    },
    "google_drive": {
        "id": "google_drive",
        "name": "Google Drive (API v3 / Cloud Sync)",
        "requires_credentials": True,
        "description": "Conecta ao Google Drive via API Key / OAuth Access Token e Folder ID para buscar e baixar materiais.",
    },
    "dropbox": {
        "id": "dropbox",
        "name": "Dropbox (API v2 / Cloud Sync)",
        "requires_credentials": True,
        "description": "Conecta ao Dropbox via Access Token / App Key para listar e importar materiais de estudo da nuvem.",
    },
    "cloud_custom": {
        "id": "cloud_custom",
        "name": "Nuvem Customizada (OneDrive / S3 / WebDAV / REST)",
        "requires_credentials": True,
        "description": "Conecta a endpoints de nuvem compatíveis via URL e Chave de API / Bearer Token.",
    },
}


def init_connectors_tables() -> None:
    """Inicializa as tabelas SQL para conexões de armazenamento e rastreamento de arquivos descobertos."""
    conn = database.get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS storage_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            provider_type TEXT NOT NULL,
            target_path_or_folder_id TEXT NOT NULL,
            subject_hint TEXT NOT NULL DEFAULT 'Multidisciplinar',
            area_hint TEXT NOT NULL DEFAULT 'Geral',
            api_key TEXT NOT NULL DEFAULT '',
            access_token TEXT NOT NULL DEFAULT '',
            app_key TEXT NOT NULL DEFAULT '',
            app_secret TEXT NOT NULL DEFAULT '',
            endpoint_url TEXT NOT NULL DEFAULT '',
            local_sync_mirror_path TEXT NOT NULL DEFAULT '',
            recursive_scan INTEGER NOT NULL DEFAULT 1,
            auto_generate_questions INTEGER NOT NULL DEFAULT 1,
            is_active INTEGER NOT NULL DEFAULT 1,
            last_connected_at TEXT,
            created_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS discovered_study_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            connection_id INTEGER NOT NULL,
            provider_type TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_path_or_remote_id TEXT NOT NULL,
            file_ext TEXT NOT NULL,
            file_size INTEGER NOT NULL DEFAULT 0,
            sha256_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'discovered',
            stored_file_id INTEGER,
            material_id INTEGER,
            battery_id INTEGER,
            extracted_topics_count INTEGER NOT NULL DEFAULT 0,
            extracted_questions_count INTEGER NOT NULL DEFAULT 0,
            related_topics_json TEXT NOT NULL DEFAULT '[]',
            discovered_at TEXT NOT NULL,
            last_synced_at TEXT NOT NULL,
            FOREIGN KEY (connection_id) REFERENCES storage_connections(id) ON DELETE CASCADE,
            FOREIGN KEY (material_id) REFERENCES study_materials(id) ON DELETE SET NULL,
            FOREIGN KEY (battery_id) REFERENCES question_batteries(id) ON DELETE SET NULL
        )
        """
    )

    conn.commit()
    conn.close()


def get_default_local_directories() -> List[Dict[str, str]]:
    """Retorna os diretórios padrão do sistema operacional do usuário (Downloads, Documentos, Desktop)."""
    home = Path.home()
    candidates = [
        ("Downloads do Usuário", home / "Downloads"),
        ("Documentos do Usuário", home / "Documents"),
        ("Documentos (PT-BR)", home / "Documentos"),
        ("Área de Trabalho (Desktop)", home / "Desktop"),
    ]
    result: List[Dict[str, str]] = []
    seen_paths = set()
    for label, p in candidates:
        resolved = str(p)
        if resolved not in seen_paths and p.exists() and p.is_dir():
            seen_paths.add(resolved)
            result.append(
                {
                    "label": label,
                    "path": resolved,
                    "provider_type": "local_fs",
                }
            )
    return result


def _mask_secret(secret: str) -> str:
    if not secret:
        return ""
    s = secret.strip()
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}...{s[-4:]}"


def create_or_update_connection(
    name: str,
    provider_type: str,
    target_path_or_folder_id: str,
    subject_hint: str = "Multidisciplinar",
    area_hint: str = "Geral",
    api_key: str = "",
    access_token: str = "",
    app_key: str = "",
    app_secret: str = "",
    endpoint_url: str = "",
    local_sync_mirror_path: str = "",
    recursive_scan: bool = True,
    auto_generate_questions: bool = True,
    connection_id: Optional[int] = None,
    nosql_store: Optional[NoSQLDocumentStore] = None,
) -> Dict[str, Any]:
    """Cadastra ou atualiza uma conexão de File System Local, Pasta de Rede, Google Drive, Dropbox ou Nuvem."""
    init_connectors_tables()
    if provider_type not in PROVIDER_TYPES:
        raise ValueError(
            f"Tipo de provedor inválido: '{provider_type}'. Use um de: {', '.join(PROVIDER_TYPES.keys())}"
        )
    if not name.strip():
        raise ValueError("O nome da conexão é obrigatório.")
    if not target_path_or_folder_id.strip() and not local_sync_mirror_path.strip():
        raise ValueError(
            "Informe o caminho da pasta (Local/Rede) ou o Folder ID / Caminho na Nuvem."
        )

    now = datetime.now().isoformat()
    conn = database.get_connection()
    cur = conn.cursor()

    if connection_id is not None:
        existing = conn.execute(
            "SELECT * FROM storage_connections WHERE id = ?", (connection_id,)
        ).fetchone()
        if not existing:
            conn.close()
            raise ValueError(f"Conexão #{connection_id} não encontrada.")

        new_api_key = api_key if (api_key and "..." not in api_key) else existing["api_key"]
        new_token = (
            access_token
            if (access_token and "..." not in access_token)
            else existing["access_token"]
        )
        new_app_key = app_key if (app_key and "..." not in app_key) else existing["app_key"]
        new_app_secret = (
            app_secret
            if (app_secret and "..." not in app_secret)
            else existing["app_secret"]
        )

        cur.execute(
            """
            UPDATE storage_connections
            SET name = ?, provider_type = ?, target_path_or_folder_id = ?,
                subject_hint = ?, area_hint = ?, api_key = ?, access_token = ?,
                app_key = ?, app_secret = ?, endpoint_url = ?, local_sync_mirror_path = ?,
                recursive_scan = ?, auto_generate_questions = ?
            WHERE id = ?
            """,
            (
                name.strip(),
                provider_type,
                target_path_or_folder_id.strip(),
                subject_hint.strip() or "Multidisciplinar",
                area_hint.strip() or "Geral",
                new_api_key.strip(),
                new_token.strip(),
                new_app_key.strip(),
                new_app_secret.strip(),
                endpoint_url.strip(),
                local_sync_mirror_path.strip(),
                1 if recursive_scan else 0,
                1 if auto_generate_questions else 0,
                connection_id,
            ),
        )
        cid = connection_id
    else:
        cur.execute(
            """
            INSERT INTO storage_connections (
                name, provider_type, target_path_or_folder_id, subject_hint, area_hint,
                api_key, access_token, app_key, app_secret, endpoint_url,
                local_sync_mirror_path, recursive_scan, auto_generate_questions,
                is_active, last_connected_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, NULL, ?)
            """,
            (
                name.strip(),
                provider_type,
                target_path_or_folder_id.strip(),
                subject_hint.strip() or "Multidisciplinar",
                area_hint.strip() or "Geral",
                api_key.strip(),
                access_token.strip(),
                app_key.strip(),
                app_secret.strip(),
                endpoint_url.strip(),
                local_sync_mirror_path.strip(),
                1 if recursive_scan else 0,
                1 if auto_generate_questions else 0,
                now,
            ),
        )
        cid = int(cur.lastrowid)

    conn.commit()
    row = conn.execute("SELECT * FROM storage_connections WHERE id = ?", (cid,)).fetchone()
    conn.close()

    formatted = _format_connection_row(dict(row))
    store = nosql_store or NoSQLDocumentStore()
    store.upsert_document("storage_connections", str(cid), formatted)
    return formatted


def _format_connection_row(d: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": d["id"],
        "name": d["name"],
        "provider_type": d["provider_type"],
        "provider_label": PROVIDER_TYPES.get(d["provider_type"], {}).get(
            "name", d["provider_type"]
        ),
        "target_path_or_folder_id": d["target_path_or_folder_id"],
        "subject_hint": d["subject_hint"],
        "area_hint": d["area_hint"],
        "has_api_key": bool(d.get("api_key")),
        "has_access_token": bool(d.get("access_token")),
        "api_key_masked": _mask_secret(d.get("api_key", "")),
        "access_token_masked": _mask_secret(d.get("access_token", "")),
        "app_key_masked": _mask_secret(d.get("app_key", "")),
        "endpoint_url": d.get("endpoint_url", ""),
        "local_sync_mirror_path": d.get("local_sync_mirror_path", ""),
        "recursive_scan": bool(d.get("recursive_scan", 1)),
        "auto_generate_questions": bool(d.get("auto_generate_questions", 1)),
        "is_active": bool(d.get("is_active", 1)),
        "last_connected_at": d.get("last_connected_at"),
        "created_at": d.get("created_at"),
    }


def list_connections() -> List[Dict[str, Any]]:
    """Lista todas as conexões cadastradas com contagem de arquivos descobertos e baterias geradas."""
    init_connectors_tables()
    conn = database.get_connection()
    rows = conn.execute(
        "SELECT * FROM storage_connections ORDER BY id DESC"
    ).fetchall()

    result: List[Dict[str, Any]] = []
    for r in rows:
        item = _format_connection_row(dict(r))
        stats = conn.execute(
            """
            SELECT
                COUNT(*) as total_files,
                SUM(CASE WHEN battery_id IS NOT NULL THEN 1 ELSE 0 END) as files_with_questions
            FROM discovered_study_files
            WHERE connection_id = ?
            """,
            (item["id"],),
        ).fetchone()
        item["discovered_files_count"] = int(stats["total_files"] or 0)
        item["files_with_questions_count"] = int(stats["files_with_questions"] or 0)
        result.append(item)

    conn.close()
    return result


def delete_connection(connection_id: int, nosql_store: Optional[NoSQLDocumentStore] = None) -> bool:
    """Remove uma conexão cadastrada e seus registros de rastreamento."""
    init_connectors_tables()
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM discovered_study_files WHERE connection_id = ?", (connection_id,))
    cur.execute("DELETE FROM storage_connections WHERE id = ?", (connection_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()

    store = nosql_store or NoSQLDocumentStore()
    store.delete_by_id("storage_connections", str(connection_id))
    return deleted


# ===========================================================================
# PARSEAMENTO MULTI-FORMATO (PDF, JSON, CSV, XML, TXT, MD)
# ===========================================================================

def parse_study_file_bytes(
    file_bytes: bytes,
    filename: str,
    subject_hint: str = "Multidisciplinar",
) -> Dict[str, Any]:
    """
    Analisa o binário de qualquer arquivo de estudo suportado (`.pdf`, `.json`, `.csv`, `.xml`, `.txt`, `.md`)
    e extrai de forma padronizada:
    - `pages`: lista de páginas/blocos `[{"page_number": 1, "text": "..."}]`
    - `extracted_questions`: questões Cebraspe encontradas no arquivo (se houver)
    - `parsed_topics`: árvore de tópicos, subtópicos e períodos sintáticos
    """
    ext = Path(filename).suffix.lower()
    pages: List[Dict[str, Any]] = []
    extracted_questions: List[Dict[str, Any]] = []

    if ext == ".pdf":
        pages = extract_pdf_pages(file_bytes, filename=filename)
        extracted_questions = extract_questions_heuristic(pages)

    elif ext == ".json":
        text_content = file_bytes.decode("utf-8", errors="ignore")
        try:
            data = json.loads(text_content)
        except Exception:
            data = {"raw_text": text_content}

        blocks: List[str] = []
        if isinstance(data, list):
            for idx, item in enumerate(data, start=1):
                if isinstance(item, dict):
                    stmt = (
                        item.get("statement")
                        or item.get("enunciado")
                        or item.get("texto")
                        or item.get("text")
                        or item.get("content")
                    )
                    ans = str(item.get("answer") or item.get("gabarito") or "").upper().strip()
                    sub = (
                        item.get("subtopic")
                        or item.get("subtopico")
                        or item.get("topic")
                        or item.get("topico")
                        or f"Item {idx}"
                    )
                    if stmt:
                        blocks.append(f"{idx}. {sub}\n{stmt}")
                        if ans in ("C", "E", "CERTO", "ERRADO"):
                            extracted_questions.append(
                                {
                                    "subtopic": str(sub),
                                    "exam_info": str(item.get("exam_info") or item.get("banca") or "CEBRASPE (JSON)"),
                                    "statement": str(stmt),
                                    "answer": "C" if ans.startswith("C") else "E",
                                }
                            )
                elif isinstance(item, str):
                    blocks.append(item)
        elif isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, str):
                    blocks.append(f"1. {k}\n{v}")
                elif isinstance(v, list):
                    sub_lines = []
                    for sub_idx, entry in enumerate(v, start=1):
                        if isinstance(entry, dict):
                            stmt = (
                                entry.get("statement")
                                or entry.get("enunciado")
                                or entry.get("text")
                                or entry.get("resumo")
                                or json.dumps(entry, ensure_ascii=False)
                            )
                            ans = str(entry.get("answer") or entry.get("gabarito") or "").upper().strip()
                            sub_topic = entry.get("subtopic") or entry.get("topico") or k
                            sub_lines.append(str(stmt))
                            if ans in ("C", "E", "CERTO", "ERRADO"):
                                extracted_questions.append(
                                    {
                                        "subtopic": str(sub_topic),
                                        "exam_info": "CEBRASPE (JSON)",
                                        "statement": str(stmt),
                                        "answer": "C" if ans.startswith("C") else "E",
                                    }
                                )
                        else:
                            sub_lines.append(str(entry))
                    blocks.append(f"1. {k}\n" + "\n".join(sub_lines))

        joined_text = "\n\n".join(blocks).strip() or text_content
        pages = [{"page_number": 1, "text": joined_text}]

    elif ext == ".csv":
        text_content = file_bytes.decode("utf-8-sig", errors="ignore")
        reader = csv.reader(io.StringIO(text_content), delimiter=";" if ";" in text_content[:400] else ",")
        rows = list(reader)
        blocks = []
        headers = [h.strip().lower() for h in rows[0]] if rows else []

        start_idx = 1 if headers and any(h in headers for h in ("statement", "enunciado", "texto", "topico", "topic", "conceito")) else 0
        for r_idx, row in enumerate(rows[start_idx:], start=1):
            if not row or not any(cell.strip() for cell in row):
                continue
            if headers and len(row) == len(headers):
                row_dict = dict(zip(headers, [c.strip() for c in row]))
                topic_val = row_dict.get("topico") or row_dict.get("topic") or row_dict.get("subtopic") or subject_hint
                stmt_val = (
                    row_dict.get("enunciado")
                    or row_dict.get("statement")
                    or row_dict.get("texto")
                    or row_dict.get("resumo")
                    or " ".join(row)
                )
                ans_val = (row_dict.get("gabarito") or row_dict.get("answer") or "").upper().strip()
                blocks.append(f"1. {topic_val}\n{stmt_val}")
                if ans_val in ("C", "E", "CERTO", "ERRADO"):
                    extracted_questions.append(
                        {
                            "subtopic": topic_val,
                            "exam_info": "CEBRASPE (CSV)",
                            "statement": stmt_val,
                            "answer": "C" if ans_val.startswith("C") else "E",
                        }
                    )
            else:
                line_str = " — ".join(c.strip() for c in row if c.strip())
                blocks.append(line_str)

        pages = [{"page_number": 1, "text": "\n\n".join(blocks).strip() or text_content}]

    elif ext == ".xml":
        text_content = file_bytes.decode("utf-8", errors="ignore")
        blocks = []
        try:
            root = ET.fromstring(text_content)
            for idx, elem in enumerate(root.iter(), start=1):
                if elem is root:
                    continue
                tag_name = elem.tag.split("}")[-1].lower()
                if tag_name in ("questao", "question", "item", "assertiva", "topico", "topic", "conceito", "artigo"):
                    topic_attr = (
                        elem.attrib.get("topico")
                        or elem.attrib.get("topic")
                        or elem.attrib.get("subtopic")
                        or elem.findtext("topico")
                        or elem.findtext("topic")
                        or elem.findtext("subtopico")
                        or subject_hint
                    )
                    stmt_text = (
                        elem.findtext("enunciado")
                        or elem.findtext("statement")
                        or elem.findtext("texto")
                        or elem.findtext("conteudo")
                        or (elem.text.strip() if elem.text and elem.text.strip() else "")
                    )
                    ans_text = (
                        elem.attrib.get("gabarito")
                        or elem.attrib.get("answer")
                        or elem.findtext("gabarito")
                        or elem.findtext("answer")
                        or ""
                    ).upper().strip()

                    if stmt_text:
                        blocks.append(f"1. {topic_attr}\n{stmt_text.strip()}")
                        if ans_text in ("C", "E", "CERTO", "ERRADO"):
                            extracted_questions.append(
                                {
                                    "subtopic": str(topic_attr).strip(),
                                    "exam_info": "CEBRASPE (XML)",
                                    "statement": stmt_text.strip(),
                                    "answer": "C" if ans_text.startswith("C") else "E",
                                }
                            )
            if not blocks:
                all_texts = [t.strip() for t in root.itertext() if t.strip()]
                blocks.append("\n".join(all_texts))
        except Exception:
            blocks.append(text_content)

        pages = [{"page_number": 1, "text": "\n\n".join(blocks).strip() or text_content}]

    else:
        # .txt ou .md
        text_content = file_bytes.decode("utf-8", errors="ignore")
        pages = [{"page_number": 1, "text": text_content}]
        extracted_questions = extract_questions_heuristic(pages)

    if not pages:
        pages = [{"page_number": 1, "text": f"Conteúdo importado de {filename}."}]

    parsed_topics = parse_pdf_topics_and_subtopics(pages)
    return {
        "pages": pages,
        "extracted_questions": extracted_questions,
        "parsed_topics": parsed_topics,
    }


# ===========================================================================
# CONECTORES DE BUSCA (LOCAL FS, REDE, GOOGLE DRIVE, DROPBOX, NUVEM)
# ===========================================================================

def _scan_filesystem_directory(
    directory_path: str,
    recursive: bool = True,
    max_files: int = 100,
) -> List[Dict[str, Any]]:
    """Varre um diretório do File System Local ou Pasta de Rede em busca de arquivos de estudo."""
    expanded = os.path.expandvars(os.path.expanduser(directory_path.strip()))
    base = Path(expanded)
    if not base.exists() or not base.is_dir():
        raise ValueError(f"O diretório '{directory_path}' não existe ou não está acessível.")

    found_files: List[Dict[str, Any]] = []
    iterator = base.rglob("*") if recursive else base.glob("*")

    for entry in iterator:
        if len(found_files) >= max_files:
            break
        try:
            if not entry.is_file():
                continue
            ext = entry.suffix.lower()
            if ext not in SUPPORTED_STUDY_EXTENSIONS:
                continue
            # Ignorar arquivos internos do próprio banco do projeto e pastas de sistema/dependências
            if "nosql_document_store" in entry.name:
                continue
            rel_parts = {p.lower() for p in entry.relative_to(base).parts[:-1]}
            if rel_parts & IGNORED_DIR_NAMES:
                continue
            # Ignorar arquivos vazios ou acima do limite de tamanho
            file_size = entry.stat().st_size
            if file_size == 0 or file_size > MAX_STUDY_FILE_SIZE_BYTES:
                continue

            raw_bytes = entry.read_bytes()
            sha256_hash = hashlib.sha256(raw_bytes).hexdigest()
            found_files.append(
                {
                    "file_name": entry.name,
                    "file_path_or_remote_id": str(entry.resolve()),
                    "file_ext": ext,
                    "file_size": len(raw_bytes),
                    "sha256_hash": sha256_hash,
                    "raw_bytes": raw_bytes,
                }
            )
        except PermissionError:
            continue
        except OSError:
            continue

    return found_files


def _fetch_google_drive_files(conn_row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Busca arquivos de estudo no Google Drive (API v3) usando `api_key` ou `access_token`
    cadastrados pelo usuário, ou a partir do diretório espelho (`local_sync_mirror_path`).
    """
    mirror_path = (conn_row.get("local_sync_mirror_path") or "").strip()
    if mirror_path and Path(os.path.expanduser(mirror_path)).exists():
        return _scan_filesystem_directory(
            mirror_path, recursive=bool(conn_row.get("recursive_scan", 1))
        )

    folder_id = (conn_row.get("target_path_or_folder_id") or "root").strip()
    # Se o usuário informou um caminho local do Google Drive Desktop (ex: G:\Meu Drive\...)
    if os.path.sep in folder_id or (len(folder_id) > 2 and folder_id[1] == ":"):
        if Path(os.path.expanduser(folder_id)).exists():
            return _scan_filesystem_directory(
                folder_id, recursive=bool(conn_row.get("recursive_scan", 1))
            )

    api_key = (conn_row.get("api_key") or "").strip()
    access_token = (conn_row.get("access_token") or "").strip()
    if not api_key and not access_token:
        raise ValueError(
            "Para conectar ao Google Drive via API, cadastre sua API Key ou OAuth Access Token (ou informe o caminho local do Google Drive Desktop em 'Pasta Espelho Local')."
        )

    q_str = f"'{folder_id}' in parents and trashed = false"
    params = {
        "q": q_str,
        "fields": "files(id,name,mimeType,size)",
        "pageSize": "50",
    }
    if api_key:
        params["key"] = api_key

    url = f"https://www.googleapis.com/drive/v3/files?{urllib.parse.urlencode(params)}"
    headers: Dict[str, str] = {"Accept": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            listing = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ValueError(f"Erro na API do Google Drive (HTTP {e.code}): verifique sua chave/token e o Folder ID.")
    except Exception as e:
        raise ValueError(f"Não foi possível conectar à API do Google Drive: {e}")

    discovered: List[Dict[str, Any]] = []
    for f in listing.get("files", []):
        fname = f.get("name", "")
        fid = f.get("id", "")
        ext = Path(fname).suffix.lower()
        if ext not in SUPPORTED_STUDY_EXTENSIONS:
            continue

        dl_params = {"alt": "media"}
        if api_key:
            dl_params["key"] = api_key
        dl_url = f"https://www.googleapis.com/drive/v3/files/{fid}?{urllib.parse.urlencode(dl_params)}"
        dl_req = urllib.request.Request(dl_url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(dl_req, timeout=20) as dl_resp:
                raw_bytes = dl_resp.read()
            discovered.append(
                {
                    "file_name": fname,
                    "file_path_or_remote_id": f"gdrive://{fid}/{fname}",
                    "file_ext": ext,
                    "file_size": len(raw_bytes),
                    "sha256_hash": hashlib.sha256(raw_bytes).hexdigest(),
                    "raw_bytes": raw_bytes,
                }
            )
        except Exception:
            continue

    return discovered


def _fetch_dropbox_files(conn_row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Busca arquivos de estudo no Dropbox (API v2) usando o `access_token` cadastrado pelo usuário,
    ou a partir do diretório espelho (`local_sync_mirror_path`).
    """
    mirror_path = (conn_row.get("local_sync_mirror_path") or "").strip()
    if mirror_path and Path(os.path.expanduser(mirror_path)).exists():
        return _scan_filesystem_directory(
            mirror_path, recursive=bool(conn_row.get("recursive_scan", 1))
        )

    folder_path = (conn_row.get("target_path_or_folder_id") or "").strip()
    if os.path.sep in folder_path or (len(folder_path) > 2 and folder_path[1] == ":"):
        if Path(os.path.expanduser(folder_path)).exists():
            return _scan_filesystem_directory(
                folder_path, recursive=bool(conn_row.get("recursive_scan", 1))
            )

    access_token = (conn_row.get("access_token") or conn_row.get("api_key") or "").strip()
    if not access_token:
        raise ValueError(
            "Para conectar ao Dropbox via nuvem, cadastre seu Access Token do Dropbox (ou informe o diretório local do Dropbox em 'Pasta Espelho Local')."
        )

    norm_path = "" if folder_path in ("/", "", "root") else (folder_path if folder_path.startswith("/") else f"/{folder_path}")
    list_url = "https://api.dropboxapi.com/2/files/list_folder"
    list_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    list_payload = json.dumps(
        {"path": norm_path, "recursive": bool(conn_row.get("recursive_scan", 1)), "limit": 50}
    ).encode("utf-8")

    req = urllib.request.Request(list_url, data=list_payload, headers=list_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            listing = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ValueError(f"Erro na API do Dropbox (HTTP {e.code}): verifique seu Access Token e o caminho da pasta.")
    except Exception as e:
        raise ValueError(f"Não foi possível conectar à API do Dropbox: {e}")

    discovered: List[Dict[str, Any]] = []
    for entry in listing.get("entries", []):
        if entry.get(".tag") != "file":
            continue
        fname = entry.get("name", "")
        path_lower = entry.get("path_lower") or entry.get("path_display") or f"/{fname}"
        ext = Path(fname).suffix.lower()
        if ext not in SUPPORTED_STUDY_EXTENSIONS:
            continue

        dl_url = "https://content.dropboxapi.com/2/files/download"
        dl_headers = {
            "Authorization": f"Bearer {access_token}",
            "Dropbox-API-Arg": json.dumps({"path": path_lower}),
        }
        dl_req = urllib.request.Request(dl_url, headers=dl_headers, method="POST")
        try:
            with urllib.request.urlopen(dl_req, timeout=20) as dl_resp:
                raw_bytes = dl_resp.read()
            discovered.append(
                {
                    "file_name": fname,
                    "file_path_or_remote_id": f"dropbox://{path_lower}",
                    "file_ext": ext,
                    "file_size": len(raw_bytes),
                    "sha256_hash": hashlib.sha256(raw_bytes).hexdigest(),
                    "raw_bytes": raw_bytes,
                }
            )
        except Exception:
            continue

    return discovered


def _fetch_custom_cloud_files(conn_row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Busca arquivos em nuvem customizada ou pasta espelho configurada."""
    mirror_path = (conn_row.get("local_sync_mirror_path") or "").strip()
    if mirror_path and Path(os.path.expanduser(mirror_path)).exists():
        return _scan_filesystem_directory(
            mirror_path, recursive=bool(conn_row.get("recursive_scan", 1))
        )
    target = (conn_row.get("target_path_or_folder_id") or "").strip()
    if target and Path(os.path.expanduser(target)).exists():
        return _scan_filesystem_directory(
            target, recursive=bool(conn_row.get("recursive_scan", 1))
        )
    raise ValueError(
        "Informe um diretório de sincronização válido ou endpoint acessível para a nuvem customizada."
    )


# ===========================================================================
# INGESTÃO, RELACIONAMENTO CONCEITUAL E GERAÇÃO DE QUESTÕES A PARTIR DO ARQUIVO
# ===========================================================================

def ingest_and_generate_questions_from_discovered_file(
    discovered_file_id: int,
    raw_bytes: Optional[bytes] = None,
    questions_count: int = 10,
    api_key: str = "",
    model_name: str = "gemini-2.5-flash",
    nosql_store: Optional[NoSQLDocumentStore] = None,
) -> Dict[str, Any]:
    """
    Processa um arquivo descoberto (`PDF`, `JSON`, `CSV`, `XML`, `TXT`, `MD`),
    salva no Vault híbrido SQL+NoSQL, cria o material de estudo, registra os relacionamentos
    `Tópico -> Subtópico -> Conceito -> Subconceito` e gera uma Bateria de Questões Cebraspe
    pronta para apresentar ao aluno!
    """
    init_connectors_tables()
    spaced_review.init_spaced_review_tables()

    conn = database.get_connection()
    file_row = conn.execute(
        "SELECT * FROM discovered_study_files WHERE id = ?", (discovered_file_id,)
    ).fetchone()
    if not file_row:
        conn.close()
        raise ValueError(f"Arquivo rastreado #{discovered_file_id} não encontrado.")

    f_dict = dict(file_row)
    conn_row = conn.execute(
        "SELECT * FROM storage_connections WHERE id = ?", (f_dict["connection_id"],)
    ).fetchone()
    conn.close()

    subject = (dict(conn_row).get("subject_hint") if conn_row else None) or "Multidisciplinar"
    area = (dict(conn_row).get("area_hint") if conn_row else None) or "Geral"
    filename = f_dict["file_name"]

    if raw_bytes is None:
        remote_or_local = f_dict["file_path_or_remote_id"]
        local_candidate = Path(remote_or_local)
        if local_candidate.exists() and local_candidate.is_file():
            raw_bytes = local_candidate.read_bytes()
        elif f_dict.get("stored_file_id"):
            from storage_manager import get_stored_file_With_bytes
            loaded = get_stored_file_With_bytes(int(f_dict["stored_file_id"]))
            if loaded:
                raw_bytes = loaded["bytes"]

    if not raw_bytes:
        raise ValueError(
            f"Não foi possível ler os bytes do arquivo '{filename}'. Verifique se o caminho está acessível."
        )

    # 1. Parsear o arquivo de estudo (PDF, JSON, CSV, XML, TXT, MD)
    parsed = parse_study_file_bytes(raw_bytes, filename, subject_hint=subject)
    pages = parsed["pages"]
    extracted_questions = parsed["extracted_questions"]
    parsed_topics = parsed["parsed_topics"]

    # 2. Analisar recorrência dos tópicos do arquivo
    recurrence_analysis = analyze_pdf_recurrence(
        pages=pages,
        heuristic_questions=extracted_questions,
        area=area,
        api_key=api_key,
        model_name=model_name,
        custom_subject_hint=subject,
    )
    recurrence_map = recurrence_analysis.get("subtopics", [])
    detected_subject = recurrence_analysis.get("detected_subject") or subject

    material_title = f"[{f_dict['provider_type'].upper()}] {Path(filename).stem}"
    material_id = database.save_study_material(
        title=material_title,
        subject=detected_subject,
        area=area,
        total_pages=len(pages),
        pages=pages,
        extracted_questions=extracted_questions,
        recurrence_map=recurrence_map,
    )

    # 3. Salvar binário bruto no Vault Híbrido (SQL + Disco) e Árvore NoSQL
    mime_map = {
        ".pdf": "application/pdf",
        ".json": "application/json",
        ".csv": "text/csv",
        ".xml": "application/xml",
        ".txt": "text/plain",
        ".md": "text/markdown",
    }
    stored_meta = store_uploaded_file(
        file_bytes=raw_bytes,
        filename=filename,
        material_id=material_id,
        file_role=f"connector_{f_dict['provider_type']}",
        mime_type=mime_map.get(f_dict["file_ext"], "application/octet-stream"),
    )

    store = nosql_store or NoSQLDocumentStore()
    save_material_knowledge_tree_nosql(
        material_id=material_id,
        title=material_title,
        subject=subject,
        area=area,
        parsed_topics=parsed_topics,
        recurrence_map=recurrence_map,
        stored_file_ids=[stored_meta["file_id"]],
        nosql_store=store,
    )

    # 4. Criar relacionamentos conceituais automáticos (Tópico -> Subtópico -> Conceito -> Subconceito)
    related_topics_summary: List[Dict[str, str]] = []
    db_conn = database.get_connection()
    now_iso = datetime.now().isoformat()

    for pt in parsed_topics[:12]:
        t_name = pt.get("topic") or material_title
        s_name = pt.get("subtopic") or "Geral"
        periods = pt.get("periods", [])
        first_period_markers = periods[0].get("markers", []) if periods else []
        concept_name = f"{s_name} ({Path(filename).stem})"
        subconcept_name = (
            first_period_markers[0] if first_period_markers else "Regra Normativa e Jurisprudencial"
        )
        related_topics_summary.append(
            {
                "topic": t_name,
                "subtopic": s_name,
                "concept": concept_name,
                "subconcept": subconcept_name,
            }
        )
        existing_link = db_conn.execute(
            """
            SELECT id FROM concept_hierarchy_links
            WHERE lower(topic) = lower(?) AND lower(subtopic) = lower(?) AND lower(concept) = lower(?)
            """,
            (t_name, s_name, concept_name),
        ).fetchone()
        if not existing_link:
            db_conn.execute(
                """
                INSERT INTO concept_hierarchy_links (
                    material_id, subject, topic, subtopic, concept, subconcept,
                    summary_ids_json, generated_questions_count, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, '[]', ?, ?)
                """,
                (
                    material_id,
                    subject,
                    t_name,
                    s_name,
                    concept_name,
                    subconcept_name,
                    questions_count,
                    now_iso,
                ),
            )

    db_conn.commit()
    db_conn.close()

    # 5. Gerar as questões Cebraspe (Certo/Errado) a partir do arquivo conectado para apresentar ao aluno
    generated_assertions: List[Dict[str, Any]] = []

    # Se o arquivo (JSON/CSV/XML/PDF) já continha questões reais extraídas, converte e complementa com questões inéditas dos períodos
    for eq in extracted_questions[:questions_count]:
        ans_char = "C" if str(eq.get("answer", "C")).upper().startswith("C") else "E"
        generated_assertions.append(
            {
                "subtopic": eq.get("subtopic", "Geral"),
                "recurrence_level": "Muito Alta",
                "command_text": f"[{eq.get('exam_info', 'Arquivo Conectado')}] Acerca de {subject}, julgue o item a seguir.",
                "statement": eq["statement"],
                "answer": ans_char,
                "explanation": (
                    f"ITEM {'CERTO' if ans_char == 'C' else 'ERRADO'}. Questão extraída diretamente do arquivo "
                    f"conectado '{filename}' ({f_dict['provider_type']})."
                ),
                "pdf_quote": eq["statement"],
                "pdf_page": "p. 1",
                "trap_type": "Questão Extraída do Arquivo Conectado",
                "difficulty": "Média",
                "inspired_by_real_question": f"Importado de {filename}",
            }
        )

    remaining = max(0, questions_count - len(generated_assertions))
    if remaining > 0:
        period_assertions = extract_assertions_from_subtopics(
            structured_topics=parsed_topics,
            subject=detected_subject,
            area=area,
            variations_per_period=2,
        )
        generated_assertions.extend(period_assertions[:remaining])

    if len(generated_assertions) < questions_count:
        extra_needed = questions_count - len(generated_assertions)
        plan_for_extra = (
            [dict(s, target_questions=max(2, extra_needed)) for s in recurrence_map[:2]]
            if recurrence_map
            else [
                {
                    "topic": material_title,
                    "subtopic": "Conteúdo Geral",
                    "recurrence_level": "Alta",
                    "target_questions": extra_needed,
                }
            ]
        )
        fallback_items = generate_cebraspe_assertions(
            pages=pages,
            real_questions=extracted_questions,
            subtopic_plan=plan_for_extra,
            subject=detected_subject,
            title=material_title,
            area=area,
            depth="Misto Padrão Cebraspe",
            api_key=api_key,
            model_name=model_name,
        )
        generated_assertions.extend(fallback_items[:extra_needed])

    battery_title = f"Questões Conectadas ({f_dict['file_ext'].upper()}) — {Path(filename).stem}"
    battery_id = database.save_question_battery(
        material_id=material_id,
        title=battery_title,
        subject=subject,
        area=area,
        depth=f"Importado via {f_dict['provider_type']} ({filename})",
        recurrence_summary=recurrence_map,
        assertions=generated_assertions[: max(questions_count, len(generated_assertions))],
    )

    # 6. Atualizar status de rastreamento do arquivo descoberto
    conn2 = database.get_connection()
    conn2.execute(
        """
        UPDATE discovered_study_files
        SET status = 'questions_generated',
            stored_file_id = ?,
            material_id = ?,
            battery_id = ?,
            extracted_topics_count = ?,
            extracted_questions_count = ?,
            related_topics_json = ?,
            last_synced_at = ?
        WHERE id = ?
        """,
        (
            stored_meta["file_id"],
            material_id,
            battery_id,
            len(parsed_topics),
            len(generated_assertions),
            json.dumps(related_topics_summary, ensure_ascii=False),
            now_iso,
            discovered_file_id,
        ),
    )
    updated_file_row = conn2.execute(
        "SELECT * FROM discovered_study_files WHERE id = ?", (discovered_file_id,)
    ).fetchone()
    conn2.commit()
    conn2.close()

    formatted_file = _format_discovered_file_row(dict(updated_file_row))
    store.upsert_document("discovered_files_catalog", str(discovered_file_id), formatted_file)

    battery = database.get_battery(battery_id)
    return {
        "discovered_file": formatted_file,
        "material_id": material_id,
        "battery_id": battery_id,
        "battery": battery,
        "related_topics": related_topics_summary,
    }


def _format_discovered_file_row(d: Dict[str, Any]) -> Dict[str, Any]:
    try:
        rel_topics = json.loads(d.get("related_topics_json") or "[]")
    except Exception:
        rel_topics = []
    return {
        "id": d["id"],
        "connection_id": d["connection_id"],
        "provider_type": d["provider_type"],
        "file_name": d["file_name"],
        "file_path_or_remote_id": d["file_path_or_remote_id"],
        "file_ext": d["file_ext"],
        "file_size": d["file_size"],
        "sha256_hash": d["sha256_hash"],
        "status": d["status"],
        "stored_file_id": d.get("stored_file_id"),
        "material_id": d.get("material_id"),
        "battery_id": d.get("battery_id"),
        "extracted_topics_count": d.get("extracted_topics_count", 0),
        "extracted_questions_count": d.get("extracted_questions_count", 0),
        "related_topics": rel_topics,
        "discovered_at": d["discovered_at"],
        "last_synced_at": d["last_synced_at"],
    }


def list_discovered_files(
    connection_id: Optional[int] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Lista os arquivos de estudo encontrados e rastreados pelo banco de dados."""
    init_connectors_tables()
    conn = database.get_connection()

    query = "SELECT * FROM discovered_study_files WHERE 1=1"
    params: List[Any] = []
    if connection_id is not None:
        query += " AND connection_id = ?"
        params.append(connection_id)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY last_synced_at DESC, id DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [_format_discovered_file_row(dict(r)) for r in rows]


def sync_connection_and_build_questions(
    connection_id: int,
    auto_ingest_and_generate: Optional[bool] = None,
    questions_per_file: int = 8,
    max_files_to_ingest: int = 10,
    api_key: str = "",
    model_name: str = "gemini-2.5-flash",
    nosql_store: Optional[NoSQLDocumentStore] = None,
) -> Dict[str, Any]:
    """
    Conecta à fonte de dados configurada (`local_fs`, `network_share`, `google_drive`, `dropbox`, `cloud_custom`),
    busca arquivos de estudo (`PDF/JSON/CSV/XML/TXT/MD`), salva e rastreia no banco, cria os relacionamentos
    e gera as questões Cebraspe apresentando-as ao aluno!
    """
    init_connectors_tables()
    conn = database.get_connection()
    conn_row = conn.execute(
        "SELECT * FROM storage_connections WHERE id = ?", (connection_id,)
    ).fetchone()
    if not conn_row:
        conn.close()
        raise ValueError(f"Conexão #{connection_id} não encontrada.")

    c_dict = dict(conn_row)
    conn.close()

    ptype = c_dict["provider_type"]
    if ptype in ("local_fs", "network_share"):
        raw_discovered = _scan_filesystem_directory(
            c_dict["target_path_or_folder_id"],
            recursive=bool(c_dict.get("recursive_scan", 1)),
        )
    elif ptype == "google_drive":
        raw_discovered = _fetch_google_drive_files(c_dict)
    elif ptype == "dropbox":
        raw_discovered = _fetch_dropbox_files(c_dict)
    else:
        raw_discovered = _fetch_custom_cloud_files(c_dict)

    now_iso = datetime.now().isoformat()
    should_ingest = (
        auto_ingest_and_generate
        if auto_ingest_and_generate is not None
        else bool(c_dict.get("auto_generate_questions", 1))
    )

    db_conn = database.get_connection()
    cur = db_conn.cursor()
    cur.execute(
        "UPDATE storage_connections SET last_connected_at = ? WHERE id = ?",
        (now_iso, connection_id),
    )

    tracked_records: List[ Tuple[int, bytes, bool] ] = []
    for item in raw_discovered:
        existing = db_conn.execute(
            """
            SELECT id, sha256_hash, battery_id FROM discovered_study_files
            WHERE connection_id = ? AND file_path_or_remote_id = ?
            """,
            (connection_id, item["file_path_or_remote_id"]),
        ).fetchone()

        if existing:
            disc_id = int(existing["id"])
            needs_reingest = (existing["sha256_hash"] != item["sha256_hash"]) or (
                existing["battery_id"] is None
            )
            cur.execute(
                """
                UPDATE discovered_study_files
                SET file_size = ?, sha256_hash = ?, last_synced_at = ?
                WHERE id = ?
                """,
                (item["file_size"], item["sha256_hash"], now_iso, disc_id),
            )
            tracked_records.append((disc_id, item["raw_bytes"], needs_reingest))
        else:
            cur.execute(
                """
                INSERT INTO discovered_study_files (
                    connection_id, provider_type, file_name, file_path_or_remote_id,
                    file_ext, file_size, sha256_hash, status, discovered_at, last_synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'discovered', ?, ?)
                """,
                (
                    connection_id,
                    ptype,
                    item["file_name"],
                    item["file_path_or_remote_id"],
                    item["file_ext"],
                    item["file_size"],
                    item["sha256_hash"],
                    now_iso,
                    now_iso,
                ),
            )
            disc_id = int(cur.lastrowid)
            tracked_records.append((disc_id, item["raw_bytes"], True))

    db_conn.commit()
    db_conn.close()

    generated_batteries: List[Dict[str, Any]] = []
    ingested_count = 0

    if should_ingest:
        for disc_id, f_bytes, needs_ingest in tracked_records:
            if not needs_ingest:
                continue
            if ingested_count >= max_files_to_ingest:
                break
            try:
                res = ingest_and_generate_questions_from_discovered_file(
                    discovered_file_id=disc_id,
                    raw_bytes=f_bytes,
                    questions_count=questions_per_file,
                    api_key=api_key,
                    model_name=model_name,
                    nosql_store=nosql_store,
                )
                ingested_count += 1
                if res.get("battery"):
                    generated_batteries.append(res["battery"])
            except Exception:
                continue

    all_files = list_discovered_files(connection_id=connection_id)
    return {
        "connection_id": connection_id,
        "provider_type": ptype,
        "synced_at": now_iso,
        "total_discovered_files": len(all_files),
        "newly_ingested_files_count": ingested_count,
        "generated_batteries": generated_batteries,
        "discovered_files": all_files,
    }
