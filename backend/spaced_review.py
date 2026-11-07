"""
Módulo de Anotação de Resumos de Erros, Relacionamento Conceitual
(Tópico -> Subtópico -> Conceito -> Subconceito) e Revisão Espaçada de 3 em 3 Dias (`spaced_review.py`).

Funcionalidades:
1. Apresenta os conceitos das questões erradas e os Tópicos/Subtópicos disponíveis nos PDFs armazenados
   para que o aluno indique/relacione `Tópico -> Subtópico -> Conceito -> Subconceito` e escreva seu
   próprio Resumo/Anotação do erro (`student_summary`, `personal_notes`).
2. Persiste esse Overview de Respostas Erradas no banco de dados (SQL + NoSQL) com agendamento
   automático de revisão de **3 em 3 dias** (`next_review_at = now + 3 days`).
3. Monitora e dispara a revisão de 3 em 3 dias: quando acionada (automaticamente por vencimento de 3 dias
   ou sob demanda pelo aluno), **gera exatamente +10 questões inéditas** no estilo Cebraspe (`Certo/Errado`)
   baseadas nos tópicos, subtópicos, conceitos, subconceitos e resumos salvos pelo aluno, reagendando
   a próxima revisão para +3 dias.
"""

import json
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from google import genai
from google.genai import types

import database
from gemini_service import GeneratedBatteryResponseSchema
from storage_manager import NoSQLDocumentStore, get_material_knowledge_tree_nosql
from topic_parser import (
    CEBRASPE_SURGICAL_SWAPS,
    generate_assertions_from_single_period,
    parse_pdf_topics_and_subtopics,
)

REVIEW_INTERVAL_DAYS = 3
DEFAULT_REVIEW_QUESTIONS_COUNT = 10
ADAPTIVE_INTERVAL_LADDER = [3, 7, 15, 30]
ADAPTIVE_MASTERY_THRESHOLD = 0.85


def init_spaced_review_tables() -> None:
    """Cria as tabelas SQL para o Overview de Resumos de Erros, Árvore de Conceitos e Ciclos de 3 em 3 dias."""
    conn = database.get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS student_error_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER,
            assertion_id INTEGER,
            subject TEXT NOT NULL DEFAULT 'Disciplina Geral',
            topic TEXT NOT NULL,
            subtopic TEXT NOT NULL,
            concept TEXT NOT NULL,
            subconcept TEXT NOT NULL DEFAULT '',
            presented_concept_context TEXT NOT NULL DEFAULT '',
            student_summary TEXT NOT NULL,
            personal_notes TEXT NOT NULL DEFAULT '',
            trap_type TEXT NOT NULL DEFAULT 'Conceito / Regra',
            pdf_page TEXT NOT NULL DEFAULT '',
            review_interval_days INTEGER NOT NULL DEFAULT 3,
            review_cycle_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            last_reviewed_at TEXT,
            next_review_at TEXT NOT NULL,
            FOREIGN KEY (material_id) REFERENCES study_materials(id) ON DELETE SET NULL,
            FOREIGN KEY (assertion_id) REFERENCES assertions(id) ON DELETE SET NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS concept_hierarchy_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER,
            subject TEXT NOT NULL,
            topic TEXT NOT NULL,
            subtopic TEXT NOT NULL,
            concept TEXT NOT NULL,
            subconcept TEXT NOT NULL DEFAULT '',
            summary_ids_json TEXT NOT NULL DEFAULT '[]',
            generated_questions_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS spaced_review_cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            battery_id INTEGER NOT NULL,
            summary_ids_json TEXT NOT NULL DEFAULT '[]',
            questions_generated INTEGER NOT NULL DEFAULT 10,
            triggered_mode TEXT NOT NULL DEFAULT '3_day_cycle',
            triggered_at TEXT NOT NULL,
            next_scheduled_at TEXT NOT NULL,
            FOREIGN KEY (battery_id) REFERENCES question_batteries(id) ON DELETE CASCADE
        )
        """
    )

    conn.commit()
    conn.close()


def get_available_concepts_and_hierarchy(material_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Apresenta para o aluno:
    1. Os conceitos/questões que ele errou recentemente (com o conceito extraído da questão/PDF),
       para que ele possa escolher/indicar a qual Tópico, Subtópico, Conceito e Subconceito pertence;
    2. A lista estruturada de Tópicos e Subtópicos disponíveis nos PDFs armazenados;
    3. Os relacionamentos `Tópico -> Subtópico -> Conceito -> Subconceito` já criados pelo aluno.
    """
    init_spaced_review_tables()
    conn = database.get_connection()

    # 1. Buscar assertivas erradas ou favoritadas pelo aluno para apresentar o conceito
    if material_id is not None:
        wrong_rows = conn.execute(
            """
            SELECT a.*, b.subject as subject, b.title as battery_title
            FROM assertions a
            JOIN question_batteries b ON a.battery_id = b.id
            WHERE a.material_id = ? AND (a.is_correct = 0 OR a.is_favorite = 1)
            ORDER BY a.answered_at DESC, a.id DESC
            """,
            (material_id,),
        ).fetchall()
    else:
        wrong_rows = conn.execute(
            """
            SELECT a.*, b.subject as subject, b.title as battery_title
            FROM assertions a
            JOIN question_batteries b ON a.battery_id = b.id
            WHERE a.is_correct = 0 OR a.is_favorite = 1
            ORDER BY a.answered_at DESC, a.id DESC
            LIMIT 30
            """
        ).fetchall()

    # 2. Buscar todos os materiais e seus Tópicos/Subtópicos para o seletor do aluno
    materials = database.list_study_materials()
    available_topics_tree: List[Dict[str, Any]] = []
    seen_pairs = set()

    for mat in materials:
        m_id = mat["id"]
        if material_id is not None and m_id != material_id:
            continue
        nosql_tree = get_material_knowledge_tree_nosql(m_id)
        parsed_topics = (nosql_tree or {}).get("parsed_topics", [])
        if parsed_topics:
            for pt in parsed_topics:
                t_name = pt.get("topic", mat["title"])
                s_name = pt.get("subtopic", "Geral")
                if (t_name, s_name) not in seen_pairs:
                    seen_pairs.add((t_name, s_name))
                    available_topics_tree.append(
                        {
                            "material_id": m_id,
                            "subject": mat["subject"],
                            "topic": t_name,
                            "subtopic": s_name,
                            "pages_reference": pt.get("pages_reference", ""),
                        }
                    )
        for rec in mat.get("recurrence_map", []):
            t_name = rec.get("topic", mat["title"])
            s_name = rec.get("subtopic", "Geral")
            if (t_name, s_name) not in seen_pairs:
                seen_pairs.add((t_name, s_name))
                available_topics_tree.append(
                    {
                        "material_id": m_id,
                        "subject": mat["subject"],
                        "topic": t_name,
                        "subtopic": s_name,
                        "pages_reference": rec.get("pages_reference", ""),
                    }
                )

    # 3. Montar sugestões de conceitos a partir dos erros do aluno
    presented_concepts: List[Dict[str, Any]] = []
    for r in wrong_rows:
        d = dict(r)
        quote = d.get("pdf_quote") or d.get("explanation") or d.get("statement", "")
        suggested_concept = f"{d.get('subtopic', 'Conceito')} — {d.get('trap_type', 'Regra Geral')}"
        presented_concepts.append(
            {
                "assertion_id": d["id"],
                "material_id": d.get("material_id"),
                "subject": d.get("subject", "Disciplina"),
                "suggested_topic": d.get("battery_title", "Tópico do Material"),
                "suggested_subtopic": d.get("subtopic", "Subtópico Geral"),
                "suggested_concept": suggested_concept,
                "suggested_subconcept": d.get("trap_type", "Distinção Conceitual"),
                "presented_concept_context": quote,
                "original_statement": d.get("statement", ""),
                "official_answer": d.get("answer", "C"),
                "explanation": d.get("explanation", ""),
                "pdf_page": d.get("pdf_page", "p. 1"),
                "trap_type": d.get("trap_type", "Conceito"),
            }
        )

    # 4. Carregar relacionamentos já criados pelo aluno
    rel_rows = conn.execute(
        "SELECT * FROM concept_hierarchy_links ORDER BY id DESC"
    ).fetchall()
    conn.close()

    relationships = []
    for rel in rel_rows:
        rd = dict(rel)
        rd["summary_ids"] = json.loads(rd.pop("summary_ids_json", "[]"))
        relationships.append(rd)

    return {
        "presented_concepts_from_errors": presented_concepts,
        "available_topics_and_subtopics": available_topics_tree,
        "concept_relationships": relationships,
    }


def _upsert_concept_relationship(
    conn: Any,
    material_id: Optional[int],
    subject: str,
    topic: str,
    subtopic: str,
    concept: str,
    subconcept: str,
    summary_id: int,
) -> int:
    row = conn.execute(
        """
        SELECT id, summary_ids_json FROM concept_hierarchy_links
        WHERE lower(topic) = lower(?) AND lower(subtopic) = lower(?)
          AND lower(concept) = lower(?) AND lower(subconcept) = lower(?)
        """,
        (topic.strip(), subtopic.strip(), concept.strip(), subconcept.strip()),
    ).fetchone()

    now = datetime.now().isoformat()
    if row:
        ids = json.loads(row["summary_ids_json"] or "[]")
        if summary_id not in ids:
            ids.append(summary_id)
        conn.execute(
            "UPDATE concept_hierarchy_links SET summary_ids_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(ids), now, row["id"]),
        )
        return int(row["id"])
    else:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO concept_hierarchy_links (
                material_id, subject, topic, subtopic, concept, subconcept,
                summary_ids_json, generated_questions_count, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                material_id,
                subject.strip(),
                topic.strip(),
                subtopic.strip(),
                concept.strip(),
                subconcept.strip(),
                json.dumps([summary_id]),
                now,
            ),
        )
        return int(cur.lastrowid)


def create_student_error_summary_note(
    topic: str,
    subtopic: str,
    concept: str,
    student_summary: str,
    subconcept: str = "",
    personal_notes: str = "",
    presented_concept_context: str = "",
    subject: str = "Disciplina Geral",
    material_id: Optional[int] = None,
    assertion_id: Optional[int] = None,
    trap_type: str = "Conceito / Regra",
    pdf_page: str = "p. 1",
    review_interval_days: int = REVIEW_INTERVAL_DAYS,
    nosql_store: Optional[NoSQLDocumentStore] = None,
) -> Dict[str, Any]:
    """
    Salva no banco (SQL + NoSQL) o resumo/anotação escrito pelo aluno sobre o que ele errou,
    vinculando à árvore `Tópico -> Subtópico -> Conceito -> Subconceito` escolhida pelo aluno
    e agendando a próxima revisão para daqui a 3 dias (`now + 3 days`).
    """
    init_spaced_review_tables()
    if not topic.strip() or not subtopic.strip() or not concept.strip():
        raise ValueError("Tópico, Subtópico e Conceito são obrigatórios.")
    if not student_summary.strip():
        raise ValueError("O resumo/anotação da resposta errada não pode estar vazio.")

    now_dt = datetime.now()
    now_iso = now_dt.isoformat()
    interval = max(1, int(review_interval_days or REVIEW_INTERVAL_DAYS))
    next_review_iso = (now_dt + timedelta(days=interval)).isoformat()

    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO student_error_summaries (
            material_id, assertion_id, subject, topic, subtopic, concept, subconcept,
            presented_concept_context, student_summary, personal_notes, trap_type, pdf_page,
            review_interval_days, review_cycle_count, created_at, last_reviewed_at, next_review_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, NULL, ?)
        """,
        (
            material_id,
            assertion_id,
            subject.strip() or "Disciplina Geral",
            topic.strip(),
            subtopic.strip(),
            concept.strip(),
            subconcept.strip(),
            presented_concept_context.strip(),
            student_summary.strip(),
            personal_notes.strip(),
            trap_type.strip(),
            pdf_page.strip(),
            interval,
            now_iso,
            next_review_iso,
        ),
    )
    summary_id = int(cur.lastrowid)

    link_id = _upsert_concept_relationship(
        conn=conn,
        material_id=material_id,
        subject=subject,
        topic=topic,
        subtopic=subtopic,
        concept=concept,
        subconcept=subconcept,
        summary_id=summary_id,
    )

    conn.commit()
    conn.close()

    record = {
        "id": summary_id,
        "relationship_link_id": link_id,
        "material_id": material_id,
        "assertion_id": assertion_id,
        "subject": subject.strip() or "Disciplina Geral",
        "topic": topic.strip(),
        "subtopic": subtopic.strip(),
        "concept": concept.strip(),
        "subconcept": subconcept.strip(),
        "presented_concept_context": presented_concept_context.strip(),
        "student_summary": student_summary.strip(),
        "personal_notes": personal_notes.strip(),
        "trap_type": trap_type.strip(),
        "pdf_page": pdf_page.strip(),
        "review_interval_days": interval,
        "review_cycle_count": 0,
        "created_at": now_iso,
        "last_reviewed_at": None,
        "next_review_at": next_review_iso,
    }

    store = nosql_store or NoSQLDocumentStore()
    store.upsert_document("student_error_summaries_overview", str(summary_id), record)
    return record


def list_student_error_summaries_overview(
    material_id: Optional[int] = None,
    only_due: bool = False,
    reference_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Retorna o Overview completo das respostas erradas resumidas/anotadas pelo aluno,
    indicando quais já completaram o ciclo de 3 em 3 dias (`is_due_for_3day_review = True`)
    e quantos dias/horas faltam para a próxima revisão programada.
    """
    init_spaced_review_tables()
    ref_dt = reference_time or datetime.now()
    conn = database.get_connection()

    if material_id is not None:
        rows = conn.execute(
            "SELECT * FROM student_error_summaries WHERE material_id = ? ORDER BY next_review_at ASC, id DESC",
            (material_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM student_error_summaries ORDER BY next_review_at ASC, id DESC"
        ).fetchall()

    cycles_rows = conn.execute(
        "SELECT * FROM spaced_review_cycles ORDER BY id DESC LIMIT 15"
    ).fetchall()
    conn.close()

    items: List[Dict[str, Any]] = []
    due_items: List[Dict[str, Any]] = []

    for r in rows:
        d = dict(r)
        try:
            next_dt = datetime.fromisoformat(d["next_review_at"])
        except Exception:
            next_dt = ref_dt
        delta_seconds = (next_dt - ref_dt).total_seconds()
        is_due = delta_seconds <= 0
        days_remaining = max(0, int((delta_seconds + 86399) // 86400)) if not is_due else 0

        d["is_due_for_3day_review"] = is_due
        d["days_until_review"] = days_remaining
        d["hierarchy_path"] = " ➔ ".join(
            [p for p in [d["topic"], d["subtopic"], d["concept"], d["subconcept"]] if p]
        )

        if is_due:
            due_items.append(d)
        if not only_due or is_due:
            items.append(d)

    cycles_history = []
    for c in cycles_rows:
        cd = dict(c)
        cd["summary_ids"] = json.loads(cd.pop("summary_ids_json", "[]"))
        cycles_history.append(cd)

    return {
        "total_summaries": len(rows),
        "due_for_review_count": len(due_items),
        "review_alert_active": len(due_items) > 0,
        "review_interval_days": REVIEW_INTERVAL_DAYS,
        "items": items,
        "due_items": due_items,
        "cycles_history": cycles_history,
    }


def _synthesize_questions_from_summary_and_concept(
    summary_records: List[Dict[str, Any]],
    questions_count: int = DEFAULT_REVIEW_QUESTIONS_COUNT,
    api_key: str = "",
    model_name: str = "gemini-2.5-flash",
) -> List[Dict[str, Any]]:
    """
    Gera exatamente `questions_count` (padrão: 10) questões inéditas de Certo/Errado no estilo Cebraspe
    a partir dos resumos das respostas erradas salvos pelo aluno e de seus relacionamentos
    `Tópico -> Subtópico -> Conceito -> Subconceito`.
    """
    if not summary_records:
        return []

    if api_key and api_key.strip():
        try:
            client = genai.Client(api_key=api_key.strip())
            summaries_json = json.dumps(
                [
                    {
                        "topic": s["topic"],
                        "subtopic": s["subtopic"],
                        "concept": s["concept"],
                        "subconcept": s.get("subconcept", ""),
                        "student_summary_of_error": s["student_summary"],
                        "personal_notes": s.get("personal_notes", ""),
                        "presented_concept_context": s.get("presented_concept_context", ""),
                        "trap_type": s.get("trap_type", "Conceito"),
                        "pdf_page": s.get("pdf_page", "p. 1"),
                    }
                    for s in summary_records
                ],
                ensure_ascii=False,
                indent=2,
            )
            prompt = f"""
Você é um Examinador Titular da banca **CEBRASPE (CESPE/UnB)** conduzindo a **Revisão Espaçada de 3 em 3 Dias** do aluno.
Abaixo estão os **Resumos de Respostas Erradas e Anotações** escritos pelo próprio aluno, organizados na hierarquia:
`Tópico -> Subtópico -> Conceito -> Subconceito`.

Elabore exatamente **{questions_count} assertivas inéditas** de **CERTO ('C') ou ERRADO ('E')** (proporção ~50% C / 50% E) que testem profundamente os conceitos, subconceitos e resumos anotados pelo aluno, garantindo que ele fixe definitivamente esses pontos!

### RESUMOS DE ERROS E HIERARQUIA CONCEITUAL DO ALUNO:
{summaries_json}
"""
            resp = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GeneratedBatteryResponseSchema,
                    temperature=0.4,
                ),
            )
            parsed = json.loads(resp.text)
            ai_assertions = parsed.get("assertions", [])
            if len(ai_assertions) >= questions_count:
                return ai_assertions[:questions_count]
        except Exception:
            pass

    # Motor determinístico local: gera exatamente `questions_count` variações baseadas nos períodos/resumos do aluno
    synthesized: List[Dict[str, Any]] = []
    idx = 0

    while len(synthesized) < questions_count:
        rec = summary_records[idx % len(summary_records)]
        topic = rec.get("topic", "Tópico Principal")
        subtopic = rec.get("subtopic", "Subtópico")
        concept = rec.get("concept", "Conceito")
        subconcept = rec.get("subconcept") or rec.get("trap_type", "Aplicação")
        student_sum = rec.get("student_summary", "").strip()
        context_quote = rec.get("presented_concept_context", "").strip() or student_sum
        notes = rec.get("personal_notes", "").strip()
        page_ref = rec.get("pdf_page") or "p. 1"

        base_text = student_sum if len(student_sum) >= 35 else f"{student_sum}. {context_quote}".strip(". ")
        if len(base_text) < 40:
            base_text = (
                f"No estudo de {concept} ({subconcept}), vinculado ao subtópico {subtopic}, "
                f"{base_text}, devendo ser observada a distinção técnica anotada no resumo de revisão."
            )

        variation_type = len(synthesized) % 4
        cmd = (
            f"[Revisão 3 em 3 Dias] Acerca de {topic} — especificamente quanto a {subtopic} "
            f"({concept}{f' / {subconcept}' if subconcept else ''}) —, julgue o item a seguir."
        )

        if variation_type == 0:
            # Item CERTO: Confirmação direta da síntese correta anotada pelo aluno
            stmt = (
                f"No que tange a {concept} ({subconcept}), é correto afirmar que {base_text[0].lower() + base_text[1:] if len(base_text) > 1 and base_text[0].isupper() else base_text}"
            )
            if not stmt.endswith("."):
                stmt += "."
            synthesized.append(
                {
                    "subtopic": f"{subtopic} ➔ {concept}",
                    "recurrence_level": "Muito Alta",
                    "command_text": cmd,
                    "statement": stmt,
                    "answer": "C",
                    "explanation": (
                        f"ITEM CERTO. A assertiva reflete com exatidão a regra consolidada no seu Resumo de Revisão "
                        f"para a árvore [{topic} ➔ {subtopic} ➔ {concept} ➔ {subconcept}]: \"{student_sum}\"."
                    ),
                    "pdf_quote": context_quote,
                    "pdf_page": page_ref,
                    "trap_type": "Confirmação Conceitual (Revisão 3 Dias)",
                    "difficulty": "Média",
                    "inspired_by_real_question": f"Revisão 3 em 3 dias — Conceito: {concept} ({subconcept})",
                }
            )
        elif variation_type == 1:
            # Item ERRADO: Inversão cirúrgica de modalizador/conceito sobre o resumo do aluno
            mutated = None
            trap_label = "Inversão de Conceito"
            reason = "A assertiva inverteu o sentido normativo/conceitual registrado no seu resumo de revisão."
            for pattern, repl, t_label, r_desc in CEBRASPE_SURGICAL_SWAPS:
                if pattern.search(base_text):
                    mutated = pattern.sub(repl, base_text, count=1)
                    trap_label = t_label
                    reason = r_desc
                    break
            if not mutated:
                mutated = (
                    f"Diferentemente do regime aplicável a {topic}, em sede de {concept} ({subconcept}), "
                    f"é vedada a aplicação da regra segundo a qual {base_text[0].lower() + base_text[1:] if len(base_text) > 1 else base_text}"
                )
            if not mutated.endswith("."):
                mutated += "."
            synthesized.append(
                {
                    "subtopic": f"{subtopic} ➔ {concept}",
                    "recurrence_level": "Muito Alta",
                    "command_text": cmd,
                    "statement": mutated,
                    "answer": "E",
                    "explanation": (
                        f"ITEM ERRADO. {reason} Conforme seu resumo salvo no banco para [{topic} ➔ {subtopic} ➔ {concept}]: \"{student_sum}\"."
                    ),
                    "pdf_quote": context_quote,
                    "pdf_page": page_ref,
                    "trap_type": trap_label,
                    "difficulty": "Média",
                    "inspired_by_real_question": f"Revisão 3 em 3 dias — Armadilha em {concept} ({subconcept})",
                }
            )
        elif variation_type == 2:
            # Item CERTO: Aplicação contextual combinando o conceito e a nota pessoal
            extra_clause = f" ({notes})" if notes else ""
            stmt = (
                f"Considerando a relação entre o subtópico {subtopic} e o conceito de {concept}{extra_clause}, "
                f"verifica-se que: {context_quote}"
            )
            if not stmt.endswith("."):
                stmt += "."
            synthesized.append(
                {
                    "subtopic": f"{subtopic} ➔ {concept}",
                    "recurrence_level": "Alta",
                    "command_text": cmd,
                    "statement": stmt,
                    "answer": "C",
                    "explanation": (
                        f"ITEM CERTO. O item reproduz corretamente o fundamento teórico vinculado ao conceito "
                        f"'{concept}' ({subconcept}) anotado em seu caderno de revisão de 3 em 3 dias."
                    ),
                    "pdf_quote": context_quote,
                    "pdf_page": page_ref,
                    "trap_type": "Literalidade / Conceito Exato",
                    "difficulty": "Média",
                    "inspired_by_real_question": f"Revisão 3 em 3 dias — Fixação de {concept}",
                }
            )
        else:
            # Item ERRADO: Situação hipotética / Restrição absoluta sobre o subconceito
            clean_b = base_text.rstrip(".")
            stmt = (
                f"Situação hipotética: Em determinado caso concreto envolvendo {subtopic}, suscitou-se a incidência de {concept} ({subconcept}). "
                f"Assertiva: Nessa situação, a regra segundo a qual {clean_b[0].lower() + clean_b[1:] if len(clean_b) > 1 else clean_b} "
                f"aplica-se exclusivamente mediante prévia autorização judicial, prescindindo dos demais requisitos normativos."
            )
            synthesized.append(
                {
                    "subtopic": f"{subtopic} ➔ {concept}",
                    "recurrence_level": "Muito Alta",
                    "command_text": cmd,
                    "statement": stmt,
                    "answer": "E",
                    "explanation": (
                        f"ITEM ERRADO. A assertiva inseriu condicionante falsa ('exclusivamente mediante prévia autorização judicial'). "
                        f"Confira sua anotação de revisão para [{topic} ➔ {subtopic} ➔ {concept} ➔ {subconcept}]: \"{student_sum}\"."
                    ),
                    "pdf_quote": context_quote,
                    "pdf_page": page_ref,
                    "trap_type": "Situação Hipotética / Restrição Indevida",
                    "difficulty": "Difícil",
                    "inspired_by_real_question": f"Revisão 3 em 3 dias — Situação Prática em {concept}",
                }
            )

        idx += 1

    return synthesized[:questions_count]


def trigger_3day_spaced_review_and_generate_10_questions(
    summary_ids: Optional[List[int]] = None,
    relationship_link_id: Optional[int] = None,
    questions_count: int = DEFAULT_REVIEW_QUESTIONS_COUNT,
    force_all_if_none_due: bool = True,
    api_key: str = "",
    model_name: str = "gemini-2.5-flash",
    reference_time: Optional[datetime] = None,
    nosql_store: Optional[NoSQLDocumentStore] = None,
) -> Dict[str, Any]:
    """
    Dispara a Revisão Espaçada de 3 em 3 dias sobre os resumos de respostas erradas salvos no banco
    (ou sobre um relacionamento específico `Tópico -> Subtópico -> Conceito -> Subconceito`),
    gera **+10 questões inéditas** sobre esses tópicos/conceitos e reagenda a próxima revisão para +3 dias!
    """
    init_spaced_review_tables()
    ref_dt = reference_time or datetime.now()
    conn = database.get_connection()

    target_rows = []
    triggered_mode = "3_day_cycle"

    if relationship_link_id is not None:
        link_row = conn.execute(
            "SELECT * FROM concept_hierarchy_links WHERE id = ?", (relationship_link_id,)
        ).fetchone()
        if link_row:
            ids = json.loads(link_row["summary_ids_json"] or "[]")
            if ids:
                placeholders = ",".join("?" for _ in ids)
                target_rows = conn.execute(
                    f"SELECT * FROM student_error_summaries WHERE id IN ({placeholders})",
                    ids,
                ).fetchall()
            triggered_mode = "concept_relationship"

    elif summary_ids:
        placeholders = ",".join("?" for _ in summary_ids)
        target_rows = conn.execute(
            f"SELECT * FROM student_error_summaries WHERE id IN ({placeholders})",
            summary_ids,
        ).fetchall()
        triggered_mode = "selected_summaries"
    else:
        # Buscar todos os resumos cujo ciclo de 3 dias já venceu (next_review_at <= ref_dt)
        all_rows = conn.execute(
            "SELECT * FROM student_error_summaries ORDER BY next_review_at ASC, id DESC"
        ).fetchall()
        for r in all_rows:
            try:
                ndt = datetime.fromisoformat(r["next_review_at"])
            except Exception:
                ndt = ref_dt
            if ndt <= ref_dt:
                target_rows.append(r)

        if not target_rows and force_all_if_none_due:
            target_rows = all_rows

    if not target_rows:
        conn.close()
        raise ValueError(
            "Nenhum resumo de resposta errada encontrado no banco. Anote pelo menos 1 resumo de erro primeiro!"
        )

    records = [dict(r) for r in target_rows]
    target_qty = max(1, int(questions_count or DEFAULT_REVIEW_QUESTIONS_COUNT))

    assertions = _synthesize_questions_from_summary_and_concept(
        summary_records=records,
        questions_count=target_qty,
        api_key=api_key,
        model_name=model_name,
    )

    first_rec = records[0]
    subject = first_rec.get("subject", "Revisão Espaçada")
    topics_covered = list(dict.fromkeys(r["subtopic"] for r in records))
    battery_title = (
        f"Revisão 3 em 3 Dias (+{len(assertions)} Questões) — {', '.join(topics_covered[:2])}"
    )

    battery_id = database.save_question_battery(
        material_id=first_rec.get("material_id"),
        title=battery_title,
        subject=subject,
        area="Revisão Espaçada 3 em 3 Dias",
        depth=f"Ciclo de Revisão de Erros ({len(records)} resumo(s) revisado(s))",
        recurrence_summary=[],
        assertions=assertions,
    )

    # Atualizar last_reviewed_at, incrementar review_cycle_count e agendar próxima revisão para +3 dias
    now_iso = ref_dt.isoformat()
    next_3days_iso = (ref_dt + timedelta(days=REVIEW_INTERVAL_DAYS)).isoformat()
    reviewed_ids = [r["id"] for r in records]

    cur = conn.cursor()
    for r in records:
        interval = max(1, int(r.get("review_interval_days") or REVIEW_INTERVAL_DAYS))
        next_for_item = (ref_dt + timedelta(days=interval)).isoformat()
        cur.execute(
            """
            UPDATE student_error_summaries
            SET review_cycle_count = review_cycle_count + 1,
                last_reviewed_at = ?,
                next_review_at = ?
            WHERE id = ?
            """,
            (now_iso, next_for_item, r["id"]),
        )

    if relationship_link_id is not None:
        cur.execute(
            """
            UPDATE concept_hierarchy_links
            SET generated_questions_count = generated_questions_count + ?,
                updated_at = ?
            WHERE id = ?
            """,
            (len(assertions), now_iso, relationship_link_id),
        )

    cur.execute(
        """
        INSERT INTO spaced_review_cycles (
            battery_id, summary_ids_json, questions_generated, triggered_mode, triggered_at, next_scheduled_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            battery_id,
            json.dumps(reviewed_ids),
            len(assertions),
            triggered_mode,
            now_iso,
            next_3days_iso,
        ),
    )
    cycle_id = int(cur.lastrowid)
    conn.commit()
    conn.close()

    battery = database.get_battery(battery_id)
    store = nosql_store or NoSQLDocumentStore()
    store.upsert_document(
        "spaced_review_cycles",
        str(cycle_id),
        {
            "cycle_id": cycle_id,
            "battery_id": battery_id,
            "summary_ids": reviewed_ids,
            "questions_generated": len(assertions),
            "triggered_mode": triggered_mode,
            "triggered_at": now_iso,
            "next_scheduled_at": next_3days_iso,
        },
    )

    return {
        "cycle_id": cycle_id,
        "reviewed_summaries_count": len(records),
        "questions_generated_count": len(assertions),
        "next_review_scheduled_at": next_3days_iso,
        "battery": battery,
    }


# ===========================================================================
# MELHORIA 1: INTERVALOS ESPAÇADOS ADAPTATIVOS (3 ➔ 7 ➔ 15 ➔ 30 DIAS COM >= 85% DE ACERTO)
# ===========================================================================

def compute_next_adaptive_interval(current_interval_days: int, accuracy_ratio: float) -> int:
    """
    Calcula o próximo intervalo de revisão espaçada:
    - Se a taxa de acerto na revisão for >= 85% (`ADAPTIVE_MASTERY_THRESHOLD`), avança na escada
      `3 ➔ 7 ➔ 15 ➔ 30 dias`.
    - Se a taxa de acerto for < 85% (ou houver erros), mantém/retorna para `3 dias` para reforço intensivo.
    """
    if accuracy_ratio < ADAPTIVE_MASTERY_THRESHOLD:
        return REVIEW_INTERVAL_DAYS

    for step in ADAPTIVE_INTERVAL_LADDER:
        if step > current_interval_days:
            return step
    return ADAPTIVE_INTERVAL_LADDER[-1]


def evaluate_spaced_review_cycle_and_adapt_intervals(
    cycle_id: Optional[int] = None,
    battery_id: Optional[int] = None,
    reference_time: Optional[datetime] = None,
    nosql_store: Optional[NoSQLDocumentStore] = None,
) -> Dict[str, Any]:
    """
    Avalia o desempenho do aluno na bateria de 10 questões da revisão espaçada:
    - Se o aluno acertou >= 85% das questões respondidas (ex: >= 9 de 10 ou >= 85%), expande
      automaticamente o `review_interval_days` dos resumos revisados de `3` para `7`, `15` ou `30 dias`!
    - Se o aluno acertou < 85%, mantém ou retorna o intervalo para `3 dias` para garantir retenção.
    """
    init_spaced_review_tables()
    ref_dt = reference_time or datetime.now()
    conn = database.get_connection()

    if cycle_id is not None:
        cycle_row = conn.execute(
            "SELECT * FROM spaced_review_cycles WHERE id = ?", (cycle_id,)
        ).fetchone()
    elif battery_id is not None:
        cycle_row = conn.execute(
            "SELECT * FROM spaced_review_cycles WHERE battery_id = ? ORDER BY id DESC LIMIT 1",
            (battery_id,),
        ).fetchone()
    else:
        cycle_row = conn.execute(
            "SELECT * FROM spaced_review_cycles ORDER BY id DESC LIMIT 1"
        ).fetchone()

    if not cycle_row:
        conn.close()
        raise ValueError("Ciclo de revisão espaçada não encontrado para avaliação.")

    c_dict = dict(cycle_row)
    target_battery_id = int(c_dict["battery_id"])
    summary_ids: List[int] = json.loads(c_dict.get("summary_ids_json") or "[]")

    bat = database.get_battery(target_battery_id)
    if not bat or not bat.get("assertions"):
        conn.close()
        raise ValueError("Bateria da revisão espaçada não encontrada.")

    assertions = bat["assertions"]
    total_q = len(assertions)
    answered_q = [a for a in assertions if a.get("user_answer") in ("C", "E")]
    correct_q = [a for a in answered_q if a.get("is_correct") == 1]

    # Taxa de acerto calculada sobre o total da bateria (ou sobre as respondidas se já respondeu ao menos metade)
    denominator = total_q if len(answered_q) == total_q else max(1, len(answered_q))
    accuracy_ratio = (len(correct_q) / denominator) if answered_q else 0.0
    accuracy_pct = round(accuracy_ratio * 100, 1)
    mastery_achieved = len(answered_q) > 0 and accuracy_ratio >= ADAPTIVE_MASTERY_THRESHOLD

    updated_summaries: List[Dict[str, Any]] = []
    cur = conn.cursor()
    store = nosql_store or NoSQLDocumentStore()

    if summary_ids:
        placeholders = ",".join("?" for _ in summary_ids)
        sum_rows = conn.execute(
            f"SELECT * FROM student_error_summaries WHERE id IN ({placeholders})",
            summary_ids,
        ).fetchall()

        for sr in sum_rows:
            s_dict = dict(sr)
            old_interval = int(s_dict.get("review_interval_days") or REVIEW_INTERVAL_DAYS)
            new_interval = compute_next_adaptive_interval(old_interval, accuracy_ratio)
            new_next_review_iso = (ref_dt + timedelta(days=new_interval)).isoformat()

            cur.execute(
                """
                UPDATE student_error_summaries
                SET review_interval_days = ?,
                    next_review_at = ?,
                    last_reviewed_at = ?
                WHERE id = ?
                """,
                (new_interval, new_next_review_iso, ref_dt.isoformat(), s_dict["id"]),
            )
            s_dict["previous_interval_days"] = old_interval
            s_dict["review_interval_days"] = new_interval
            s_dict["next_review_at"] = new_next_review_iso
            updated_summaries.append(s_dict)
            store.upsert_document("student_error_summaries_overview", str(s_dict["id"]), s_dict)

    conn.commit()
    conn.close()

    return {
        "cycle_id": c_dict["id"],
        "battery_id": target_battery_id,
        "total_questions": total_q,
        "answered_questions": len(answered_q),
        "correct_questions": len(correct_q),
        "accuracy_ratio": round(accuracy_ratio, 4),
        "accuracy_percentage": accuracy_pct,
        "threshold_percentage": round(ADAPTIVE_MASTERY_THRESHOLD * 100, 1),
        "mastery_threshold_percentage": round(ADAPTIVE_MASTERY_THRESHOLD * 100, 1),
        "mastery_achieved": mastery_achieved,
        "achieved_mastery": mastery_achieved,
        "updated_summaries": updated_summaries,
        "updated_count": len(updated_summaries),
    }


# ===========================================================================
# MELHORIA 2: MARCADOR "ACERTEI COM DÚVIDA" -> ENVIO DIRETO PARA REVISÃO DE 3 EM 3 DIAS
# ===========================================================================

def queue_doubt_assertion_to_3day_review(
    assertion_id: int,
    student_doubt_note: str = "",
    nosql_store: Optional[NoSQLDocumentStore] = None,
) -> Dict[str, Any]:
    """
    Marca uma assertiva como 'Respondida com Dúvida' (`answered_with_doubt = True`, `is_favorite = True`)
    e a envia automaticamente para o Caderno de Resumos de Revisão de 3 em 3 Dias, mesmo quando o aluno
    acertou o item por intuição ou chute calculado!
    """
    init_spaced_review_tables()
    updated_assertion = database.record_assertion_answer(
        assertion_id=assertion_id,
        user_answer=None,
        is_favorite=True,
        answered_with_doubt=True,
    )
    if not updated_assertion:
        raise ValueError(f"Assertiva #{assertion_id} não encontrada.")

    conn = database.get_connection()
    bat_row = conn.execute(
        "SELECT title, subject FROM question_batteries WHERE id = ?",
        (updated_assertion["battery_id"],),
    ).fetchone()
    existing_summary = conn.execute(
        "SELECT * FROM student_error_summaries WHERE assertion_id = ? ORDER BY id DESC LIMIT 1",
        (assertion_id,),
    ).fetchone()
    conn.close()

    if existing_summary:
        return {
            "assertion": updated_assertion,
            "summary_record": dict(existing_summary),
            "already_queued": True,
        }

    subject = (dict(bat_row).get("subject") if bat_row else None) or "Disciplina Geral"
    topic = (dict(bat_row).get("title") if bat_row else None) or "Tópico do Material"
    subtopic = updated_assertion.get("subtopic") or "Subtópico Geral"
    trap = updated_assertion.get("trap_type") or "Distinção Conceitual"
    concept = f"{subtopic} — {trap}"
    subconcept = f"Revisão por Dúvida ({trap})"
    quote_or_exp = (
        updated_assertion.get("pdf_quote")
        or updated_assertion.get("explanation")
        or updated_assertion.get("statement", "")
    )
    auto_summary = (
        student_doubt_note.strip()
        if student_doubt_note.strip()
        else f"[Marcado com Dúvida para Fixação em 3 Dias] Gabarito Oficial: {updated_assertion['answer']}. {updated_assertion.get('explanation', '')}"
    )

    summary_record = create_student_error_summary_note(
        topic=topic,
        subtopic=subtopic,
        concept=concept,
        subconcept=subconcept,
        student_summary=auto_summary,
        personal_notes="Item marcado com 'Acertei/Respondi com Dúvida' durante resolução de bateria.",
        presented_concept_context=quote_or_exp,
        subject=subject,
        material_id=updated_assertion.get("material_id"),
        assertion_id=assertion_id,
        trap_type=trap,
        pdf_page=updated_assertion.get("pdf_page") or "p. 1",
        review_interval_days=REVIEW_INTERVAL_DAYS,
        nosql_store=nosql_store,
    )

    return {
        "assertion": updated_assertion,
        "summary_record": summary_record,
        "already_queued": False,
    }


# ===========================================================================
# MELHORIA 3: GERADOR DE PARES CONTRASTIVOS ("BATALHA DE SUBCONCEITOS CONFUNDÍVEIS")
# ===========================================================================

CLASSIC_CEBRASPE_CONTRASTIVE_PAIRS: List[Dict[str, str]] = [
    {
        "pair_id": "anulacao_vs_revogacao",
        "subject": "Direito Administrativo",
        "topic": "Extinção dos Atos Administrativos",
        "concept_a": "Anulação",
        "concept_b": "Revogação",
        "rule_a": "decorre de vício de ilegalidade/legitimidade, opera efeitos retroativos (ex tunc), incide sobre atos vinculados ou discricionários e pode ser decretada tanto pela Administração quanto pelo Poder Judiciário",
        "rule_b": "decorre de juízo de mérito (conveniência e oportunidade), opera efeitos prospectivos (ex nunc), incide apenas sobre atos discricionários válidos e é privativa da Administração Pública que praticou o ato",
        "reference": "Súmula 473 do STF e Art. 53 da Lei 9.784/1999",
    },
    {
        "pair_id": "cassacao_vs_caducidade",
        "subject": "Direito Administrativo",
        "topic": "Extinção dos Atos Administrativos",
        "concept_a": "Cassação",
        "concept_b": "Caducidade",
        "rule_a": "extingue o ato administrativo válido porque o próprio particular beneficiário descumpriu os requisitos legais que deveria manter para continuar usufruindo da situação (ex: perda de CNH para dirigir veículo oficial)",
        "rule_b": "extingue o ato administrativo válido em razão da superveniência de nova legislação que torna jurídica ou materialmente inadmissível a atividade antes permitida no momento da edição do ato",
        "reference": "Doutrina Clássica e Jurisprudência Cebraspe",
    },
    {
        "pair_id": "urgencia_vs_evidencia",
        "subject": "Direito Processual Civil",
        "topic": "Tutela Provisória (CPC)",
        "concept_a": "Tutela de Urgência",
        "concept_b": "Tutela da Evidência",
        "rule_a": "exige a demonstração cumulativa da probabilidade do direito (fumus boni iuris) e do perigo de dano ou risco ao resultado útil do processo (periculum in mora), podendo ter natureza cautelar ou antecipada",
        "rule_b": "independe da demonstração de perigo de dano ou de risco ao resultado útil do processo, sendo concedida quando o direito da parte se mostra evidente nas hipóteses taxativas do art. 311 do CPC",
        "reference": "Arts. 300 e 311 do Código de Processo Civil",
    },
    {
        "pair_id": "dispensa_vs_inexigibilidade",
        "subject": "Direito Administrativo",
        "topic": "Contratação Direta (Lei 14.133/2021)",
        "concept_a": "Inexigibilidade de Licitação",
        "concept_b": "Dispensa de Licitação",
        "rule_a": "configura-se sempre que houver inviabilidade de competição (rol exemplificativo do art. 74 da Lei 14.133/2021), como fornecedor exclusivo, notória especialização ou contratação de profissional do setor artístico",
        "rule_b": "ocorre em situações em que a competição seria teoricamente viável, mas a lei autoriza a não realização do certame em hipóteses taxativas (art. 75 da Lei 14.133/2021), como baixo valor ou emergência",
        "reference": "Arts. 74 e 75 da Lei 14.133/2021",
    },
]


def list_contrastive_concept_pairs() -> List[Dict[str, Any]]:
    """Lista os pares contrastivos clássicos da Cebraspe e pares dinâmicos extraídos da árvore do aluno."""
    init_spaced_review_tables()
    pairs: List[Dict[str, Any]] = list(CLASSIC_CEBRASPE_CONTRASTIVE_PAIRS)

    conn = database.get_connection()
    rows = conn.execute("SELECT * FROM concept_hierarchy_links ORDER BY id DESC").fetchall()
    conn.close()

    # Se o aluno tiver conceitos salvos com "vs", "e" ou múltiplos conceitos no mesmo subtópico, adiciona como par dinâmico
    by_subtopic: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        d = dict(r)
        by_subtopic.setdefault(d["subtopic"], []).append(d)

    for sub, links in by_subtopic.items():
        if len(links) >= 2:
            a, b = links[0], links[1]
            pairs.append(
                {
                    "pair_id": f"custom_{a['id']}_{b['id']}",
                    "subject": a["subject"],
                    "topic": a["topic"],
                    "concept_a": a["concept"],
                    "concept_b": b["concept"],
                    "rule_a": f"aplica-se especificamente ao subconceito '{a.get('subconcept') or a['concept']}' dentro de {sub}",
                    "rule_b": f"aplica-se especificamente ao subconceito '{b.get('subconcept') or b['concept']}' dentro de {sub}",
                    "reference": f"Árvore Conceitual do Aluno ({sub})",
                }
            )

    return pairs


def generate_contrastive_concept_battle_battery(
    pair_id: Optional[str] = None,
    questions_count: int = 8,
) -> Dict[str, Any]:
    """
    Gera uma Bateria de 'Batalha de Subconceitos Confundíveis' (Pares Contrastivos Cebraspe),
    confrontando Conceito A vs. Conceito B com assertivas de definição cruzada (Erradas)
    e distinção exata (Certas) para blindar o aluno contra a armadilha de Inversão de Conceito!
    """
    all_pairs = list_contrastive_concept_pairs()
    selected_pairs = (
        [p for p in all_pairs if p["pair_id"] == pair_id] if pair_id else all_pairs
    )
    if not selected_pairs:
        selected_pairs = list(CLASSIC_CEBRASPE_CONTRASTIVE_PAIRS)

    target_qty = max(4, int(questions_count or 8))
    assertions: List[Dict[str, Any]] = []
    idx = 0

    while len(assertions) < target_qty:
        pair = selected_pairs[idx % len(selected_pairs)]
        ca = pair["concept_a"]
        cb = pair["concept_b"]
        ra = pair["rule_a"]
        rb = pair["rule_b"]
        topic = pair["topic"]
        ref = pair["reference"]
        mode = len(assertions) % 4

        cmd = (
            f"[Batalha de Pares Contrastivos Cebraspe: {ca} vs. {cb}] "
            f"No que concerne a {topic}, julgue o item a seguir."
        )

        if mode == 0:
            # ERRADO: Atribui a definição de B ao conceito A (Inversão Clássica Cebraspe)
            assertions.append(
                {
                    "subtopic": f"{ca} vs. {cb}",
                    "recurrence_level": "Muito Alta",
                    "command_text": cmd,
                    "statement": f"No âmbito de {topic}, o instituto da {ca.lower()} caracteriza-se pelo fato de que {rb}.",
                    "answer": "E",
                    "explanation": (
                        f"ITEM ERRADO. Pegadinha clássica de INVERSÃO DE CONCEITO! O enunciado descreveu a **{cb}** "
                        f"({rb}), mas trocou o nome pelo instituto da **{ca}** ({ra})."
                    ),
                    "pdf_quote": f"{ca}: {ra}. | {cb}: {rb}.",
                    "pdf_page": ref,
                    "trap_type": f"Inversão de Par Contrastivo ({ca} ↔ {cb})",
                    "difficulty": "Média",
                    "inspired_by_real_question": f"Batalha Contrastiva: {ca} vs. {cb}",
                }
            )
        elif mode == 1:
            # CERTO: Distinção exata entre A e B lado a lado
            assertions.append(
                {
                    "subtopic": f"{ca} vs. {cb}",
                    "recurrence_level": "Muito Alta",
                    "command_text": cmd,
                    "statement": (
                        f"Distinguem-se tecnicamente os institutos de {ca.lower()} e {cb.lower()}: "
                        f"enquanto na {ca.lower()} verifica-se que {ra}, na {cb.lower()} constata-se que {rb}."
                    ),
                    "answer": "C",
                    "explanation": (
                        f"ITEM CERTO. A assertiva apresenta com precisão cirúrgica a distinção entre **{ca}** "
                        f"e **{cb}** segundo a referência ({ref})."
                    ),
                    "pdf_quote": f"{ca}: {ra}. | {cb}: {rb}.",
                    "pdf_page": ref,
                    "trap_type": "Distinção Conceitual Exata",
                    "difficulty": "Média",
                    "inspired_by_real_question": f"Batalha Contrastiva: {ca} vs. {cb}",
                }
            )
        elif mode == 2:
            # ERRADO: Atribui a definição de A ao conceito B
            assertions.append(
                {
                    "subtopic": f"{ca} vs. {cb}",
                    "recurrence_level": "Muito Alta",
                    "command_text": cmd,
                    "statement": f"Configura-se a hipótese de {cb.lower()} quando {ra}.",
                    "answer": "E",
                    "explanation": (
                        f"ITEM ERRADO. Houve inversão direta: a hipótese em que {ra} corresponde a **{ca}**, "
                        f"e não a **{cb}** ({rb})."
                    ),
                    "pdf_quote": f"{ca}: {ra}. | {cb}: {rb}.",
                    "pdf_page": ref,
                    "trap_type": f"Inversão de Par Contrastivo ({cb} ↔ {ca})",
                    "difficulty": "Difícil",
                    "inspired_by_real_question": f"Batalha Contrastiva: {ca} vs. {cb}",
                }
            )
        else:
            # CERTO: Afirmação verdadeira focada no Conceito B em contraste com A
            assertions.append(
                {
                    "subtopic": f"{ca} vs. {cb}",
                    "recurrence_level": "Alta",
                    "command_text": cmd,
                    "statement": (
                        f"Diferentemente do que ocorre em sede de {ca.lower()}, no instituto de {cb.lower()} "
                        f"observa-se que {rb}."
                    ),
                    "answer": "C",
                    "explanation": (
                        f"ITEM CERTO. A assertiva delimita corretamente o regime próprio de **{cb}** ({rb}), "
                        f"sem confundi-lo com **{ca}**."
                    ),
                    "pdf_quote": f"{cb}: {rb}.",
                    "pdf_page": ref,
                    "trap_type": "Contraste Conceitual Direto",
                    "difficulty": "Média",
                    "inspired_by_real_question": f"Batalha Contrastiva: {ca} vs. {cb}",
                }
            )

        idx += 1

    first_p = selected_pairs[0]
    title_label = (
        f"Batalha Contrastiva: {first_p['concept_a']} vs. {first_p['concept_b']}"
        if len(selected_pairs) == 1
        else f"Batalha de Pares Contrastivos Cebraspe ({len(assertions)} Itens)"
    )

    battery_id = database.save_question_battery(
        material_id=None,
        title=title_label,
        subject=first_p["subject"],
        area="Revisão Contrastiva Anti-Pegadinha",
        depth="Confronto Direto de Subconceitos Confundíveis",
        recurrence_summary=[],
        assertions=assertions[:target_qty],
    )
    return {
        "battery_id": battery_id,
        "pairs_used": selected_pairs,
        "battery": database.get_battery(battery_id),
    }


