"""
Módulo de Armazenamento Híbrido SQL + NoSQL (`storage_manager.py`).

Combina:
1. **Camada Relacional/Binária SQL (SQLite + Vault em Disco):**
   - Armazena de forma persistente os arquivos PDF originais enviados pelo usuário (metadados, hash SHA-256,
     BLOB binário no banco SQL e cópia física em `data/pdf_vault/`), garantindo que o PDF nunca seja perdido
     e possa ser baixado, visualizado ou reprocessado a qualquer momento sem novo upload.
2. **Camada NoSQL Orientada a Documentos (`NoSQLDocumentStore` em JSON estruturado):**
   - Armazena documentos hierárquicos não-relacionais em coleções (`pdf_knowledge_trees`,
     `user_weakness_profiles`, `study_summaries`, `discursive_evaluations`), permitindo consultas rápidas
     sobre a árvore de tópicos, subtópicos e períodos de cada PDF armazenado.
"""

import hashlib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import database

VAULT_DIR = database.DATA_DIR / "pdf_vault"
NOSQL_PATH = database.DATA_DIR / "nosql_document_store.json"


def _ensure_storage_dirs() -> None:
    database.DATA_DIR.mkdir(parents=True, exist_ok=True)
    VAULT_DIR.mkdir(parents=True, exist_ok=True)


class NoSQLDocumentStore:
    """
    Banco NoSQL local orientado a documentos (estilo MongoDB / TinyDB) com persistência
    atômica em arquivo JSON e suporte a coleções dinâmicas.
    """

    def __init__(self, file_path: Optional[Path] = None) -> None:
        self.file_path = file_path or NOSQL_PATH
        self._ensure_file()

    def _ensure_file(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self._write_raw(
                {
                    "pdf_knowledge_trees": {},
                    "user_weakness_profiles": {},
                    "study_summaries": {},
                    "discursive_evaluations": {},
                }
            )

    def _read_raw(self) -> Dict[str, Dict[str, Any]]:
        self._ensure_file()
        try:
            return json.loads(self.file_path.read_text(encoding="utf-8"))
        except Exception:
            return {
                "pdf_knowledge_trees": {},
                "user_weakness_profiles": {},
                "study_summaries": {},
                "discursive_evaluations": {},
            }

    def _write_raw(self, data: Dict[str, Dict[str, Any]]) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def upsert_document(self, collection: str, doc_id: str, document: Dict[str, Any]) -> Dict[str, Any]:
        store = self._read_raw()
        if collection not in store:
            store[collection] = {}
        now = datetime.now().isoformat()
        existing = store[collection].get(str(doc_id), {})
        merged = {
            **existing,
            **document,
            "_id": str(doc_id),
            "_updated_at": now,
            "_created_at": existing.get("_created_at", now),
        }
        store[collection][str(doc_id)] = merged
        self._write_raw(store)
        return merged

    def find_by_id(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        store = self._read_raw()
        return store.get(collection, {}).get(str(doc_id))

    def find_many(
        self,
        collection: str,
        predicate: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ) -> List[Dict[str, Any]]:
        store = self._read_raw()
        docs = list(store.get(collection, {}).values())
        if predicate:
            docs = [d for d in docs if predicate(d)]
        return docs

    def delete_by_id(self, collection: str, doc_id: str) -> bool:
        store = self._read_raw()
        col = store.get(collection, {})
        if str(doc_id) in col:
            del col[str(doc_id)]
            self._write_raw(store)
            return True
        return False


def init_storage_tables() -> None:
    """Inicializa as tabelas SQL dedicadas ao armazenamento binário de PDFs e questões discursivas."""
    _ensure_storage_dirs()
    conn = database.get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS stored_pdf_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER,
            filename TEXT NOT NULL,
            file_role TEXT NOT NULL DEFAULT 'study_pdf',
            mime_type TEXT NOT NULL DEFAULT 'application/pdf',
            file_size INTEGER NOT NULL DEFAULT 0,
            sha256_hash TEXT NOT NULL,
            vault_filename TEXT NOT NULL,
            file_blob BLOB NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (material_id) REFERENCES study_materials(id) ON DELETE CASCADE
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS discursive_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER,
            subject TEXT NOT NULL,
            subtopic TEXT NOT NULL,
            target_concept TEXT NOT NULL,
            trap_type TEXT NOT NULL DEFAULT '',
            prompt_text TEXT NOT NULL,
            max_lines INTEGER NOT NULL DEFAULT 5,
            expected_key_points_json TEXT NOT NULL DEFAULT '[]',
            pdf_reference_quote TEXT NOT NULL DEFAULT '',
            pdf_page TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (material_id) REFERENCES study_materials(id) ON DELETE SET NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS discursive_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            material_id INTEGER,
            student_text TEXT NOT NULL,
            lines_used INTEGER NOT NULL DEFAULT 1,
            char_count INTEGER NOT NULL DEFAULT 0,
            score REAL NOT NULL DEFAULT 0.0,
            feedback_text TEXT NOT NULL DEFAULT '',
            covered_points_json TEXT NOT NULL DEFAULT '[]',
            missing_points_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            FOREIGN KEY (question_id) REFERENCES discursive_questions(id) ON DELETE CASCADE
        )
        """
    )

    conn.commit()
    conn.close()


def store_uploaded_file(
    file_bytes: bytes,
    filename: str,
    material_id: Optional[int] = None,
    file_role: str = "study_pdf",
    mime_type: str = "application/pdf",
) -> Dict[str, Any]:
    """
    Persiste o arquivo PDF enviado tanto no banco SQL (BLOB + metadados) quanto no Vault físico,
    retornando os metadados completos do arquivo armazenado.
    """
    init_storage_tables()
    _ensure_storage_dirs()

    sha256 = hashlib.sha256(file_bytes).hexdigest()
    safe_name = re.sub(r"[^\w\.\-]", "_", filename or "documento.pdf")
    vault_filename = f"{sha256[:12]}_{safe_name}"
    vault_file_path = VAULT_DIR / vault_filename
    vault_file_path.write_bytes(file_bytes)

    now = datetime.now().isoformat()
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO stored_pdf_files (
            material_id, filename, file_role, mime_type, file_size, sha256_hash, vault_filename, file_blob, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            material_id,
            filename,
            file_role,
            mime_type,
            len(file_bytes),
            sha256,
            vault_filename,
            sqlite3.Binary(file_bytes),
            now,
        ),
    )
    file_id = int(cur.lastrowid)
    conn.commit()
    conn.close()

    return {
        "file_id": file_id,
        "material_id": material_id,
        "filename": filename,
        "file_role": file_role,
        "mime_type": mime_type,
        "file_size": len(file_bytes),
        "sha256_hash": sha256,
        "vault_filename": vault_filename,
        "created_at": now,
    }


def list_stored_files(material_id: Optional[int] = None) -> List[Dict[str, Any]]:
    init_storage_tables()
    conn = database.get_connection()
    if material_id is not None:
        rows = conn.execute(
            """
            SELECT id, material_id, filename, file_role, mime_type, file_size, sha256_hash, vault_filename, created_at
            FROM stored_pdf_files WHERE material_id = ? ORDER BY id DESC
            """,
            (material_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, material_id, filename, file_role, mime_type, file_size, sha256_hash, vault_filename, created_at
            FROM stored_pdf_files ORDER BY id DESC
            """
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stored_file_With_bytes(file_id: int) -> Optional[Dict[str, Any]]:
    init_storage_tables()
    conn = database.get_connection()
    row = conn.execute("SELECT * FROM stored_pdf_files WHERE id = ?", (file_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    blob = d.pop("file_blob", None)
    vault_path = VAULT_DIR / d["vault_filename"]
    if blob is not None:
        d["bytes"] = bytes(blob)
    elif vault_path.exists():
        d["bytes"] = vault_path.read_bytes()
    else:
        d["bytes"] = b""
    return d


def save_material_knowledge_tree_nosql(
    material_id: int,
    title: str,
    subject: str,
    area: str,
    parsed_topics: List[Dict[str, Any]],
    recurrence_map: List[Dict[str, Any]],
    stored_file_ids: List[int],
    nosql_store: Optional[NoSQLDocumentStore] = None,
) -> Dict[str, Any]:
    """
    Salva no banco NoSQL a árvore completa de conhecimento extraída do PDF (Tópicos, Subtópicos,
    Períodos, Marcadores Normativos e Vínculos com os arquivos binários do SQL).
    """
    store = nosql_store or NoSQLDocumentStore()
    doc = {
        "material_id": material_id,
        "title": title,
        "subject": subject,
        "area": area,
        "stored_file_ids": stored_file_ids,
        "parsed_topics": parsed_topics,
        "recurrence_map": recurrence_map,
        "total_subtopics": len(parsed_topics),
        "total_periods": sum(t.get("periods_count", len(t.get("periods", []))) for t in parsed_topics),
    }
    return store.upsert_document("pdf_knowledge_trees", str(material_id), doc)


def get_material_knowledge_tree_nosql(
    material_id: int,
    nosql_store: Optional[NoSQLDocumentStore] = None,
) -> Optional[Dict[str, Any]]:
    store = nosql_store or NoSQLDocumentStore()
    return store.find_by_id("pdf_knowledge_trees", str(material_id))

