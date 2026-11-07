"""
Módulo de Mentoria Adaptativa, Resumo Direcionado e Questão Discursiva de 5 Linhas (`adaptive_tutor.py`).

A partir do PDF armazenado no banco (SQL + NoSQL):
1. Avalia onde o usuário está errando mais (subtópicos, conceitos e tipos de pegadinhas Cebraspe);
2. Apresenta um resumo estruturado do conteúdo extraído do PDF armazenado sobre esses pontos críticos;
3. Gera mais questões inéditas de fixação a partir dos períodos do PDF armazenado;
4. Elabora uma questão discursiva de até 5 linhas no estilo Cebraspe sobre o conceito em que o aluno
   tem errado, permitindo que o aluno digite a resposta na plataforma e salvando a resposta e a
   avaliação no banco de dados (SQL + NoSQL).
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

import database
from storage_manager import (
    NoSQLDocumentStore,
    get_material_knowledge_tree_nosql,
    init_storage_tables,
    list_stored_files,
)
from topic_parser import (
    extract_assertions_from_subtopics,
    parse_pdf_topics_and_subtopics,
)


class DiscursiveEvaluationSchema(BaseModel):
    score: float = Field(description="Nota atribuída à resposta discursiva de 5 linhas (de 0.0 a 10.0)")
    feedback_text: str = Field(description="Parecer técnico de correção no padrão Cebraspe, incluindo sugestão de redação ideal em até 5 linhas")
    covered_points: List[str] = Field(description="Quesitos do espelho de correção que o aluno abordou corretamente")
    missing_points: List[str] = Field(description="Quesitos ou conceitos essenciais que faltaram ou foram confundidos na resposta")


def _extract_keywords(text: str) -> List[str]:
    stopwords = {
        "para", "como", "pelo", "pela", "pelos", "pelas", "sobre", "entre", "quando", "onde",
        "qual", "quais", "este", "esta", "isso", "aquele", "aquela", "deve", "pode", "sendo",
        "caso", "casos", "forma", "modo", "meio", "área", "item", "itens", "regra", "geral",
    }
    words = re.findall(r"[a-záéíóúâêôãõç]{5,}", text.lower())
    seen = set()
    out = []
    for w in words:
        if w not in stopwords and w not in seen:
            seen.add(w)
            out.append(w)
    return out[:12]


def save_discursive_question(
    material_id: Optional[int],
    subject: str,
    subtopic: str,
    target_concept: str,
    trap_type: str,
    prompt_text: str,
    expected_key_points: List[str],
    pdf_reference_quote: str,
    pdf_page: str,
    max_lines: int = 5,
) -> Dict[str, Any]:
    init_storage_tables()
    conn = database.get_connection()
    cur = conn.cursor()
    now = datetime.now().isoformat()
    cur.execute(
        """
        INSERT INTO discursive_questions (
            material_id, subject, subtopic, target_concept, trap_type, prompt_text,
            max_lines, expected_key_points_json, pdf_reference_quote, pdf_page, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            material_id,
            subject,
            subtopic,
            target_concept,
            trap_type,
            prompt_text,
            max_lines,
            json.dumps(expected_key_points, ensure_ascii=False),
            pdf_reference_quote,
            pdf_page,
            now,
        ),
    )
    q_id = int(cur.lastrowid)
    conn.commit()
    conn.close()

    return {
        "id": q_id,
        "material_id": material_id,
        "subject": subject,
        "subtopic": subtopic,
        "target_concept": target_concept,
        "trap_type": trap_type,
        "prompt_text": prompt_text,
        "max_lines": max_lines,
        "expected_key_points": expected_key_points,
        "pdf_reference_quote": pdf_reference_quote,
        "pdf_page": pdf_page,
        "created_at": now,
    }


def get_discursive_question(question_id: int) -> Optional[Dict[str, Any]]:
    init_storage_tables()
    conn = database.get_connection()
    row = conn.execute("SELECT * FROM discursive_questions WHERE id = ?", (question_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["expected_key_points"] = json.loads(d.pop("expected_key_points_json", "[]"))
    return d


def build_weakness_diagnosis_and_study_plan(
    material_id: Optional[int] = None,
    nosql_store: Optional[NoSQLDocumentStore] = None,
) -> Dict[str, Any]:
    """
    A partir do PDF armazenado no banco (SQL + NoSQL):
    1. Identifica onde o aluno está errando mais (subtópicos, conceitos e pegadinhas);
    2. Gera um Resumo Direcionado do Conteúdo com base nas páginas/períodos do PDF armazenado;
    3. Cria e persiste uma Questão Discursiva de 5 linhas sobre o conceito que o aluno tem errado.
    """
    init_storage_tables()
    store = nosql_store or NoSQLDocumentStore()

    # Selecionar o material armazenado (ou o último material salvo caso material_id seja None)
    materials = database.list_study_materials()
    target_mat: Optional[Dict[str, Any]] = None
    if material_id is not None:
        target_mat = database.get_study_material(material_id)
    elif materials:
        target_mat = database.get_study_material(materials[0]["id"])

    if not target_mat:
        # Se ainda não houver PDF salvo, cria o material demonstrativo automaticamente
        import main

        demo_bat = main.create_demo_battery()
        target_mat = database.get_study_material(demo_bat["material_id"])

    assert target_mat is not None
    mat_id = int(target_mat["id"])
    subject = target_mat.get("subject", "Disciplina")
    title = target_mat.get("title", "Material de Estudo")
    pages = target_mat.get("pages", [])

    # Carregar árvore de períodos do NoSQL ou parsear agora e salvar no NoSQL
    nosql_tree = get_material_knowledge_tree_nosql(mat_id, nosql_store=store)
    if nosql_tree and nosql_tree.get("parsed_topics"):
        parsed_topics = nosql_tree["parsed_topics"]
    else:
        parsed_topics = parse_pdf_topics_and_subtopics(pages)
        store.upsert_document(
            "pdf_knowledge_trees",
            str(mat_id),
            {
                "material_id": mat_id,
                "title": title,
                "subject": subject,
                "parsed_topics": parsed_topics,
            },
        )

    # Consultar respostas e erros do usuário no SQL
    conn = database.get_connection()
    wrong_rows = conn.execute(
        """
        SELECT a.* FROM assertions a
        WHERE a.material_id = ? AND (a.is_correct = 0 OR a.is_favorite = 1)
        ORDER BY a.is_correct ASC, a.answered_at DESC
        """,
        (mat_id,),
    ).fetchall()

    if not wrong_rows:
        # Se o usuário errou em outra bateria da mesma matéria ou geral, buscar globalmente
        wrong_rows = conn.execute(
            """
            SELECT a.* FROM assertions a
            WHERE a.is_correct = 0 OR a.is_favorite = 1
            ORDER BY a.is_correct ASC, a.answered_at DESC
            LIMIT 15
            """
        ).fetchall()

    subtopic_error_rows = conn.execute(
        """
        SELECT
            subtopic,
            COUNT(*) as total_answered,
            SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as correct,
            SUM(CASE WHEN is_correct = 0 AND user_answer != 'BLANK' THEN 1 ELSE 0 END) as wrong
        FROM assertions
        WHERE user_answer IS NOT NULL AND (material_id = ? OR ? IS NULL)
        GROUP BY subtopic
        ORDER BY wrong DESC, total_answered DESC
        """,
        (mat_id, mat_id),
    ).fetchall()
    conn.close()

    wrong_items = [dict(r) for r in wrong_rows]
    subtopic_stats = [dict(r) for r in subtopic_error_rows]

    # Determinar o subtópico e o conceito onde o aluno mais erra
    if wrong_items:
        top_wrong = wrong_items[0]
        weakest_subtopic = top_wrong.get("subtopic", "Conceitos Fundamentais")
        dominant_trap = top_wrong.get("trap_type", "Inversão de Conceito")
        critical_quote = top_wrong.get("pdf_quote") or top_wrong.get("explanation", "")
        critical_page = top_wrong.get("pdf_page", "p. 1")
        critical_explanation = top_wrong.get("explanation", "")
    elif parsed_topics:
        first_sec = parsed_topics[0]
        weakest_subtopic = first_sec["subtopic"]
        first_p = first_sec["periods"][0] if first_sec.get("periods") else {"text": title, "page_number": 1, "markers": ["Conceito"]}
        dominant_trap = (first_p.get("markers") or ["Inversão de Conceito"])[0]
        critical_quote = first_p["text"]
        critical_page = f"p. {first_p.get('page_number', 1)}"
        critical_explanation = (
            f"Ponto de altíssima incidência na Cebraspe dentro de {weakest_subtopic}: exige atenção redobrada à redação literal e às exceções."
        )
    else:
        weakest_subtopic = "Conceitos Nucleares do Tema"
        dominant_trap = "Inversão de Conceito"
        critical_quote = f"Estudo essencial sobre {title} em {subject}."
        critical_page = "p. 1"
        critical_explanation = "Dominar a diferença entre regra geral e exceções previstas no material."

    # Coletar todos os períodos relevantes do PDF armazenado para compor o Resumo do Conteúdo
    matching_periods: List[Dict[str, Any]] = []
    for sec in parsed_topics:
        if weakest_subtopic.lower() in sec["subtopic"].lower() or sec["subtopic"].lower() in weakest_subtopic.lower():
            matching_periods.extend(sec.get("periods", []))
    if not matching_periods:
        for sec in parsed_topics[:3]:
            matching_periods.extend(sec.get("periods", [])[:4])

    # Construir o Resumo Direcionado do Conteúdo onde o aluno mais erra
    summary_bullets: List[Dict[str, str]] = []
    for p_obj in matching_periods[:8]:
        summary_bullets.append(
            {
                "page": f"p. {p_obj.get('page_number', 1)}",
                "text": p_obj["text"],
                "focus": ", ".join(p_obj.get("markers", ["Conceito-Chave"])[:2]),
            }
        )

    for w in wrong_items[:4]:
        if w.get("pdf_quote") and not any(b["text"] == w["pdf_quote"] for b in summary_bullets):
            summary_bullets.append(
                {
                    "page": w.get("pdf_page", "p. 1"),
                    "text": w["pdf_quote"],
                    "focus": f"Pegadinha em que você caiu: {w.get('trap_type', 'Conceito')}",
                }
            )

    content_summary = {
        "target_subtopic": weakest_subtopic,
        "dominant_trap": dominant_trap,
        "errors_analyzed_count": len(wrong_items),
        "executive_overview": (
            f"Com base no seu histórico sobre '{title}' ({subject}), seu ponto de maior vulnerabilidade "
            f"concentra-se no subtópico '{weakest_subtopic}', especialmente diante da técnica Cebraspe de "
            f"'{dominant_trap}'. Abaixo está a síntese direta dos períodos do seu PDF armazenado para blindar esse tema."
        ),
        "golden_rule": critical_explanation,
        "key_periods_from_pdf": summary_bullets,
    }

    # Salvar diagnóstico e resumo no banco NoSQL
    store.upsert_document(
        "user_weakness_profiles",
        f"material_{mat_id}",
        {
            "material_id": mat_id,
            "subject": subject,
            "title": title,
            "weakest_subtopic": weakest_subtopic,
            "dominant_trap": dominant_trap,
            "subtopic_stats": subtopic_stats,
            "content_summary": content_summary,
        },
    )

    # Criar a Questão Discursiva de 5 Linhas sobre o conceito em que o aluno tem errado
    expected_points = [
        f"Definir corretamente a regra aplicável a '{weakest_subtopic}' conforme o PDF ({critical_page})",
        f"Explicar por que a armadilha de '{dominant_trap}' é incorreta na sistemática da matéria",
        f"Mencionar os elementos essenciais do texto-base: \"{critical_quote[:140]}...\"",
    ]

    discursive_prompt = (
        f"[PROVA DISCURSIVA CEBRASPE — MÁXIMO DE 5 LINHAS]\n"
        f"Considerando a disciplina de {subject} ({title}), redija um texto dissertativo objetivo, de até 5 linhas, "
        f"a respeito de **{weakest_subtopic}**, abordando necessariamente:\n"
        f"1. O conceito ou regra correta prevista no seu material de estudo ({critical_page});\n"
        f"2. O esclarecimento técnico sobre o ponto crítico em que houve erro ({dominant_trap}), distinguindo a regra verdadeira da pegadinha da banca."
    )

    discursive_q = save_discursive_question(
        material_id=mat_id,
        subject=subject,
        subtopic=weakest_subtopic,
        target_concept=f"{weakest_subtopic} ({dominant_trap})",
        trap_type=dominant_trap,
        prompt_text=discursive_prompt,
        expected_key_points=expected_points,
        pdf_reference_quote=critical_quote,
        pdf_page=critical_page,
        max_lines=5,
    )

    stored_files = list_stored_files(material_id=mat_id)

    return {
        "material_id": mat_id,
        "material_title": title,
        "subject": subject,
        "stored_files": stored_files,
        "weakness_stats": subtopic_stats,
        "wrong_assertions_sample": wrong_items[:6],
        "content_summary": content_summary,
        "discursive_question": discursive_q,
    }


def generate_more_fixation_questions_from_stored_pdf(
    material_id: int,
    target_subtopic: Optional[str] = None,
    variations_per_period: int = 3,
) -> Dict[str, Any]:
    """
    A partir do PDF armazenado no banco (SQL + NoSQL), extrai novas assertivas inéditas
    de Certo/Errado focadas nos subtópicos onde o aluno mais errou para fixar o conteúdo.
    """
    mat = database.get_study_material(material_id)
    if not mat:
        raise ValueError("Material não encontrado no banco.")

    pages = mat.get("pages", [])
    nosql_tree = get_material_knowledge_tree_nosql(material_id)
    parsed_topics = (
        nosql_tree["parsed_topics"]
        if nosql_tree and nosql_tree.get("parsed_topics")
        else parse_pdf_topics_and_subtopics(pages)
    )

    if target_subtopic:
        filtered_topics = [
            t
            for t in parsed_topics
            if target_subtopic.lower() in t["subtopic"].lower()
            or t["subtopic"].lower() in target_subtopic.lower()
        ]
        if not filtered_topics:
            filtered_topics = parsed_topics
    else:
        filtered_topics = parsed_topics

    assertions = extract_assertions_from_subtopics(
        structured_topics=filtered_topics,
        subject=mat.get("subject", "Disciplina"),
        area=mat.get("area", "Geral"),
        variations_per_period=max(2, min(3, variations_per_period)),
    )

    # Caso o PDF seja demonstrativo e curto, complementar com variações dos itens do próprio material
    if len(assertions) < 4:
        conn = database.get_connection()
        existing_rows = conn.execute(
            "SELECT * FROM assertions WHERE material_id = ? LIMIT 8", (material_id,)
        ).fetchall()
        conn.close()
        from gemini_service import generate_error_reinforcement

        extra = generate_error_reinforcement(
            wrong_assertions=[dict(r) for r in existing_rows],
            api_key="",
            questions_per_error=2,
        )
        assertions.extend(extra)

    battery_title = (
        f"Fixação Direcionada — {target_subtopic or mat.get('title', 'Conteúdo')}"
    )
    battery_id = database.save_question_battery(
        material_id=material_id,
        title=battery_title,
        subject=mat.get("subject", "Disciplina"),
        area=mat.get("area", "Geral"),
        depth="Fixação Intensiva a partir do PDF Armazenado",
        recurrence_summary=mat.get("recurrence_map", []),
        assertions=assertions,
    )
    res = database.get_battery(battery_id)
    assert res is not None
    return res


def submit_and_save_discursive_5lines_answer(
    question_id: int,
    student_text: str,
    api_key: str = "",
    model_name: str = "gemini-2.5-flash",
    nosql_store: Optional[NoSQLDocumentStore] = None,
) -> Dict[str, Any]:
    """
    Recebe a resposta discursiva de até 5 linhas digitada pelo aluno na plataforma,
    avalia o domínio do conceito em relação ao PDF armazenado e salva a resposta
    tanto no banco SQL (`discursive_responses`) quanto no banco NoSQL (`discursive_evaluations`).
    """
    init_storage_tables()
    store = nosql_store or NoSQLDocumentStore()

    q = get_discursive_question(question_id)
    if not q:
        raise ValueError(f"Questão discursiva #{question_id} não encontrada.")

    cleaned_text = student_text.strip()
    if not cleaned_text:
        raise ValueError("A resposta discursiva não pode estar em branco.")

    # Calcular número de linhas utilizadas (considerando quebras explícitas ou ~90 caracteres por linha padrão Cebraspe)
    explicit_lines = [ln for ln in cleaned_text.split("\n") if ln.strip()]
    estimated_lines_by_chars = max(1, (len(cleaned_text) + 89) // 90)
    lines_used = max(len(explicit_lines), estimated_lines_by_chars)
    char_count = len(cleaned_text)

    score = 0.0
    feedback_text = ""
    covered_points: List[str] = []
    missing_points: List[str] = []

    if api_key and api_key.strip():
        try:
            client = genai.Client(api_key=api_key.strip())
            prompt = f"""
Você é um Examinador de Prova Discursiva da banca **CEBRASPE (CESPE/UnB)**.
Avalie a resposta discursiva de até 5 linhas enviada pelo candidato.

- **Disciplina:** {q['subject']}
- **Subtópico / Conceito Alvo:** {q['target_concept']}
- **Comando da Questão:** {q['prompt_text']}
- **Trecho Oficial do PDF de Referência ({q['pdf_page']}):** "{q['pdf_reference_quote']}"
- **Quesitos Esperados no Espelho:** {json.dumps(q['expected_key_points'], ensure_ascii=False)}
- **Linhas utilizadas pelo candidato:** {lines_used} de {q['max_lines']} linhas permitidas.

### RESPOSTA DIGITADA PELO ALUNO:
\"\"\"{cleaned_text}\"\"\"

Atribua uma nota de 0.0 a 10.0, liste os pontos cobertos, os pontos faltantes e forneça um parecer construtivo com uma proposta de resposta padrão em até 5 linhas.
"""
            resp = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=DiscursiveEvaluationSchema,
                    temperature=0.2,
                ),
            )
            parsed = json.loads(resp.text)
            score = float(parsed.get("score", 8.0))
            feedback_text = parsed.get("feedback_text", "")
            covered_points = parsed.get("covered_points", [])
            missing_points = parsed.get("missing_points", [])
        except Exception:
            pass

    if not feedback_text:
        # Avaliador determinístico local baseado nos conceitos-chave do trecho do PDF
        ref_keywords = _extract_keywords(q["pdf_reference_quote"] + " " + q["subtopic"])
        student_lower = cleaned_text.lower()
        matched_kw = [kw for kw in ref_keywords if kw in student_lower]
        missed_kw = [kw for kw in ref_keywords if kw not in student_lower]

        coverage_ratio = len(matched_kw) / max(1, len(ref_keywords))
        length_bonus = 2.5 if 60 <= char_count <= 550 else 1.0
        line_penalty = 1.5 if lines_used > q["max_lines"] else 0.0

        raw_score = min(10.0, max(2.0, round((coverage_ratio * 7.5) + length_bonus - line_penalty, 1)))
        score = raw_score

        if matched_kw:
            covered_points.append(
                f"Abordou termos/conceitos nucleares do material: {', '.join(matched_kw[:6])}"
            )
        if 1 <= lines_used <= q["max_lines"]:
            covered_points.append(
                f"Respeitou o limite máximo de {q['max_lines']} linhas da Cebraspe ({lines_used} linha(s) utilizada(s))."
            )
        else:
            missing_points.append(
                f"Atenção ao limite de espaço: sua resposta ocupou aproximadamente {lines_used} linhas (o limite é de {q['max_lines']} linhas)."
            )

        if missed_kw:
            missing_points.append(
                f"Termos técnicos do trecho-base ({q['pdf_page']}) que poderiam enriquecer a resposta: {', '.join(missed_kw[:5])}."
            )

        feedback_text = (
            f"Avaliação Cebraspe (5 Linhas) — Nota: {score}/10.0. "
            f"Sua resposta foi salva com sucesso no banco de dados! "
            f"Espelho de Referência ({q['pdf_page']}): \"{q['pdf_reference_quote']}\""
        )

    now = datetime.now().isoformat()
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO discursive_responses (
            question_id, material_id, student_text, lines_used, char_count,
            score, feedback_text, covered_points_json, missing_points_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            question_id,
            q.get("material_id"),
            cleaned_text,
            lines_used,
            char_count,
            score,
            feedback_text,
            json.dumps(covered_points, ensure_ascii=False),
            json.dumps(missing_points, ensure_ascii=False),
            now,
        ),
    )
    response_id = int(cur.lastrowid)
    conn.commit()
    conn.close()

    saved_record = {
        "response_id": response_id,
        "question_id": question_id,
        "material_id": q.get("material_id"),
        "subject": q["subject"],
        "subtopic": q["subtopic"],
        "target_concept": q["target_concept"],
        "prompt_text": q["prompt_text"],
        "student_text": cleaned_text,
        "lines_used": lines_used,
        "max_lines": q["max_lines"],
        "char_count": char_count,
        "score": score,
        "feedback_text": feedback_text,
        "covered_points": covered_points,
        "missing_points": missing_points,
        "pdf_reference_quote": q["pdf_reference_quote"],
        "pdf_page": q["pdf_page"],
        "created_at": now,
    }

    # Persistir também no banco NoSQL de avaliações discursivas
    store.upsert_document("discursive_evaluations", str(response_id), saved_record)
    return saved_record


def list_saved_discursive_responses(material_id: Optional[int] = None) -> List[Dict[str, Any]]:
    init_storage_tables()
    conn = database.get_connection()
    if material_id is not None:
        rows = conn.execute(
            """
            SELECT r.*, q.subject, q.subtopic, q.target_concept, q.prompt_text, q.pdf_reference_quote, q.pdf_page
            FROM discursive_responses r
            JOIN discursive_questions q ON r.question_id = q.id
            WHERE r.material_id = ?
            ORDER BY r.id DESC
            """,
            (material_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT r.*, q.subject, q.subtopic, q.target_concept, q.prompt_text, q.pdf_reference_quote, q.pdf_page
            FROM discursive_responses r
            JOIN discursive_questions q ON r.question_id = q.id
            ORDER BY r.id DESC
            """
        ).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        d["covered_points"] = json.loads(d.pop("covered_points_json", "[]"))
        d["missing_points"] = json.loads(d.pop("missing_points_json", "[]"))
        result.append(d)
    return result

