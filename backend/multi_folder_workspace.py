"""
Módulo de Seleção, Gerenciamento e Sincronização de Múltiplas Pastas de Estudo (`multi_folder_workspace.py`).

Permite que o usuário (inclusive usuários leigos/não-técnicos):
1. Navegue visualmente pelas pastas do seu computador (`browse_local_folders`) ou abra a janela nativa do
   sistema operacional (`pick_folder_native_dialog`) para escolher **1 ou mais pastas** com arquivos de estudo;
2. Agrupe múltiplas pastas simultaneamente em um **Workspace Multi-Pasta** (`multi_folder_workspaces`) ou
   processe uma lista avulsa de várias pastas de uma só vez (`scan_and_sync_multiple_folders`);
3. Realize **deduplicação automática por hash SHA-256** entre pastas diferentes (evitando processar duas vezes
   um mesmo PDF que esteja salvo tanto em `Downloads` quanto em `Documentos`);
4. Extraia e relacione os conceitos (`Tópico -> Subtópico -> Conceito -> Subconceito`) de todas as pastas
   selecionadas e gere uma **Bateria Unificada Multi-Pasta** (estudo intercalado) além das baterias por arquivo.
"""

import json
import os
import string
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import data_connectors
import database
from storage_manager import NoSQLDocumentStore


def init_multi_folder_tables() -> None:
    """Cria a tabela SQL para armazenar conjuntos/workspaces de múltiplas pastas escolhidas pelo usuário."""
    data_connectors.init_connectors_tables()
    conn = database.get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS multi_folder_workspaces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            subject_hint TEXT NOT NULL DEFAULT 'Multidisciplinar',
            area_hint TEXT NOT NULL DEFAULT 'Geral',
            folders_json TEXT NOT NULL DEFAULT '[]',
            connection_ids_json TEXT NOT NULL DEFAULT '[]',
            recursive_scan INTEGER NOT NULL DEFAULT 1,
            auto_generate_questions INTEGER NOT NULL DEFAULT 1,
            unified_battery_id INTEGER,
            total_files_found INTEGER NOT NULL DEFAULT 0,
            last_synced_at TEXT,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()


def list_available_drives_and_quick_folders() -> Dict[str, Any]:
    """
    Lista unidades de disco disponíveis no computador (ex: C:\\, D:\\) e pastas rápidas
    (Downloads, Documentos, Área de Trabalho) para facilitar a escolha visual por usuários não-técnicos.
    """
    drives: List[Dict[str, str]] = []
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive_path = f"{letter}:\\"
            if os.path.exists(drive_path):
                drives.append({"label": f"Disco Local ({letter}:)", "path": drive_path})
    else:
        drives.append({"label": "Raiz do Sistema (/)", "path": "/"})

    quick_folders = data_connectors.get_default_local_directories()
    home_dir = str(Path.home())

    return {
        "home_directory": home_dir,
        "drives": drives,
        "quick_folders": quick_folders,
    }


def browse_local_folders(current_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Navegador visual de pastas locais: retorna o diretório atual, a pasta pai (`parent_path`),
    as subpastas imediatas (`subfolders`) e a contagem de arquivos de estudo suportados na pasta atual,
    permitindo que o usuário escolha múltiplas pastas clicando na interface sem precisar digitar caminhos.
    """
    target_str = (current_path or "").strip()
    if not target_str:
        target = Path.home()
    else:
        expanded = os.path.expandvars(os.path.expanduser(target_str))
        target = Path(expanded)

    if not target.exists() or not target.is_dir():
        raise ValueError(f"A pasta '{target_str}' não existe ou não pôde ser aberta.")

    resolved = target.resolve()
    parent_path = str(resolved.parent) if resolved.parent != resolved else None

    subfolders: List[Dict[str, Any]] = []
    study_files_in_current: List[Dict[str, Any]] = []

    try:
        for entry in sorted(resolved.iterdir(), key=lambda e: e.name.lower()):
            name_lower = entry.name.lower()
            if entry.name.startswith(".") or name_lower in data_connectors.IGNORED_DIR_NAMES:
                continue
            try:
                if entry.is_dir():
                    subfolders.append(
                        {
                            "name": entry.name,
                            "path": str(entry.resolve()),
                        }
                    )
                elif entry.is_file():
                    ext = entry.suffix.lower()
                    if ext in data_connectors.SUPPORTED_STUDY_EXTENSIONS:
                        study_files_in_current.append(
                            {
                                "name": entry.name,
                                "ext": ext,
                                "size_bytes": entry.stat().st_size,
                            }
                        )
            except (PermissionError, OSError):
                continue
    except PermissionError:
        pass

    return {
        "current_path": str(resolved),
        "current_name": resolved.name or str(resolved),
        "parent_path": parent_path,
        "subfolders": subfolders[:150],
        "study_files_in_current": study_files_in_current[:100],
        "study_files_count": len(study_files_in_current),
    }


def pick_folder_native_dialog(initial_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Abre a janela nativa do Windows/OS (Explorer) para o usuário escolher uma pasta clicando normalmente.
    Retorna `{"selected": True, "path": "..."}` ou `{"selected": False, "path": ""}` se cancelado.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        start_dir = initial_dir if (initial_dir and os.path.isdir(initial_dir)) else str(Path.home())
        chosen = filedialog.askdirectory(
            initialdir=start_dir,
            title="CebraspeLab — Escolha uma pasta com seus arquivos de estudo",
        )
        root.destroy()
        if chosen:
            norm = str(Path(chosen).resolve())
            return {"selected": True, "path": norm}
        return {"selected": False, "path": ""}
    except Exception as e:
        return {"selected": False, "path": "", "error": str(e)}


def _normalize_and_validate_folder_entries(
    folders: List[Any],
    default_subject: str = "Multidisciplinar",
) -> List[Dict[str, str]]:
    """
    Aceita uma lista de strings de caminhos `["C:\\Pasta1", "D:\\Pasta2"]` ou objetos
    `[{"path": "C:\\Pasta1", "label": "Direito Constitucional", "subject": "Direito Constitucional"}]`,
    valida se os diretórios existem e remove caminhos duplicados mantendo a ordem.
    """
    if not folders:
        raise ValueError("Selecione pelo menos uma pasta com arquivos de estudo.")

    normalized: List[Dict[str, str]] = []
    seen_paths = set()

    for item in folders:
        if isinstance(item, str):
            raw_path = item.strip()
            label = ""
            subject = default_subject
        elif isinstance(item, dict):
            raw_path = str(item.get("path") or item.get("folder_path") or "").strip()
            label = str(item.get("label") or item.get("name") or "").strip()
            subject = str(item.get("subject") or default_subject).strip() or default_subject
        else:
            continue

        if not raw_path:
            continue

        expanded = os.path.expandvars(os.path.expanduser(raw_path))
        p = Path(expanded)
        if not p.exists() or not p.is_dir():
            raise ValueError(f"A pasta informada não existe ou não é um diretório válido: '{raw_path}'")

        resolved_str = str(p.resolve())
        norm_key = resolved_str.lower() if os.name == "nt" else resolved_str
        if norm_key in seen_paths:
            continue
        seen_paths.add(norm_key)

        normalized.append(
            {
                "path": resolved_str,
                "label": label or p.name or resolved_str,
                "subject": subject,
            }
        )

    if not normalized:
        raise ValueError("Nenhuma pasta válida foi fornecida.")

    return normalized


def create_or_update_multi_folder_workspace(
    name: str,
    folders: List[Any],
    subject_hint: str = "Multidisciplinar",
    area_hint: str = "Geral",
    recursive_scan: bool = True,
    auto_generate_questions: bool = True,
    workspace_id: Optional[int] = None,
    nosql_store: Optional[NoSQLDocumentStore] = None,
) -> Dict[str, Any]:
    """
    Salva ou atualiza um conjunto de múltiplas pastas (`multi_folder_workspaces`) e garante que cada
    pasta do conjunto possua um conector correspondente em `storage_connections`.
    """
    init_multi_folder_tables()
    if not name.strip():
        raise ValueError("Informe um nome para o conjunto de pastas de estudo.")

    validated_folders = _normalize_and_validate_folder_entries(folders, default_subject=subject_hint)
    now = datetime.now().isoformat()

    # Criar ou reutilizar uma conexão individual em `storage_connections` para cada pasta escolhida
    conn = database.get_connection()
    connection_ids: List[int] = []

    for f_entry in validated_folders:
        f_path = f_entry["path"]
        existing_conn = conn.execute(
            """
            SELECT id FROM storage_connections
            WHERE provider_type IN ('local_fs', 'network_share')
              AND lower(target_path_or_folder_id) = lower(?)
            """,
            (f_path,),
        ).fetchone()

        if existing_conn:
            cid = int(existing_conn["id"])
        else:
            provider = "network_share" if f_path.startswith("\\\\") else "local_fs"
            created_conn = data_connectors.create_or_update_connection(
                name=f"[{name.strip()}] {f_entry['label']}",
                provider_type=provider,
                target_path_or_folder_id=f_path,
                subject_hint=f_entry["subject"] or subject_hint,
                area_hint=area_hint,
                recursive_scan=recursive_scan,
                auto_generate_questions=auto_generate_questions,
                nosql_store=nosql_store,
            )
            cid = int(created_conn["id"])
        connection_ids.append(cid)

    cur = conn.cursor()
    if workspace_id is not None:
        existing_ws = conn.execute(
            "SELECT * FROM multi_folder_workspaces WHERE id = ?", (workspace_id,)
        ).fetchone()
        if not existing_ws:
            conn.close()
            raise ValueError(f"Workspace de múltiplas pastas #{workspace_id} não encontrado.")

        cur.execute(
            """
            UPDATE multi_folder_workspaces
            SET name = ?, subject_hint = ?, area_hint = ?, folders_json = ?,
                connection_ids_json = ?, recursive_scan = ?, auto_generate_questions = ?
            WHERE id = ?
            """,
            (
                name.strip(),
                subject_hint.strip() or "Multidisciplinar",
                area_hint.strip() or "Geral",
                json.dumps(validated_folders, ensure_ascii=False),
                json.dumps(connection_ids),
                1 if recursive_scan else 0,
                1 if auto_generate_questions else 0,
                workspace_id,
            ),
        )
        ws_id = workspace_id
    else:
        cur.execute(
            """
            INSERT INTO multi_folder_workspaces (
                name, subject_hint, area_hint, folders_json, connection_ids_json,
                recursive_scan, auto_generate_questions, unified_battery_id,
                total_files_found, last_synced_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 0, NULL, ?)
            """,
            (
                name.strip(),
                subject_hint.strip() or "Multidisciplinar",
                area_hint.strip() or "Geral",
                json.dumps(validated_folders, ensure_ascii=False),
                json.dumps(connection_ids),
                1 if recursive_scan else 0,
                1 if auto_generate_questions else 0,
                now,
            ),
        )
        ws_id = int(cur.lastrowid)

    conn.commit()
    row = conn.execute("SELECT * FROM multi_folder_workspaces WHERE id = ?", (ws_id,)).fetchone()
    conn.close()

    formatted = _format_workspace_row(dict(row))
    store = nosql_store or NoSQLDocumentStore()
    store.upsert_document("multi_folder_workspaces", str(ws_id), formatted)
    return formatted


def add_folders_to_workspace(
    workspace_id: int,
    new_folders: List[Any],
    nosql_store: Optional[NoSQLDocumentStore] = None,
) -> Dict[str, Any]:
    """Adiciona uma ou mais pastas a um Workspace Multi-Pasta já existente."""
    init_multi_folder_tables()
    conn = database.get_connection()
    row = conn.execute(
        "SELECT * FROM multi_folder_workspaces WHERE id = ?", (workspace_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise ValueError(f"Workspace #{workspace_id} não encontrado.")

    d = dict(row)
    current_folders = json.loads(d.get("folders_json") or "[]")
    combined = current_folders + list(new_folders)
    return create_or_update_multi_folder_workspace(
        name=d["name"],
        folders=combined,
        subject_hint=d["subject_hint"],
        area_hint=d["area_hint"],
        recursive_scan=bool(d.get("recursive_scan", 1)),
        auto_generate_questions=bool(d.get("auto_generate_questions", 1)),
        workspace_id=workspace_id,
        nosql_store=nosql_store,
    )


def remove_folder_from_workspace(
    workspace_id: int,
    folder_path_to_remove: str,
    nosql_store: Optional[NoSQLDocumentStore] = None,
) -> Dict[str, Any]:
    """Remove uma pasta específica de um Workspace Multi-Pasta."""
    init_multi_folder_tables()
    conn = database.get_connection()
    row = conn.execute(
        "SELECT * FROM multi_folder_workspaces WHERE id = ?", (workspace_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise ValueError(f"Workspace #{workspace_id} não encontrado.")

    d = dict(row)
    current_folders = json.loads(d.get("folders_json") or "[]")
    target_norm = str(Path(os.path.expanduser(folder_path_to_remove)).resolve()).lower()
    remaining = [
        f for f in current_folders if str(Path(f["path"]).resolve()).lower() != target_norm
    ]
    if not remaining:
        raise ValueError("O conjunto deve manter pelo menos 1 pasta ativa (ou exclua o conjunto inteiro).")

    return create_or_update_multi_folder_workspace(
        name=d["name"],
        folders=remaining,
        subject_hint=d["subject_hint"],
        area_hint=d["area_hint"],
        recursive_scan=bool(d.get("recursive_scan", 1)),
        auto_generate_questions=bool(d.get("auto_generate_questions", 1)),
        workspace_id=workspace_id,
        nosql_store=nosql_store,
    )


def list_multi_folder_workspaces() -> List[Dict[str, Any]]:
    """Lista todos os conjuntos de múltiplas pastas salvos pelo usuário."""
    init_multi_folder_tables()
    conn = database.get_connection()
    rows = conn.execute("SELECT * FROM multi_folder_workspaces ORDER BY id DESC").fetchall()
    conn.close()
    return [_format_workspace_row(dict(r)) for r in rows]


def delete_multi_folder_workspace(
    workspace_id: int, nosql_store: Optional[NoSQLDocumentStore] = None
) -> bool:
    """Remove um workspace de múltiplas pastas."""
    init_multi_folder_tables()
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM multi_folder_workspaces WHERE id = ?", (workspace_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()

    store = nosql_store or NoSQLDocumentStore()
    store.delete_by_id("multi_folder_workspaces", str(workspace_id))
    return deleted


def _format_workspace_row(d: Dict[str, Any]) -> Dict[str, Any]:
    folders = json.loads(d.get("folders_json") or "[]")
    conn_ids = json.loads(d.get("connection_ids_json") or "[]")
    return {
        "id": d["id"],
        "name": d["name"],
        "subject_hint": d["subject_hint"],
        "area_hint": d["area_hint"],
        "folders": folders,
        "folders_count": len(folders),
        "connection_ids": conn_ids,
        "recursive_scan": bool(d.get("recursive_scan", 1)),
        "auto_generate_questions": bool(d.get("auto_generate_questions", 1)),
        "unified_battery_id": d.get("unified_battery_id"),
        "total_files_found": d.get("total_files_found", 0),
        "last_synced_at": d.get("last_synced_at"),
        "created_at": d["created_at"],
    }


def scan_and_sync_multiple_folders(
    workspace_id: Optional[int] = None,
    folders: Optional[List[Any]] = None,
    workspace_name: str = "Minhas Pastas de Estudo",
    subject_hint: str = "Multidisciplinar",
    area_hint: str = "Geral",
    questions_per_file: int = 6,
    create_unified_battery: bool = True,
    api_key: str = "",
    model_name: str = "gemini-2.5-flash",
    nosql_store: Optional[NoSQLDocumentStore] = None,
) -> Dict[str, Any]:
    """
    Escaneia e sincroniza **múltiplas pastas de estudo** de uma só vez:
    1. Se `workspace_id` for informado, usa as pastas daquele workspace; se `folders` for informado,
       cria/atualiza o workspace automaticamente;
    2. Varre cada pasta selecionada em busca de arquivos `.pdf`, `.json`, `.csv`, `.xml`, `.txt`, `.md`;
    3. Deduplica arquivos idênticos entre pastas diferentes pelo hash `SHA-256`;
    4. Ingere os arquivos novos/alterados, cria os relacionamentos conceituais e gera uma
       **Bateria Unificada Multi-Pasta (Estudo Intercalado)** reunindo as questões de todas as pastas!
    """
    init_multi_folder_tables()
    store = nosql_store or NoSQLDocumentStore()

    if workspace_id is not None:
        conn = database.get_connection()
        row = conn.execute(
            "SELECT * FROM multi_folder_workspaces WHERE id = ?", (workspace_id,)
        ).fetchone()
        conn.close()
        if not row:
            raise ValueError(f"Workspace de múltiplas pastas #{workspace_id} não encontrado.")
        ws = _format_workspace_row(dict(row))
    else:
        if not folders:
            raise ValueError("Informe `workspace_id` ou uma lista de `folders` para escanear.")
        ws = create_or_update_multi_folder_workspace(
            name=workspace_name,
            folders=folders,
            subject_hint=subject_hint,
            area_hint=area_hint,
            nosql_store=store,
        )

    now_iso = datetime.now().isoformat()
    seen_sha256: set[str] = set()
    duplicates_skipped_count = 0
    folder_reports: List[Dict[str, Any]] = []
    all_discovered_files: List[Dict[str, Any]] = []
    all_generated_batteries: List[Dict[str, Any]] = []
    unified_assertions: List[Dict[str, Any]] = []
    unified_recurrence: List[Dict[str, Any]] = []
    first_material_id: Optional[int] = None

    for idx, f_entry in enumerate(ws["folders"]):
        cid = ws["connection_ids"][idx]
        folder_path = f_entry["path"]
        folder_label = f_entry.get("label") or Path(folder_path).name

        # Varredura física da pasta para identificar duplicatas inter-pastas antes de ingerir
        raw_files = data_connectors._scan_filesystem_directory(
            folder_path, recursive=ws["recursive_scan"]
        )
        unique_in_folder = 0
        dup_in_folder = 0

        db_conn = database.get_connection()
        cur = db_conn.cursor()
        cur.execute(
            "UPDATE storage_connections SET last_connected_at = ? WHERE id = ?",
            (now_iso, cid),
        )

        to_ingest: List[tuple[int, bytes, bool]] = []
        for item in raw_files:
            sha = item["sha256_hash"]
            if sha in seen_sha256:
                dup_in_folder += 1
                duplicates_skipped_count += 1
                continue
            seen_sha256.add(sha)
            unique_in_folder += 1

            existing = db_conn.execute(
                """
                SELECT id, sha256_hash, battery_id FROM discovered_study_files
                WHERE connection_id = ? AND file_path_or_remote_id = ?
                """,
                (cid, item["file_path_or_remote_id"]),
            ).fetchone()

            if existing:
                disc_id = int(existing["id"])
                needs_reingest = (existing["sha256_hash"] != sha) or (
                    existing["battery_id"] is None
                )
                cur.execute(
                    """
                    UPDATE discovered_study_files
                    SET file_size = ?, sha256_hash = ?, last_synced_at = ?
                    WHERE id = ?
                    """,
                    (item["file_size"], sha, now_iso, disc_id),
                )
                to_ingest.append((disc_id, item["raw_bytes"], needs_reingest))
            else:
                cur.execute(
                    """
                    INSERT INTO discovered_study_files (
                        connection_id, provider_type, file_name, file_path_or_remote_id,
                        file_ext, file_size, sha256_hash, status, discovered_at, last_synced_at
                    ) VALUES (?, 'local_fs', ?, ?, ?, ?, ?, 'discovered', ?, ?)
                    """,
                    (
                        cid,
                        item["file_name"],
                        item["file_path_or_remote_id"],
                        item["file_ext"],
                        item["file_size"],
                        sha,
                        now_iso,
                        now_iso,
                    ),
                )
                disc_id = int(cur.lastrowid)
                to_ingest.append((disc_id, item["raw_bytes"], True))

        db_conn.commit()
        db_conn.close()

        ingested_in_folder = 0
        for disc_id, raw_bytes, needs_ingest in to_ingest:
            if needs_ingest and ws["auto_generate_questions"]:
                res = data_connectors.ingest_and_generate_questions_from_discovered_file(
                    discovered_file_id=disc_id,
                    raw_bytes=raw_bytes,
                    questions_count=questions_per_file,
                    api_key=api_key,
                    model_name=model_name,
                    nosql_store=store,
                )
                ingested_in_folder += 1
                bat = res.get("battery")
                if bat:
                    all_generated_batteries.append(bat)
                    if first_material_id is None:
                        first_material_id = bat.get("material_id")
                    for a in bat.get("assertions", []):
                        unified_assertions.append(a)
                    for r_item in bat.get("recurrence_summary", []):
                        unified_recurrence.append(r_item)
            else:
                # Carregar bateria já existente deste arquivo para incluir na bateria unificada
                files_rows = data_connectors.list_discovered_files(connection_id=cid)
                matched = next((f for f in files_rows if f["id"] == disc_id), None)
                if matched and matched.get("battery_id"):
                    existing_bat = database.get_battery(int(matched["battery_id"]))
                    if existing_bat:
                        if first_material_id is None:
                            first_material_id = existing_bat.get("material_id")
                        for a in existing_bat.get("assertions", []):
                            unified_assertions.append(a)

        folder_files = data_connectors.list_discovered_files(connection_id=cid)
        all_discovered_files.extend(folder_files)
        folder_reports.append(
            {
                "folder_path": folder_path,
                "folder_label": folder_label,
                "connection_id": cid,
                "unique_files_count": unique_in_folder,
                "duplicates_skipped_in_folder": dup_in_folder,
                "newly_ingested_count": ingested_in_folder,
            }
        )

    unified_battery: Optional[Dict[str, Any]] = None
    unified_battery_id: Optional[int] = ws.get("unified_battery_id")

    if create_unified_battery and unified_assertions:
        folder_names = ", ".join(f["label"] for f in ws["folders"][:3])
        unified_title = (
            f"Caderno Multi-Pasta ({len(ws['folders'])} pastas: {folder_names}) — "
            f"{len(unified_assertions)} Questões"
        )
        unified_battery_id = database.save_question_battery(
            material_id=first_material_id,
            title=unified_title,
            subject=ws["subject_hint"],
            area=ws["area_hint"],
            depth=f"Estudo Intercalado Multi-Pasta ({len(ws['folders'])} diretórios)",
            recurrence_summary=unified_recurrence[:15],
            assertions=unified_assertions,
        )
        unified_battery = database.get_battery(unified_battery_id)

    conn_upd = database.get_connection()
    conn_upd.execute(
        """
        UPDATE multi_folder_workspaces
        SET unified_battery_id = ?, total_files_found = ?, last_synced_at = ?
        WHERE id = ?
        """,
        (unified_battery_id, len(all_discovered_files), now_iso, ws["id"]),
    )
    updated_ws_row = conn_upd.execute(
        "SELECT * FROM multi_folder_workspaces WHERE id = ?", (ws["id"],)
    ).fetchone()
    conn_upd.commit()
    conn_upd.close()

    updated_ws = _format_workspace_row(dict(updated_ws_row))
    store.upsert_document("multi_folder_workspaces", str(ws["id"]), updated_ws)

    return {
        "workspace": updated_ws,
        "folders_scanned_count": len(ws["folders"]),
        "total_unique_files": len(all_discovered_files),
        "duplicates_skipped_count": duplicates_skipped_count,
        "folder_reports": folder_reports,
        "discovered_files": all_discovered_files,
        "unified_battery_id": unified_battery_id,
        "unified_battery": unified_battery,
        "individual_batteries": all_generated_batteries,
    }

