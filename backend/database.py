import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_env_data_dir = os.environ.get("CEBRASPELAB_DATA_DIR")
if _env_data_dir:
    DATA_DIR = Path(_env_data_dir)
elif Path(__file__).parent.is_file():
    # Quando executado a partir de um arquivo único .pyz (zipapp universal)
    DATA_DIR = Path(__file__).parent.parent / "cebraspelab_data"
else:
    DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "cebraspe_generator.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS study_materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            subject TEXT NOT NULL,
            area TEXT NOT NULL DEFAULT 'Geral',
            total_pages INTEGER NOT NULL DEFAULT 0,
            pages_json TEXT NOT NULL,
            extracted_questions_json TEXT NOT NULL DEFAULT '[]',
            recurrence_map_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS real_questions_bank (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER,
            subject TEXT NOT NULL,
            subtopic TEXT NOT NULL DEFAULT 'Geral',
            exam_info TEXT NOT NULL DEFAULT 'Cebraspe',
            statement TEXT NOT NULL,
            answer TEXT NOT NULL DEFAULT '',
            commentary TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (material_id) REFERENCES study_materials(id) ON DELETE SET NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS question_batteries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER,
            title TEXT NOT NULL,
            subject TEXT NOT NULL,
            area TEXT NOT NULL DEFAULT 'Geral',
            depth TEXT NOT NULL DEFAULT 'Misto Padrão Cebraspe',
            total_questions INTEGER NOT NULL DEFAULT 0,
            recurrence_summary_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            FOREIGN KEY (material_id) REFERENCES study_materials(id) ON DELETE SET NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS assertions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            battery_id INTEGER NOT NULL,
            material_id INTEGER,
            item_number INTEGER NOT NULL,
            subtopic TEXT NOT NULL,
            recurrence_level TEXT NOT NULL DEFAULT 'Alta',
            command_text TEXT NOT NULL,
            statement TEXT NOT NULL,
            answer TEXT NOT NULL,
            explanation TEXT NOT NULL,
            pdf_quote TEXT NOT NULL DEFAULT '',
            pdf_page TEXT NOT NULL DEFAULT '',
            trap_type TEXT NOT NULL DEFAULT '',
            difficulty TEXT NOT NULL DEFAULT 'Média',
            inspired_by_real_question TEXT NOT NULL DEFAULT '',
            is_favorite INTEGER NOT NULL DEFAULT 0,
            answered_with_doubt INTEGER NOT NULL DEFAULT 0,
            user_answer TEXT,
            is_correct INTEGER,
            annotations_json TEXT NOT NULL DEFAULT '[]',
            answered_at TEXT,
            FOREIGN KEY (battery_id) REFERENCES question_batteries(id) ON DELETE CASCADE
        )
        """
    )

    try:
        cur.execute("ALTER TABLE assertions ADD COLUMN answered_with_doubt INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # Default settings
    defaults = {
        "gemini_api_key": os.environ.get("GEMINI_API_KEY", ""),
        "gemini_model": "gemini-2.5-flash",
        "default_area": "Geral",
        "default_depth": "Misto Padrão Cebraspe",
    }
    for k, v in defaults.items():
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    conn.commit()
    conn.close()


def get_settings() -> Dict[str, str]:
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    result = {row["key"]: row["value"] for row in rows}
    if not result.get("gemini_api_key") and os.environ.get("GEMINI_API_KEY"):
        result["gemini_api_key"] = os.environ["GEMINI_API_KEY"]
    return result


def update_settings(new_settings: Dict[str, Any]) -> Dict[str, str]:
    conn = get_connection()
    cur = conn.cursor()
    for k, v in new_settings.items():
        if v is not None:
            cur.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (k, str(v)),
            )
    conn.commit()
    conn.close()
    return get_settings()


def save_study_material(
    title: str,
    subject: str,
    area: str,
    total_pages: int,
    pages: List[Dict[str, Any]],
    extracted_questions: List[Dict[str, Any]],
    recurrence_map: List[Dict[str, Any]],
) -> int:
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now().isoformat()
    cur.execute(
        """
        INSERT INTO study_materials (
            title, subject, area, total_pages, pages_json, extracted_questions_json, recurrence_map_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            title,
            subject,
            area,
            total_pages,
            json.dumps(pages, ensure_ascii=False),
            json.dumps(extracted_questions, ensure_ascii=False),
            json.dumps(recurrence_map, ensure_ascii=False),
            now,
        ),
    )
    material_id = cur.lastrowid

    for q in extracted_questions:
        cur.execute(
            """
            INSERT INTO real_questions_bank (
                material_id, subject, subtopic, exam_info, statement, answer, commentary, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                material_id,
                subject,
                q.get("subtopic", "Geral"),
                q.get("exam_info", "Cebraspe"),
                q.get("statement", ""),
                q.get("answer", ""),
                q.get("commentary", ""),
                now,
            ),
        )

    conn.commit()
    conn.close()
    return int(material_id)


def update_material_recurrence(material_id: int, recurrence_map: List[Dict[str, Any]]) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE study_materials SET recurrence_map_json = ? WHERE id = ?",
        (json.dumps(recurrence_map, ensure_ascii=False), material_id),
    )
    conn.commit()
    conn.close()


def get_study_material(material_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM study_materials WHERE id = ?", (material_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["pages"] = json.loads(d.pop("pages_json", "[]"))
    d["extracted_questions"] = json.loads(d.pop("extracted_questions_json", "[]"))
    d["recurrence_map"] = json.loads(d.pop("recurrence_map_json", "[]"))
    return d


def list_study_materials() -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, title, subject, area, total_pages, extracted_questions_json, recurrence_map_json, created_at FROM study_materials ORDER BY id DESC"
    ).fetchall()
    conn.close()
    items = []
    for row in rows:
        d = dict(row)
        questions = json.loads(d.pop("extracted_questions_json", "[]"))
        recurrence = json.loads(d.pop("recurrence_map_json", "[]"))
        d["real_questions_count"] = len(questions)
        d["recurrence_map"] = recurrence
        items.append(d)
    return items


def save_question_battery(
    material_id: Optional[int],
    title: str,
    subject: str,
    area: str,
    depth: str,
    recurrence_summary: List[Dict[str, Any]],
    assertions: List[Dict[str, Any]],
) -> int:
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now().isoformat()

    cur.execute(
        """
        INSERT INTO question_batteries (
            material_id, title, subject, area, depth, total_questions, recurrence_summary_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            material_id,
            title,
            subject,
            area,
            depth,
            len(assertions),
            json.dumps(recurrence_summary, ensure_ascii=False),
            now,
        ),
    )
    battery_id = int(cur.lastrowid)

    for idx, item in enumerate(assertions, start=1):
        ans = str(item.get("answer", "C")).strip().upper()
        if ans.startswith("C"):
            ans = "C"
        elif ans.startswith("E"):
            ans = "E"
        else:
            ans = "C"

        cur.execute(
            """
            INSERT INTO assertions (
                battery_id, material_id, item_number, subtopic, recurrence_level,
                command_text, statement, answer, explanation, pdf_quote, pdf_page,
                trap_type, difficulty, inspired_by_real_question
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                battery_id,
                material_id,
                idx,
                item.get("subtopic", "Geral"),
                item.get("recurrence_level", "Alta"),
                item.get("command_text", f"Acerca de {subject}, julgue o item a seguir."),
                item.get("statement", ""),
                ans,
                item.get("explanation", ""),
                item.get("pdf_quote", ""),
                str(item.get("pdf_page", "")),
                item.get("trap_type", "Literalidade / Conceito"),
                item.get("difficulty", "Média"),
                item.get("inspired_by_real_question", ""),
            ),
        )

    conn.commit()
    conn.close()
    return battery_id


def get_battery(battery_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM question_batteries WHERE id = ?", (battery_id,)).fetchone()
    if not row:
        conn.close()
        return None
    battery = dict(row)
    battery["recurrence_summary"] = json.loads(battery.pop("recurrence_summary_json", "[]"))

    assertion_rows = conn.execute(
        "SELECT * FROM assertions WHERE battery_id = ? ORDER BY item_number ASC",
        (battery_id,),
    ).fetchall()
    conn.close()

    assertions = []
    for a in assertion_rows:
        ad = dict(a)
        ad["is_favorite"] = bool(ad["is_favorite"])
        ad["answered_with_doubt"] = bool(ad.get("answered_with_doubt", 0))
        ad["annotations"] = json.loads(ad.pop("annotations_json", "[]"))
        assertions.append(ad)

    battery["assertions"] = assertions
    return battery


def list_batteries() -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM question_batteries ORDER BY id DESC").fetchall()
    result = []
    for row in rows:
        b = dict(row)
        b["recurrence_summary"] = json.loads(b.pop("recurrence_summary_json", "[]"))
        stats = conn.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN user_answer IS NOT NULL THEN 1 ELSE 0 END) as answered,
                SUM(CASE WHEN user_answer = 'BLANK' THEN 1 ELSE 0 END) as blank,
                SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as correct,
                SUM(CASE WHEN is_correct = 0 AND user_answer != 'BLANK' THEN 1 ELSE 0 END) as wrong,
                SUM(CASE WHEN is_favorite = 1 THEN 1 ELSE 0 END) as favorites
            FROM assertions WHERE battery_id = ?
            """,
            (b["id"],),
        ).fetchone()
        b["stats"] = {
            "total": stats["total"] or 0,
            "answered": stats["answered"] or 0,
            "blank": stats["blank"] or 0,
            "correct": stats["correct"] or 0,
            "wrong": stats["wrong"] or 0,
            "favorites": stats["favorites"] or 0,
            "net_score": (stats["correct"] or 0) - (stats["wrong"] or 0),
        }
        result.append(b)
    conn.close()
    return result


def record_assertion_answer(
    assertion_id: int,
    user_answer: Optional[str],
    is_favorite: Optional[bool] = None,
    annotations: Optional[List[Dict[str, Any]]] = None,
    answered_with_doubt: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM assertions WHERE id = ?", (assertion_id,)).fetchone()
    if not row:
        conn.close()
        return None

    current = dict(row)
    now = datetime.now().isoformat()

    if user_answer is not None:
        ua = user_answer.strip().upper()
        if ua in ("C", "E"):
            is_correct = 1 if ua == current["answer"] else 0
            conn.execute(
                "UPDATE assertions SET user_answer = ?, is_correct = ?, answered_at = ? WHERE id = ?",
                (ua, is_correct, now, assertion_id),
            )
        elif ua == "BLANK":
            conn.execute(
                "UPDATE assertions SET user_answer = 'BLANK', is_correct = NULL, answered_at = ? WHERE id = ?",
                (now, assertion_id),
            )
        elif ua == "RESET":
            conn.execute(
                "UPDATE assertions SET user_answer = NULL, is_correct = NULL, answered_with_doubt = 0, answered_at = NULL WHERE id = ?",
                (assertion_id,),
            )

    if answered_with_doubt is not None:
        conn.execute(
            "UPDATE assertions SET answered_with_doubt = ?, is_favorite = CASE WHEN ? = 1 THEN 1 ELSE is_favorite END WHERE id = ?",
            (1 if answered_with_doubt else 0, 1 if answered_with_doubt else 0, assertion_id),
        )

    if is_favorite is not None:
        conn.execute(
            "UPDATE assertions SET is_favorite = ? WHERE id = ?",
            (1 if is_favorite else 0, assertion_id),
        )

    if annotations is not None:
        conn.execute(
            "UPDATE assertions SET annotations_json = ? WHERE id = ?",
            (json.dumps(annotations, ensure_ascii=False), assertion_id),
        )

    conn.commit()
    updated = conn.execute("SELECT * FROM assertions WHERE id = ?", (assertion_id,)).fetchone()
    conn.close()
    res = dict(updated)
    res["is_favorite"] = bool(res["is_favorite"])
    res["answered_with_doubt"] = bool(res.get("answered_with_doubt", 0))
    res["annotations"] = json.loads(res.pop("annotations_json", "[]"))
    return res


def get_error_notebook(subject: Optional[str] = None, only_favorites: bool = False) -> Dict[str, Any]:
    conn = get_connection()
    query = """
        SELECT a.*, b.title as battery_title, b.subject as subject, b.area as area
        FROM assertions a
        JOIN question_batteries b ON a.battery_id = b.id
        WHERE (a.is_correct = 0 OR a.is_favorite = 1)
    """
    params: List[Any] = []
    if only_favorites:
        query = """
            SELECT a.*, b.title as battery_title, b.subject as subject, b.area as area
            FROM assertions a
            JOIN question_batteries b ON a.battery_id = b.id
            WHERE a.is_favorite = 1
        """
    if subject:
        query += " AND b.subject = ?"
        params.append(subject)

    query += " ORDER BY a.answered_at DESC, a.id DESC"
    rows = conn.execute(query, params).fetchall()

    # Subtopic error aggregation
    subtopic_stats_rows = conn.execute(
        """
        SELECT
            b.subject,
            a.subtopic,
            COUNT(*) as total_answered,
            SUM(CASE WHEN a.is_correct = 1 THEN 1 ELSE 0 END) as correct,
            SUM(CASE WHEN a.is_correct = 0 AND a.user_answer != 'BLANK' THEN 1 ELSE 0 END) as wrong,
            SUM(CASE WHEN a.user_answer = 'BLANK' THEN 1 ELSE 0 END) as blank
        FROM assertions a
        JOIN question_batteries b ON a.battery_id = b.id
        WHERE a.user_answer IS NOT NULL
        GROUP BY b.subject, a.subtopic
        ORDER BY wrong DESC
        """
    ).fetchall()

    trap_stats_rows = conn.execute(
        """
        SELECT
            a.trap_type,
            COUNT(*) as total_answered,
            SUM(CASE WHEN a.is_correct = 0 AND a.user_answer != 'BLANK' THEN 1 ELSE 0 END) as wrong
        FROM assertions a
        WHERE a.user_answer IS NOT NULL AND a.trap_type != ''
        GROUP BY a.trap_type
        ORDER BY wrong DESC
        """
    ).fetchall()

    conn.close()

    items = []
    for r in rows:
        d = dict(r)
        d["is_favorite"] = bool(d["is_favorite"])
        d["annotations"] = json.loads(d.pop("annotations_json", "[]"))
        items.append(d)

    return {
        "items": items,
        "subtopic_stats": [dict(r) for r in subtopic_stats_rows],
        "trap_stats": [dict(r) for r in trap_stats_rows],
    }

