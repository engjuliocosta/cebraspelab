import json
import re
from typing import Any, Dict, List, Optional
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from topic_parser import (
    extract_assertions_from_subtopics,
    parse_pdf_topics_and_subtopics,
)


class SubtopicRecurrenceSchema(BaseModel):
    topic: str = Field(default="Tópico Geral", description="Tópico principal ao qual o subtópico pertence")
    subtopic: str = Field(description="Nome claro e específico do subtópico encontrado no PDF")
    recurrence_level: str = Field(description="Nível de recorrência na Cebraspe: 'Muito Alta', 'Alta', 'Média' ou 'Baixa'")
    recurrence_percentage: int = Field(description="Peso percentual estimado de cobrança deste subtópico na Cebraspe (soma total ~100)")
    real_questions_found: int = Field(description="Quantidade de questões reais da Cebraspe encontradas no material sobre este subtópico")
    periods_count: int = Field(default=0, description="Quantidade de períodos normativos/conceituais extraídos deste subtópico")
    min_recommended_questions: int = Field(description="Número mínimo recomendado de assertivas inéditas a gerar para cobrir este subtópico com segurança")
    pages_reference: str = Field(description="Intervalo ou lista de páginas do PDF onde este subtópico aparece, ex: 'p. 2-6'")
    cebraspe_focus_points: List[str] = Field(description="2 a 4 pontos exatos ou pegadinhas clássicas que a Cebraspe mais cobra neste subtópico")


class PDFAnalysisResponseSchema(BaseModel):
    detected_subject: str = Field(description="Matéria ou disciplina principal identificada no PDF")
    detected_title: str = Field(description="Título resumido do tema/assunto da aula ou PDF")
    total_real_questions_detected: int = Field(description="Total de questões reais da Cebraspe identificadas no material")
    analysis_summary: str = Field(description="Resumo executivo do perfil de cobrança da Cebraspe para este tema e área de concurso")
    subtopics: List[SubtopicRecurrenceSchema]
    extracted_real_questions: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Amostra estruturada de questões reais da Cebraspe identificadas no texto (com exam_info, subtopic, statement, answer)",
    )


class GeneratedAssertionSchema(BaseModel):
    subtopic: str = Field(description="Subtópico ao qual a assertiva pertence")
    recurrence_level: str = Field(description="Nível de recorrência do subtópico ('Muito Alta', 'Alta', 'Média', 'Baixa')")
    command_text: str = Field(description="Comando estilo Cebraspe que introduz o bloco de itens, ex: 'Acerca de..., julgue o item a seguir.'")
    statement: str = Field(description="Texto da assertiva inédita no padrão rigoroso Cebraspe (Certo/Errado)")
    answer: str = Field(description="Gabarito oficial: 'C' para Certo ou 'E' para Errado")
    explanation: str = Field(description="Gabarito comentado detalhado explicando exatamente o erro (pegadinha) ou a confirmação do acerto")
    pdf_quote: str = Field(description="Trecho exato ou período fiel do PDF de estudo que fundamenta o gabarito")
    pdf_page: str = Field(description="Número da página do PDF de onde saiu a fundamentação, ex: 'p. 4'")
    trap_type: str = Field(
        description="Tipo de técnica Cebraspe aplicada: 'Inversão de Conceito', 'Modalizador (Deve vs. Pode)', 'Termo Restritivo / Absoluto', 'Regra Geral vs. Exceção', 'Verdade Parcial + Conclusão Falsa', 'Situação Hipotética', 'Jurisprudência / Doutrina' ou 'Literalidade / Conceito Exato'"
    )
    difficulty: str = Field(description="Nível de dificuldade: 'Fácil', 'Média' ou 'Difícil'")
    inspired_by_real_question: str = Field(
        description="Indicação da questão real da Cebraspe ou período do subtópico que inspirou esta assertiva"
    )


class GeneratedBatteryResponseSchema(BaseModel):
    assertions: List[GeneratedAssertionSchema]


AREA_GUIDELINES = {
    "Geral": "Equilíbrio clássico da Cebraspe entre literalidade normativa/conceitual (50%), aplicação de conceitos (30%) e casos práticos/exceções (20%).",
    "Policial": "Foco intenso em literalidade de leis/conceitos nucleares, distinções conceituais diretas, prazos/requisitos e situações operacionais curtas.",
    "Tribunais / Jurídico": "Forte cobrança de exceções legais, distinções doutrinárias finas, jurisprudência consolidada (STF/STJ) e situações hipotéticas ('Considere que...').",
    "Controle / Fiscal": "Alta densidade técnica, situações hipotéticas complexas, entendimento do TCU/jurisprudência, exceções e cruzamento de conceitos.",
    "TI (Tecnologia da Informação)": "Comparação rigorosa entre protocolos/arquiteturas/algoritmos, troca sutil de camadas ou responsabilidades de ferramentas e cenários práticos de engenharia/segurança.",
    "Administrativo": "Foco nos conceitos mais recorrentes (Pareto 80/20), classificações, atributos, competências e troca de termos correlatos.",
}


def _build_pdf_context(pages: List[Dict[str, Any]], max_chars: int = 160000) -> str:
    chunks = []
    current_len = 0
    for p in pages:
        chunk = f"\n--- [Página {p['page_number']}] ({p.get('source_file', 'PDF')}) ---\n{p['text']}\n"
        if current_len + len(chunk) > max_chars:
            remaining = max_chars - current_len
            if remaining > 500:
                chunks.append(chunk[:remaining] + "\n...[Texto truncado por limite]...")
            break
        chunks.append(chunk)
        current_len += len(chunk)
    return "".join(chunks)


def test_gemini_connection(api_key: str, model_name: str = "gemini-2.5-flash") -> Dict[str, Any]:
    if not api_key or not api_key.strip():
        return {"ok": False, "message": "Chave de API vazia. Insira sua GEMINI_API_KEY."}
    try:
        client = genai.Client(api_key=api_key.strip())
        resp = client.models.generate_content(
            model=model_name,
            contents="Responda apenas com a palavra: CONECTADO",
        )
        return {
            "ok": True,
            "message": f"Conectado com sucesso ao modelo {model_name}!",
            "response": (resp.text or "").strip(),
        }
    except Exception as e:
        return {"ok": False, "message": f"Erro ao conectar na API Gemini: {str(e)}"}


def analyze_pdf_recurrence(
    pages: List[Dict[str, Any]],
    heuristic_questions: List[Dict[str, Any]],
    area: str,
    api_key: str,
    model_name: str = "gemini-2.5-flash",
    custom_subject_hint: str = "",
) -> Dict[str, Any]:
    """
    Analisa o PDF de estudo + questões reais encontradas + períodos parseados por tópico/subtópico
    e retorna o Raio-X de Recorrência da Cebraspe, calculando o número mínimo recomendado de assertivas.
    """
    parsed_topics = parse_pdf_topics_and_subtopics(pages)

    if not api_key or not api_key.strip():
        return _fallback_analyze_pdf_recurrence(
            pages, heuristic_questions, area, custom_subject_hint, parsed_topics=parsed_topics
        )

    pdf_context = _build_pdf_context(pages, max_chars=160000)
    questions_context = json.dumps(heuristic_questions[:60], ensure_ascii=False, indent=2)
    topics_summary = json.dumps(
        [
            {
                "topic": t["topic"],
                "subtopic": t["subtopic"],
                "pages_reference": t["pages_reference"],
                "periods_count": t["periods_count"],
                "sample_periods": [p["text"] for p in t["periods"][:4]],
            }
            for t in parsed_topics[:15]
        ],
        ensure_ascii=False,
        indent=2,
    )
    area_desc = AREA_GUIDELINES.get(area, AREA_GUIDELINES["Geral"])

    prompt = f"""
Você é um Especialista Sênior em Estatística de Provas e Engenharia Reversa da banca CEBRASPE (CESPE/UnB).
Sua tarefa é analisar o material em PDF abaixo, os tópicos/subtópicos e períodos sintáticos extraídos, e as questões reais da Cebraspe para a área: **{area}** ({area_desc}).
{f'Dica de disciplina informada pelo usuário: {custom_subject_hint}' if custom_subject_hint else ''}

### O QUE VOCÊ DEVE FAZER:
1. Identificar a **Disciplina/Matéria** (`detected_subject`) e o **Título do Assunto/Aula** (`detected_title`).
2. Mapear os **Tópicos e Subtópicos** do PDF (use os tópicos e subtópicos pré-parseados abaixo como base para não perder nenhuma seção!).
3. Para cada subtópico, determinar:
   - `topic`: Tópico pai ao qual o subtópico pertence.
   - `subtopic`: Nome claro do subtópico.
   - `recurrence_level`: `'Muito Alta'`, `'Alta'`, `'Média'` ou `'Baixa'` na Cebraspe.
   - `recurrence_percentage`: Percentual estimado de cobrança (soma ~100).
   - `real_questions_found`: Quantas questões reais da Cebraspe no material abordam este subtópico.
   - `periods_count`: Quantidade de períodos analisáveis encontrados neste subtópico.
   - `min_recommended_questions`: O **NÚMERO MÍNIMO RECOMENDADO DE ASSERTIVAS INÉDITAS** combinando a recorrência Cebraspe e a riqueza de períodos do subtópico (garanta múltiplas questões por subtópico: ex. 8 a 14 em 'Muito Alta', 6 a 10 em 'Alta', 4 a 6 em 'Média', 2 a 4 em 'Baixa').
   - `pages_reference`: Páginas do PDF (ex: `'p. 1-4'`).
   - `cebraspe_focus_points`: 2 a 4 pontos específicos ou pegadinhas que a Cebraspe mais cobra nesse subtópico.

### TÓPICOS, SUBTÓPICOS E PERÍODOS PRÉ-PARSEADOS DO PDF:
{topics_summary}

### QUESTÕES REAIS PREVIAMENTE DETECTADAS POR REGEX ({len(heuristic_questions)} encontradas):
{questions_context}

### CONTEÚDO DAS PÁGINAS DO PDF:
{pdf_context}
"""

    try:
        client = genai.Client(api_key=api_key.strip())
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PDFAnalysisResponseSchema,
                temperature=0.2,
            ),
        )
        parsed = json.loads(response.text)
        parsed["parsed_topics"] = parsed_topics
        return parsed
    except Exception as e:
        fallback = _fallback_analyze_pdf_recurrence(
            pages, heuristic_questions, area, custom_subject_hint, parsed_topics=parsed_topics
        )
        fallback["analysis_summary"] += f" (Nota: Análise gerada pelo motor de parseamento de períodos local devido a: {str(e)[:120]})"
        return fallback


def generate_cebraspe_assertions(
    pages: List[Dict[str, Any]],
    real_questions: List[Dict[str, Any]],
    subtopic_plan: List[Dict[str, Any]],
    subject: str,
    title: str,
    area: str,
    depth: str,
    api_key: str,
    model_name: str = "gemini-2.5-flash",
) -> List[Dict[str, Any]]:
    """
    Gera a bateria de assertivas inéditas no estilo Cebraspe seguindo rigorosamente a quantidade
    de cada subtópico definida pelo mapa de recorrência e utilizando os períodos extraídos de cada subtópico.
    """
    active_plan = [s for s in subtopic_plan if int(s.get("target_questions", s.get("min_recommended_questions", 0))) > 0]
    total_requested = sum(int(s.get("target_questions", s.get("min_recommended_questions", 3))) for s in active_plan)

    if not api_key or not api_key.strip():
        return _fallback_generate_assertions(pages, real_questions, active_plan, subject, title, area)

    parsed_topics = parse_pdf_topics_and_subtopics(pages)
    periods_by_subtopic = json.dumps(
        [
            {
                "topic": t["topic"],
                "subtopic": t["subtopic"],
                "pages": t["pages_reference"],
                "periods": [p["text"] for p in t["periods"][:15]],
            }
            for t in parsed_topics[:15]
        ],
        ensure_ascii=False,
        indent=2,
    )

    pdf_context = _build_pdf_context(pages, max_chars=140000)
    few_shot_questions = json.dumps(real_questions[:35], ensure_ascii=False, indent=2)
    plan_json = json.dumps(
        [
            {
                "topic": s.get("topic", "Tópico Principal"),
                "subtopic": s["subtopic"],
                "recurrence_level": s.get("recurrence_level", "Alta"),
                "exact_questions_to_generate": int(s.get("target_questions", s.get("min_recommended_questions", 3))),
                "pages_reference": s.get("pages_reference", ""),
                "cebraspe_focus_points": s.get("cebraspe_focus_points", []),
            }
            for s in active_plan
        ],
        ensure_ascii=False,
        indent=2,
    )
    area_desc = AREA_GUIDELINES.get(area, AREA_GUIDELINES["Geral"])

    prompt = f"""
Você é um Examinador Titular da banca **CEBRASPE (CESPE/UnB)** elaborando itens inéditos de **CERTO ou ERRADO** baseados nos períodos de cada tópico e subtópico do PDF de estudo fornecido e calibrados pela recorrência histórica da banca.

### PARÂMETROS DA PROVA:
- **Matéria / Disciplina:** {subject}
- **Tema / Aula:** {title}
- **Área do Concurso:** {area} ({area_desc})
- **Nível de Profundidade:** {depth}
- **Total Exato de Assertivas a Gerar:** {total_requested} itens

### DISTRIBUIÇÃO OBRIGATÓRIA POR SUBTÓPICO (BASEADA NA RECORRÊNCIA CEBRASPE E NOS PERÍODOS):
Você DEVE gerar exatamente a quantidade solicitada (`exact_questions_to_generate`) para cada subtópico abaixo, utilizando os períodos de cada tópico/subtópico para extrair múltiplas variações de Certo e Errado:
{plan_json}

### PERÍODOS EXTRAÍDOS DE CADA TÓPICO E SUBTÓPICO DO PDF:
{periods_by_subtopic}

### DIRETRIZES RIGOROSAS DE ESTILO CEBRASPE:
1. **Proporção de Gabarito:** Mantenha equilíbrio próximo de **50% CERTO ('C') e 50% ERRADO ('E')** dentro de cada subtópico.
2. **Exploração de Períodos:** Utilize os períodos sintáticos de cada subtópico para criar múltiplas questões por subtópico (confirmando a regra por paráfrase técnica nos itens CERTOS e aplicando inversão de conceito, troca de modalizador *deve/pode*, *prescinde/imprescinde*, supressão de exceção ou situação hipotética nos itens ERRADOS).
3. **Rastreabilidade Total no Gabarito:**
   - `explanation`: Explique de forma direta e didática por que o item está CERTO ou qual ponto exato torna o item ERRADO.
   - `pdf_quote`: Cite o período correspondente do PDF de estudo.
   - `pdf_page`: Indique a página exata do PDF (ex.: `'p. 5'`).

### QUESTÕES REAIS DA CEBRASPE EXTRAÍDAS DO MATERIAL (FEW-SHOT EXAMPLES):
{few_shot_questions}

### TEXTO INTEGRAL DO PDF DE ESTUDO:
{pdf_context}
"""

    try:
        client = genai.Client(api_key=api_key.strip())
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GeneratedBatteryResponseSchema,
                temperature=0.4,
            ),
        )
        parsed = json.loads(response.text)
        assertions = parsed.get("assertions", [])
        if assertions:
            # Se a IA retornou menos itens do que o total solicitado, complementa com as assertivas extraídas dos períodos!
            if len(assertions) < total_requested:
                period_supplement = _fallback_generate_assertions(
                    pages, real_questions, active_plan, subject, title, area
                )
                needed = total_requested - len(assertions)
                assertions.extend(period_supplement[:needed])
            return assertions
    except Exception as e:
        print(f"Erro no Gemini generate_cebraspe_assertions: {e}")

    return _fallback_generate_assertions(pages, real_questions, active_plan, subject, title, area)


def generate_error_reinforcement(
    wrong_assertions: List[Dict[str, Any]],
    api_key: str,
    model_name: str = "gemini-2.5-flash",
    questions_per_error: int = 2,
) -> List[Dict[str, Any]]:
    """
    Gera novas variações inéditas no estilo Cebraspe focadas exatamente nas assertivas que o aluno errou ou favoritou.
    """
    if not wrong_assertions:
        return []

    if not api_key or not api_key.strip():
        out = []
        for idx, w in enumerate(wrong_assertions[:15]):
            base_period = {
                "text": w.get("pdf_quote") or w.get("statement") or w.get("explanation", ""),
                "page_number": str(w.get("pdf_page", "1")).replace("p.", "").strip() or 1,
                "markers": [w.get("trap_type", "Conceito")],
            }
            from topic_parser import generate_assertions_from_single_period

            variations = generate_assertions_from_single_period(
                period_obj=base_period,
                topic=w.get("subject", "Revisão de Erros"),
                subtopic=w.get("subtopic", "Ponto Crítico"),
                subject=w.get("subject", "Revisão de Erros"),
                recurrence_level=w.get("recurrence_level", "Muito Alta"),
                max_variations=max(1, questions_per_error),
            )
            for v in variations[:questions_per_error]:
                v["inspired_by_real_question"] = f"Reforço do item #{w.get('item_number', idx + 1)} que você errou/favoritou"
                out.append(v)
        return out

    errors_context = json.dumps(
        [
            {
                "subtopic": w.get("subtopic"),
                "original_statement": w.get("statement"),
                "original_answer": w.get("answer"),
                "explanation": w.get("explanation"),
                "pdf_quote": w.get("pdf_quote"),
                "pdf_page": w.get("pdf_page"),
                "trap_type": w.get("trap_type"),
            }
            for w in wrong_assertions[:20]
        ],
        ensure_ascii=False,
        indent=2,
    )

    total_target = len(wrong_assertions[:20]) * questions_per_error
    prompt = f"""
Você é um Examinador da banca **CEBRASPE**. O estudante errou ou marcou como dúvida as assertivas abaixo.
Para cada item da lista abaixo, elabore **{questions_per_error} novas assertivas inéditas** (totalizando {total_target} assertivas) que cobrem exatamente o mesmo conceito/regra e explorem a mesma armadilha sob um novo ângulo (uma versão correta e/ou uma nova situação hipotética ou inversão sutil), para garantir que o aluno nunca mais erre esse ponto na prova!

### ITENS QUE O ESTUDANTE ERROU / FAVORITOU:
{errors_context}
"""

    try:
        client = genai.Client(api_key=api_key.strip())
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GeneratedBatteryResponseSchema,
                temperature=0.45,
            ),
        )
        parsed = json.loads(response.text)
        return parsed.get("assertions", [])
    except Exception:
        return []


# ============================================================================
# MOTOR LOCAL BASEADO EM PARSEAMENTO DE TÓPICOS, SUBTÓPICOS E PERÍODOS
# ============================================================================

def _fallback_analyze_pdf_recurrence(
    pages: List[Dict[str, Any]],
    heuristic_questions: List[Dict[str, Any]],
    area: str,
    custom_subject_hint: str = "",
    parsed_topics: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if parsed_topics is None:
        parsed_topics = parse_pdf_topics_and_subtopics(pages)

    first_page_text = pages[0]["text"] if pages else "Material de Estudo"
    lines = [ln.strip() for ln in first_page_text.split("\n") if len(ln.strip()) > 4]
    detected_title = lines[0][:85] if lines else "Estudo Dirigido Cebraspe"
    detected_subject = custom_subject_hint.strip() or (lines[1][:60] if len(lines) > 1 else "Disciplina do Concurso")

    total_pages = len(pages) or 1
    levels = [
        ("Muito Alta", 32, 8),
        ("Alta", 24, 6),
        ("Alta", 18, 5),
        ("Média", 14, 4),
        ("Baixa", 7, 3),
        ("Baixa", 5, 2),
    ]

    subtopics: List[Dict[str, Any]] = []
    q_count = len(heuristic_questions)

    if parsed_topics:
        for idx, pt in enumerate(parsed_topics[:10]):
            lvl, pct, base_min_q = levels[min(idx, len(levels) - 1)]
            periods_count = pt.get("periods_count", len(pt.get("periods", [])))
            real_for_sub = max(0, q_count // len(parsed_topics) + (1 if idx < (q_count % len(parsed_topics)) else 0))

            # Aumenta o número mínimo recomendado com base nos períodos extraídos do subtópico
            period_boosted_min = max(base_min_q, min(16, periods_count * 2))
            if real_for_sub > 3:
                period_boosted_min = max(period_boosted_min, min(18, real_for_sub + 2))

            # Coletar tipos de marcadores reais encontrados nos períodos deste subtópico
            detected_markers: List[str] = []
            for p_obj in pt.get("periods", []):
                for m in p_obj.get("markers", []):
                    if m not in detected_markers:
                        detected_markers.append(m)

            focus_points = [
                f"Exploração direta de {periods_count} período(s) normativo(s)/conceitual(is) extraído(s) do subtópico",
                *(
                    [f"Alvo de prova detectado nos períodos: {m}" for m in detected_markers[:2]]
                    if detected_markers
                    else ["Distinção conceitual e troca de modalizadores (deve vs. pode)"]
                ),
            ]

            subtopics.append(
                {
                    "topic": pt.get("topic", "Tópico Principal"),
                    "subtopic": pt["subtopic"],
                    "recurrence_level": lvl,
                    "recurrence_percentage": pct,
                    "real_questions_found": real_for_sub,
                    "periods_count": periods_count,
                    "min_recommended_questions": period_boosted_min,
                    "pages_reference": pt.get("pages_reference", f"p. 1-{total_pages}"),
                    "cebraspe_focus_points": focus_points[:4],
                }
            )
    else:
        subtopics = [
            {
                "topic": "1. Tópico Geral",
                "subtopic": "1.1. Conceitos Fundamentais e Disposições Gerais",
                "recurrence_level": "Muito Alta",
                "recurrence_percentage": 100,
                "real_questions_found": q_count,
                "periods_count": 1,
                "min_recommended_questions": 6,
                "pages_reference": f"p. 1-{total_pages}",
                "cebraspe_focus_points": [
                    "Distinção conceitual e troca de termos correlatos",
                    "Troca de modalizadores (deve vs. pode / vinculado vs. discricionário)",
                ],
            }
        ]

    sum_pct = sum(s["recurrence_percentage"] for s in subtopics) or 100
    for s in subtopics:
        s["recurrence_percentage"] = max(1, round(s["recurrence_percentage"] * 100 / sum_pct))

    total_periods = sum(s.get("periods_count", 0) for s in subtopics)
    return {
        "detected_subject": detected_subject,
        "detected_title": detected_title,
        "total_real_questions_detected": len(heuristic_questions),
        "analysis_summary": (
            f"Mapeamento concluído sobre {total_pages} página(s) para a área {area}. "
            f"Foram extraídos {len(subtopics)} subtópicos contendo {total_periods} períodos analisáveis "
            f"e {len(heuristic_questions)} questões de referência."
        ),
        "subtopics": subtopics,
        "parsed_topics": parsed_topics,
        "extracted_real_questions": heuristic_questions[:20],
    }


def _fallback_generate_assertions(
    pages: List[Dict[str, Any]],
    real_questions: List[Dict[str, Any]],
    active_plan: List[Dict[str, Any]],
    subject: str,
    title: str,
    area: str,
) -> List[Dict[str, Any]]:
    """
    Utiliza o módulo `topic_parser` para extrair de cada tópico e subtópico do PDF
    os seus respectivos períodos sintáticos e gerar múltiplas assertivas de Certo ou Errado.
    """
    parsed_topics = parse_pdf_topics_and_subtopics(pages)
    parsed_by_sub_name = {pt["subtopic"].lower(): pt for pt in parsed_topics}

    # Coletar todos os períodos globais do PDF como reserva caso algum subtópico customizado não case pelo nome
    all_periods_pool: List[Dict[str, Any]] = []
    for pt in parsed_topics:
        all_periods_pool.extend(pt.get("periods", []))

    if not all_periods_pool:
        all_periods_pool = [
            {
                "text": (
                    f"O regime aplicável a {title} no âmbito de {subject} deve observar estritamente os requisitos "
                    f"de validade e competência definidos na norma, salvo nas hipóteses expressamente ressalvadas."
                ),
                "page_number": 1,
                "markers": ["Modalizador (Deve vs. Pode)", "Exceção / Ressalva"],
            }
        ]

    structured_for_plan: List[Dict[str, Any]] = []
    questions_target_map: Dict[str, int] = {}

    pool_cursor = 0
    for idx, plan_item in enumerate(active_plan):
        sub_name = plan_item.get("subtopic", f"Subtópico {idx + 1}")
        topic_name = plan_item.get("topic", title)
        rec_level = plan_item.get("recurrence_level", "Alta")
        qty = int(plan_item.get("target_questions", plan_item.get("min_recommended_questions", 4)))
        questions_target_map[sub_name] = qty

        matched_pt = parsed_by_sub_name.get(sub_name.lower())
        if matched_pt and matched_pt.get("periods"):
            periods_for_sub = matched_pt["periods"]
            topic_name = matched_pt.get("topic", topic_name)
        else:
            # Selecionar fatia de períodos do pool global
            needed_periods = max(2, (qty + 1) // 2)
            periods_for_sub = []
            for _ in range(needed_periods):
                periods_for_sub.append(all_periods_pool[pool_cursor % len(all_periods_pool)])
                pool_cursor += 1

        structured_for_plan.append(
            {
                "topic": topic_name,
                "subtopic": sub_name,
                "recurrence_level": rec_level,
                "periods": periods_for_sub,
            }
        )

    assertions = extract_assertions_from_subtopics(
        structured_topics=structured_for_plan,
        subject=subject,
        area=area,
        questions_per_subtopic=questions_target_map,
        variations_per_period=2,
    )
    return assertions
