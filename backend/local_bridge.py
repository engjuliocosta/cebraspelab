r"""
Módulo de Ponte Híbrida GitHub Pages <-> PC Local & Empacotamento Comercial (`local_bridge.py`).

Permite duas formas de uso simultâneas para o usuário final:
1. **Interface Web no GitHub Pages (URL de Alto Nível, ex: `https://app.cebraspelab.com.br`) + Banco Local no PC**:
   - O usuário abre o aplicativo pela URL limpa de alto nível (sem `/nome-do-repo` na URL).
   - A interface estática do GitHub Pages conecta-se automaticamente ao Agente Local (`http://127.0.0.1:8000`)
     rodando no computador do aluno via **CORS + Private Network Access (CORS-RFC1918 / Chrome PNA)**.
   - Todos os PDFs, banco SQL (`SQLite`), banco NoSQL (`JSON Document Store`), pastas locais (`Downloads`,
     `Documentos`, `C:\`, `D:\`) e chaves de nuvem (`Google Drive`, `Dropbox`) permanecem **100% no computador
     do usuário**, garantindo privacidade total e custo zero de banco em nuvem.
2. **Execução 100% Local (`http://127.0.0.1:8000` via `CebraspeLab-Universal.pyz` ou `CebraspeLab.exe`)**:
   - O próprio Agente Local também serve a mesma interface compilada caso o aluno esteja 100% sem internet.

Inclui também utilitários de licenciamento/ativação comercial e geração de pacote `.zip` pronto para
entrega em plataformas de infoprodutos/SaaS (como **Hotmart**, Kiwify, Eduzz).
"""

import hashlib
import os
import platform
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import database
import data_connectors
import multi_folder_workspace
import storage_manager
from topic_parser import extract_assertions_from_subtopics, parse_pdf_topics_and_subtopics

DEFAULT_TOP_LEVEL_PAGES_URL = os.environ.get(
    "CEBRASPELAB_PAGES_URL", "https://app.cebraspelab.com.br"
)


def compute_pna_cors_headers(origin: Optional[str] = None, request_pna: Optional[str] = None) -> Dict[str, str]:
    """
    Gera os cabeçalhos HTTP necessários para que navegadores modernos (Chrome, Edge, Brave, Firefox, Safari)
    permitam que uma página HTTPS hospedada no GitHub Pages (domínio de alto nível) acesse a API local
    em `http://127.0.0.1:8000` (Especificação W3C Private Network Access / CORS-RFC1918).
    """
    allowed_origin = origin.strip() if origin and origin.strip() else "*"
    headers: Dict[str, str] = {
        "Access-Control-Allow-Origin": allowed_origin,
        "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With, X-CebraspeLab-Client, Access-Control-Request-Private-Network",
        "Access-Control-Expose-Headers": "Content-Disposition, X-CebraspeLab-Bridge",
        "X-CebraspeLab-Bridge": "local-pc-agent-v2",
    }
    if allowed_origin != "*":
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Vary"] = "Origin"
    if request_pna and request_pna.lower() == "true":
        headers["Access-Control-Allow-Private-Network"] = "true"
    else:
        # Sempre incluir para facilitar preflights de navegadores Chromium a partir de HTTPS -> 127.0.0.1
        headers["Access-Control-Allow-Private-Network"] = "true"
    return headers


def get_license_status() -> Dict[str, Any]:
    """
    Consulta o status de ativação/licença comercial (para distribuição via Hotmart / Kiwify / Eduzz).
    Por padrão, o modo de avaliação/estudante já vem habilitado, permitindo ativar um código de
    transação Hotmart (ex: `HP123456789` ou `CEBRASPE-PRO-...`).
    """
    conn = database.get_connection()
    rows = conn.execute(
        "SELECT key, value FROM settings WHERE key IN ('license_key', 'license_buyer_email', 'license_activated_at', 'custom_pages_url')"
    ).fetchall()
    conn.close()
    meta = {r["key"]: r["value"] for r in rows}

    license_key = meta.get("license_key", "")
    buyer_email = meta.get("license_buyer_email", "")
    activated_at = meta.get("license_activated_at", "")
    custom_pages_url = meta.get("custom_pages_url", "") or DEFAULT_TOP_LEVEL_PAGES_URL

    is_pro = bool(license_key and len(license_key.strip()) >= 6)
    return {
        "is_activated": is_pro,
        "plan": "Pro Vitalício (Hotmart / Completo)" if is_pro else "Edição Local Completa",
        "license_key_masked": (
            f"{license_key[:4]}****{license_key[-3:]}" if len(license_key) > 7 else ("Ativa" if is_pro else "")
        ),
        "buyer_email": buyer_email,
        "activated_at": activated_at,
        "top_level_pages_url": custom_pages_url,
    }


def activate_product_license(
    license_key: str,
    buyer_email: str = "",
    custom_pages_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Valida e salva no banco SQL local o código de transação/licença (ex: código HP da Hotmart
    ou chave de ativação do aluno).
    """
    clean_key = (license_key or "").strip().upper()
    if len(clean_key) < 6:
        raise ValueError(
            "Informe um código de licença ou código de transação Hotmart válido (mínimo de 6 caracteres, ex: HP12345678)."
        )

    now_iso = datetime.now().isoformat(timespec="seconds")
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('license_key', ?)",
        (clean_key,),
    )
    cur.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('license_buyer_email', ?)",
        ((buyer_email or "").strip(),),
    )
    cur.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('license_activated_at', ?)",
        (now_iso,),
    )
    if custom_pages_url and custom_pages_url.strip():
        cur.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('custom_pages_url', ?)",
            (custom_pages_url.strip().rstrip("/"),),
        )
    conn.commit()
    conn.close()
    return get_license_status()


def build_bridge_status(request_origin: Optional[str] = None) -> Dict[str, Any]:
    """
    Retorna o diagnóstico completo da Ponte Local (`127.0.0.1:8000`) para que a interface hospedada
    no GitHub Pages exiba o status da conexão com o banco SQL+NoSQL local do PC do usuário,
    as pastas locais disponíveis e as conexões de nuvem (Google Drive / Dropbox).
    """
    data_connectors.init_connectors_tables()
    multi_folder_workspace.init_multi_folder_tables()

    connections = data_connectors.list_connections()
    workspaces = multi_folder_workspace.list_multi_folder_workspaces()
    stored_files = storage_manager.list_stored_files()
    batteries = database.list_batteries()
    drives_info = multi_folder_workspace.list_available_drives_and_quick_folders()
    lic = get_license_status()

    is_remote_ui = bool(
        request_origin
        and not any(
            local_host in request_origin
            for local_host in ("127.0.0.1", "localhost", "0.0.0.0")
        )
    )

    return {
        "bridge_online": True,
        "bridge_version": "2.1.0",
        "ui_mode": "github_pages_connected_to_local_pc" if is_remote_ui else "local_direct_ui",
        "request_origin": request_origin or "http://127.0.0.1:8000",
        "top_level_pages_url": lic["top_level_pages_url"],
        "pc_environment": {
            "os": platform.system(),
            "os_release": platform.release(),
            "arch": platform.machine(),
            "hostname": platform.node(),
        },
        "local_storage": {
            "sql_db_path": str(database.DB_PATH.resolve()),
            "nosql_store_path": str(storage_manager.NOSQL_PATH.resolve()),
            "pdf_vault_dir": str(storage_manager.VAULT_DIR.resolve()),
            "stored_files_count": len(stored_files),
            "saved_batteries_count": len(batteries),
            "storage_connections_count": len(connections),
            "multi_folder_workspaces_count": len(workspaces),
        },
        "quick_folders": drives_info.get("quick_folders", []),
        "drives": drives_info.get("drives", []),
        "license": lic,
    }


def ingest_browser_selected_files_batch(
    files_payload: List[Dict[str, Any]],
    folder_label: str = "Pasta Selecionada no Navegador",
    subject_hint: str = "Multidisciplinar",
    area_hint: str = "Tribunais / Jurídico",
    questions_per_file: int = 6,
) -> Dict[str, Any]:
    """
    Permite que o usuário, mesmo acessando a interface pelo GitHub Pages, selecione uma pasta inteira
    (ou múltiplos arquivos `.pdf`, `.json`, `.csv`, `.xml`, `.txt`, `.md`) diretamente pelo seletor
    do navegador (`webkitdirectory` / File System Access API) e envie para o banco SQL+NoSQL local no PC,
    deduplicando por SHA-256, criando os relacionamentos conceituais e gerando uma Bateria Unificada!
    """
    if not files_payload:
        raise ValueError("Nenhum arquivo de estudo válido foi enviado do seletor do navegador.")

    seen_hashes = set()
    duplicates_skipped = 0
    processed_files: List[Dict[str, Any]] = []
    unified_assertions: List[Dict[str, Any]] = []
    first_material_id: Optional[int] = None

    for item in files_payload:
        filename = str(item.get("filename") or "arquivo.txt")
        raw_bytes: bytes = item.get("content_bytes") or b""
        if not raw_bytes:
            continue

        ext = Path(filename).suffix.lower()
        if ext not in data_connectors.SUPPORTED_STUDY_EXTENSIONS:
            continue

        file_hash = hashlib.sha256(raw_bytes).hexdigest()
        if file_hash in seen_hashes:
            duplicates_skipped += 1
            continue
        seen_hashes.add(file_hash)

        parsed = data_connectors.parse_study_file_bytes(
            raw_bytes,
            filename,
            subject_hint=subject_hint,
        )
        pages = parsed["pages"]
        parsed_topics = parsed["parsed_topics"]
        extracted_questions = parsed["extracted_questions"]

        mat_id = database.save_study_material(
            title=f"[{folder_label}] {Path(filename).stem}",
            subject=subject_hint,
            area=area_hint,
            total_pages=max(1, len(pages)),
            pages=pages,
            extracted_questions=extracted_questions,
            recurrence_map=[],
        )
        if first_material_id is None:
            first_material_id = mat_id

        stored_meta = storage_manager.store_uploaded_file(
            file_bytes=raw_bytes,
            filename=filename,
            material_id=mat_id,
            file_role="browser_folder_sync",
        )
        storage_manager.save_material_knowledge_tree_nosql(
            material_id=mat_id,
            title=f"[{folder_label}] {Path(filename).stem}",
            subject=subject_hint,
            area=area_hint,
            parsed_topics=parsed_topics,
            recurrence_map=[],
            stored_file_ids=[stored_meta["file_id"]],
        )

        file_assertions: List[Dict[str, Any]] = []
        for eq in extracted_questions[:questions_per_file]:
            file_assertions.append(
                {
                    "subtopic": eq.get("subtopic") or Path(filename).stem,
                    "recurrence_level": "Alta",
                    "command_text": f"Acerca de {subject_hint} ({Path(filename).name}), julgue o item a seguir.",
                    "statement": eq["statement"],
                    "answer": eq["answer"] if eq.get("answer") in ("C", "E") else "C",
                    "explanation": eq.get("commentary") or "Item extraído do arquivo sincronizado.",
                    "pdf_quote": eq["statement"][:220],
                    "pdf_page": f"p. {eq.get('page_number', 1)}",
                    "trap_type": "Questão do Material",
                    "difficulty": "Média",
                    "inspired_by_real_question": eq.get("exam_info") or filename,
                }
            )

        if len(file_assertions) < questions_per_file and parsed_topics:
            gen_period_items = extract_assertions_from_subtopics(
                structured_topics=parsed_topics,
                subject=subject_hint,
                area=area_hint,
                variations_per_period=2,
            )
            needed = max(0, questions_per_file - len(file_assertions))
            file_assertions.extend(gen_period_items[:needed])

        unified_assertions.extend(file_assertions)
        processed_files.append(
            {
                "filename": filename,
                "sha256_hash": file_hash,
                "material_id": mat_id,
                "stored_file_id": stored_meta["file_id"],
                "questions_generated": len(file_assertions),
            }
        )

    if not processed_files:
        raise ValueError(
            "Nenhum arquivo compatível (.pdf, .json, .csv, .xml, .txt, .md) foi encontrado na seleção."
        )

    battery_id = database.save_question_battery(
        material_id=first_material_id,
        title=f"[GitHub Pages <-> PC Local] {folder_label} ({len(processed_files)} arquivo(s))",
        subject=subject_hint,
        area=area_hint,
        depth="Sincronização Híbrida Web/Local",
        recurrence_summary=[],
        assertions=unified_assertions,
    )
    battery = database.get_battery(battery_id)

    return {
        "folder_label": folder_label,
        "processed_files_count": len(processed_files),
        "duplicates_skipped_count": duplicates_skipped,
        "processed_files": processed_files,
        "battery_id": battery_id,
        "battery": battery,
    }


def build_hotmart_customer_package(
    output_zip_path: Path,
    top_level_pages_url: str = DEFAULT_TOP_LEVEL_PAGES_URL,
    universal_pyz_path: Optional[Path] = None,
    polyglot_cmd_path: Optional[Path] = None,
) -> Path:
    """
    Gera o pacote comercial `.zip` pronto para upload na área de membros da Hotmart / Kiwify / Eduzz.
    O pacote contém:
      1. `CebraspeLab-Universal.pyz` (Executável único universal Windows / Linux / macOS)
      2. `CebraspeLab-Universal.cmd` (Lançador poliglota de 1 clique)
      3. `Abrir_Interface_Web_CebraspeLab.html` (Atalho de 1 clique que abre a URL de alto nível do
         GitHub Pages já conectada ao banco local `http://127.0.0.1:8000` do comprador)
      4. `LEIA_ME_ACESSO_ALUNO.txt` (Instruções rápidas para o comprador)
    """
    root_dir = Path(__file__).resolve().parent.parent
    pyz_file = universal_pyz_path or (root_dir / "dist" / "CebraspeLab-Universal.pyz")
    cmd_file = polyglot_cmd_path or (root_dir / "CebraspeLab-Universal.cmd")

    output_zip_path.parent.mkdir(parents=True, exist_ok=True)
    clean_url = top_level_pages_url.strip().rstrip("/")

    web_shortcut_html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="refresh" content="2;url={clean_url}?local_api=http://127.0.0.1:8000" />
  <title>CebraspeLab — Abrindo Interface Web + Banco Local</title>
  <style>
    body {{ font-family: system-ui, sans-serif; background: #090d16; color: #f8fafc; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
    .card {{ max-width: 540px; padding: 32px; border-radius: 16px; background: #111827; border: 1px solid #374151; text-align: center; }}
    a {{ display: inline-block; margin-top: 16px; padding: 12px 24px; border-radius: 10px; background: #4f46e5; color: white; text-decoration: none; font-weight: bold; }}
  </style>
</head>
<body>
  <div class="card">
    <h2>🎯 CebraspeLab — Plataforma Híbrida</h2>
    <p>Certifique-se de que o Agente Local (<strong>CebraspeLab-Universal.cmd</strong>) está aberto no seu computador para conectar seu banco de dados e suas pastas locais.</p>
    <p>Redirecionando para a interface principal...</p>
    <a href="{clean_url}?local_api=http://127.0.0.1:8000">Acessar Interface Web Agora ({clean_url})</a>
    <br/>
    <a href="http://127.0.0.1:8000" style="background:#059669; margin-top:10px;">Ou Abrir Direto no Servidor Local (http://127.0.0.1:8000)</a>
  </div>
</body>
</html>
"""

    buyer_readme = f"""================================================================================
  BEM-VINDO AO CEBRASPELAB — GUIA RÁPIDO DO ALUNO (EDIÇÃO COMPLETA)
================================================================================

Você tem DUAS OPÇÕES para usar o CebraspeLab no seu computador (Windows, Linux ou Mac):

OPÇÃO 1: USAR PELA INTERFACE WEB OFICIAL + BANCO LOCAL NO SEU PC
--------------------------------------------------------------------------------
1. Dê dois cliques em "CebraspeLab-Universal.cmd" (no Windows) ou execute
   "sh ./CebraspeLab-Universal.cmd" (no Linux/Mac) para ligar o seu Banco Local.
2. Acesse a interface online de alto nível:
   {clean_url}
   (ou clique em "Abrir_Interface_Web_CebraspeLab.html").
3. Pronto! A interface online vai se conectar automaticamente ao banco SQL+NoSQL
   do seu próprio computador (127.0.0.1:8000), permitindo escolher suas pastas
   locais (Downloads, Documentos, C:, D:) e nuvem (Google Drive / Dropbox)
   com total privacidade!

OPÇÃO 2: USAR 100% LOCAL (MESMO SEM INTERNET)
--------------------------------------------------------------------------------
1. Dê dois cliques em "CebraspeLab-Universal.cmd".
2. O navegador abrirá automaticamente em http://127.0.0.1:8000 com toda a
   plataforma funcionando direto na sua máquina!

COMO ATIVAR SEU CÓDIGO DE COMPRA (HOTMART):
--------------------------------------------------------------------------------
No topo da plataforma, clique no botão "Ponte PC Local / Licença" e informe o
código da sua transação (ex: HP123456789) para registrar sua licença vitalícia.
================================================================================
"""

    with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if pyz_file.exists():
            zf.write(pyz_file, arcname="CebraspeLab-Universal.pyz")
        if cmd_file.exists():
            zf.write(cmd_file, arcname="CebraspeLab-Universal.cmd")
        zf.writestr("Abrir_Interface_Web_CebraspeLab.html", web_shortcut_html)
        zf.writestr("LEIA_ME_ACESSO_ALUNO.txt", buyer_readme)

    return output_zip_path
