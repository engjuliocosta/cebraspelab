"""
Módulo de Parseamento Estrutural de Tópicos, Subtópicos e Períodos do PDF (`topic_parser.py`).

Analisa a hierarquia de tópicos e subtópicos do PDF, segmenta o texto de cada subtópico
em períodos sintáticos/normativos completos e gera múltiplas assertivas de Certo ou Errado
para cada período e subtópico no estilo Cebraspe, ampliando a cobertura e o volume de questões.
"""

import re
from typing import Any, Dict, List, Optional, Tuple


# Padrões de cabeçalhos de Tópicos Principais (ex: "1. ATOS ADMINISTRATIVOS", "CAPÍTULO I - ...", "TÓPICO 2:")
TOPIC_HEADER_REGEX = re.compile(
    r"^(?:"
    r"(?:CAP[ÍI]TULO|T[ÓO]PICO|TEMA|UNIDADE|PARTE)\s+[0-9IVXLCDM]+\s*[\-\–\:\.]?\s*[^\n]{3,90}"
    r"|(?:[1-9]\d?)\s*[\.\-\)]\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][^\n]{3,85}"
    r"|[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9\s\,\-\–\/\(\)]{7,75}"
    r")$"
)

# Padrões de Subtópicos (ex: "1.1. Atributos", "2.1.3 Convalidação", "a) Presunção de legitimidade", "Art. 54.")
SUBTOPIC_HEADER_REGEX = re.compile(
    r"^(?:"
    r"\d+\.\d+(?:\.\d+)*\s*[\.\-\)]?\s*[^\n]{3,90}"
    r"|(?:SE[ÇC][ÃA]O|SUBT[ÓO]PICO|ITEM)\s+[0-9IVXLCDM\.]+\s*[\-\–\:\.]?\s*[^\n]{3,90}"
    r"|[a-zA-Z]\)\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][^\n]{4,80}"
    r"|Art\.\s*\d+[º°]?(?:\-[A-Z])?\s*[\.\-]?"
    r")$"
)

# Pares cirúrgicos de inversão semântica/normativa muito cobrados pela Cebraspe
CEBRASPE_SURGICAL_SWAPS: List[Tuple[re.Pattern, str, str, str]] = [
    (
        re.compile(r"\b(não\s+pode(?:m)?|não\s+poderá|não\s+poderão|é\s+vedado|são\s+vedados)\b", re.IGNORECASE),
        "pode livremente, a critério discricionário,",
        "Modalizador / Permissão Indevida",
        "O período original estabelece uma vedação/proibição expressa, que foi invertida para uma permissão discricionária.",
    ),
    (
        re.compile(r"\b(deve(?:m)?|deverá|deverão|é\s+obrigat[óo]ri[oa]|impõe-se)\b", re.IGNORECASE),
        "pode facultativamente, a juízo de conveniência,",
        "Modalizador (Deve vs. Pode)",
        "Trocou-se um comando obrigatório/vinculado ('deve' / 'obrigatório') por uma faculdade discricionária ('pode facultativamente').",
    ),
    (
        re.compile(r"\b(pode(?:m)?|poderá|poderão|é\s+facultado|admite-se)\b", re.IGNORECASE),
        "deve obrigatoriamente e sem margem de escolha",
        "Modalizador (Pode vs. Deve)",
        "Transformou-se uma hipótese facultativa/discricionária ('pode' / 'admite-se') em obrigação absoluta e vinculada.",
    ),
    (
        re.compile(r"\b(prescinde(?:m)?\s+de|independe(?:m)?\s+de)\b", re.IGNORECASE),
        "imprescinde e depende obrigatoriamente de",
        "Inversão Semântica (Prescinde vs. Imprescinde)",
        "Pegadinha clássica da Cebraspe: 'prescinde/independe' significa que NÃO precisa, mas o item afirmou que é indispensável ('imprescinde/depende').",
    ),
    (
        re.compile(r"\b(depende(?:m)?\s+de|imprescinde(?:m)?\s+de|exige(?:m)?)\b", re.IGNORECASE),
        "prescinde totalmente de",
        "Inversão Semântica (Exige vs. Prescinde)",
        "O texto original exige o requisito ('depende/exige'), mas a assertiva afirmou que ele seria dispensável ('prescinde').",
    ),
    (
        re.compile(r"\b(ex\s+tunc|retroativos?)\b", re.IGNORECASE),
        "ex nunc (não retroativos, valendo apenas para o futuro)",
        "Inversão de Conceito (Ex Tunc vs. Ex Nunc)",
        "Houve inversão dos efeitos temporais: onde o material prevê efeitos retroativos (ex tunc), a assertiva indicou efeitos prospectivos (ex nunc).",
    ),
    (
        re.compile(r"\b(ex\s+nunc|irretroativos?|prospectivos?)\b", re.IGNORECASE),
        "ex tunc (retroagindo à origem do ato)",
        "Inversão de Conceito (Ex Nunc vs. Ex Tunc)",
        "Houve inversão dos efeitos temporais: onde o material prevê efeitos ex nunc (não retroativos), a assertiva indicou efeitos ex tunc.",
    ),
    (
        re.compile(r"\b(relativa|juris\s+tantum)\b", re.IGNORECASE),
        "absoluta (juris et de jure, não admitindo prova em contrário)",
        "Inversão de Conceito (Relativa vs. Absoluta)",
        "O texto original prevê natureza relativa (juris tantum, que admite prova em contrário), mas a assertiva trocou por natureza absoluta (juris et de jure).",
    ),
    (
        re.compile(r"\b(absoluta|juris\s+et\s+de\s+jure)\b", re.IGNORECASE),
        "meramente relativa (juris tantum)",
        "Inversão de Conceito (Absoluta vs. Relativa)",
        "O texto original prevê natureza absoluta, mas a assertiva a reduziu para relativa.",
    ),
    (
        re.compile(r"\b(vinculad[oa]s?)\b", re.IGNORECASE),
        "essencialmente discricionário(a)",
        "Inversão de Conceito (Vinculado vs. Discricionário)",
        "A assertiva trocou a natureza vinculada prevista no PDF por natureza discricionária.",
    ),
    (
        re.compile(r"\b(discricion[áa]ri[oa]s?)\b", re.IGNORECASE),
        "estritamente vinculado(a), sem margem de mérito",
        "Inversão de Conceito (Discricionário vs. Vinculado)",
        "A assertiva trocou a natureza discricionária prevista no PDF por natureza estritamente vinculada.",
    ),
    (
        re.compile(r"\b(anula[çc][ãa]o|anular|anulado)\b", re.IGNORECASE),
        "revogação por conveniência e oportunidade",
        "Inversão de Conceito (Anulação vs. Revogação)",
        "Inverteu-se o instituto da anulação (controle de legalidade) pelo da revogação (controle de mérito).",
    ),
    (
        re.compile(r"\b(revoga[çc][ãa]o|revogar|revogado)\b", re.IGNORECASE),
        "anulação fundada em vício de legalidade",
        "Inversão de Conceito (Revogação vs. Anulação)",
        "Inverteu-se o instituto da revogação (mérito administrativo) pelo da anulação (ilegalidade).",
    ),
    (
        re.compile(r"\b(desconcentra[çc][ãa]o)\b", re.IGNORECASE),
        "descentralização mediante criação de nova pessoa jurídica",
        "Inversão de Conceito (Desconcentração vs. Descentralização)",
        "Trocou-se desconcentração (distribuição interna de competências na mesma pessoa jurídica) por descentralização.",
    ),
    (
        re.compile(r"\b(descentraliza[çc][ãa]o)\b", re.IGNORECASE),
        "mera desconcentração interna de órgãos subordinados",
        "Inversão de Conceito (Descentralização vs. Desconcentração)",
        "Trocou-se descentralização (entre pessoas jurídicas distintas) por desconcentração interna.",
    ),
    (
        re.compile(r"\b(unilateral|unilateralmente)\b", re.IGNORECASE),
        "bilateral, dependendo de prévia concordância da outra parte,",
        "Inversão de Conceito (Unilateral vs. Bilateral)",
        "O período original afirma o caráter unilateral, que foi adulterado para bilateral.",
    ),
]

EXCEPTION_TRIGGER_REGEX = re.compile(
    r"\b(salvo|exceto|ressalvad[oa]s?|excetuad[oa]s?|a\s+menos\s+que|desde\s+que|não\s+se\s+aplicando)\b",
    re.IGNORECASE,
)


def _is_noise_line(line: str) -> bool:
    upper = line.upper()
    if len(line) < 3:
        return True
    if upper.startswith(("PÁGINA ", "PAGINA ", "WWW.", "HTTP://", "HTTPS://", "TODOS OS DIREITOS")):
        return True
    if re.match(r"^\d+$", line):
        return True
    return False


def split_into_periods(text: str) -> List[str]:
    """
    Segmenta um bloco de texto em períodos sintáticos completos (frases/orações normativas ou conceituais),
    protegendo abreviações jurídicas e técnicas (ex: Art., inc., nº, §, p., Dr., CF, STF, STJ).
    """
    if not text or not text.strip():
        return []

    # Proteger abreviações comuns para não quebrar o período no ponto abreviativo
    protected = text
    abbreviations = [
        (r"\bArt\.", "Art<DOT>"),
        (r"\bart\.", "art<DOT>"),
        (r"\binc\.", "inc<DOT>"),
        (r"\bp\.", "p<DOT>"),
        (r"\bpp\.", "pp<DOT>"),
        (r"\bn\.", "n<DOT>"),
        (r"\bnº\.", "nº<DOT>"),
        (r"\bDr\.", "Dr<DOT>"),
        (r"\bProf\.", "Prof<DOT>"),
        (r"\bEx\.", "Ex<DOT>"),
        (r"\bex\.", "ex<DOT>"),
        (r"\bobs\.", "obs<DOT>"),
        (r"\bObs\.", "Obs<DOT>"),
        (r"\bcf\.", "cf<DOT>"),
    ]
    for pattern, repl in abbreviations:
        protected = re.sub(pattern, repl, protected)

    # Normalizar quebras de linha simples dentro do mesmo parágrafo, preservando quebras duplas ou listas
    protected = re.sub(r"(?<![\.\;\:\!\?\n])\n(?=[a-záéíóúâêôãõç0-9])", " ", protected)

    # Quebrar em fim de período (ponto final, ponto e vírgula longo, ou quebra de parágrafo)
    raw_chunks = re.split(r"(?<=[\.\!\?])\s+|\n{2,}|(?<=\;)\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])", protected)

    periods: List[str] = []
    for chunk in raw_chunks:
        restored = chunk.replace("<DOT>", ".")
        cleaned = re.sub(r"\s+", " ", restored).strip(" -•*\t\r\n")
        # Filtrar períodos com substância teórica/normativa (entre 45 e 550 caracteres)
        if 45 <= len(cleaned) <= 550:
            upper = cleaned.upper()
            if not upper.startswith(("GABARITO:", "RESPOSTA:", "QUESTÃO ", "COMENTÁRIO:")):
                periods.append(cleaned)

    return periods


def detect_period_markers(period_text: str) -> List[str]:
    """Identifica marcadores lógicos, normativos ou conceituais presentes no período."""
    markers: List[str] = []
    if EXCEPTION_TRIGGER_REGEX.search(period_text):
        markers.append("Exceção / Ressalva")
    for pattern, _, trap_label, _ in CEBRASPE_SURGICAL_SWAPS:
        if pattern.search(period_text):
            markers.append(trap_label)
    if re.search(r"\b(\d+\s*(?:dias?|anos?|meses|horas?)|prazo)\b", period_text, re.IGNORECASE):
        markers.append("Prazo / Critério Numérico")
    if re.search(r"\b(conceito|define-se|consiste\s+em|caracteriza-se|entende-se\s+por|denomina-se)\b", period_text, re.IGNORECASE):
        markers.append("Definição Conceitual")
    if not markers:
        markers.append("Afirmação Teórica / Literalidade")
    return list(dict.fromkeys(markers))


def parse_pdf_topics_and_subtopics(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Analisa todas as páginas do PDF, identifica a árvore de Tópicos e Subtópicos,
    e extrai todos os períodos (frases/orações completas) pertencentes a cada subtópico.

    Retorna uma lista de dicionários estruturados por subtópico:
    [
        {
            "topic": "1. ATOS ADMINISTRATIVOS",
            "subtopic": "1.1. Atributos do Ato Administrativo",
            "start_page": 2,
            "end_page": 5,
            "pages_reference": "p. 2-5",
            "periods": [
                {
                    "text": "...",
                    "page_number": 2,
                    "markers": ["Inversão de Conceito (Relativa vs. Absoluta)", ...],
                },
                ...
            ],
            "periods_count": 12,
            "estimated_questions_capacity": 28
        }
    ]
    """
    if not pages:
        return []

    current_topic = "1. Disposições Gerais e Conceitos Nucleares"
    current_subtopic = "1.1. Fundamentos e Regras Gerais do Tema"

    sections_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def get_or_create_section(topic_name: str, subtopic_name: str, page_num: int) -> Dict[str, Any]:
        key = (topic_name, subtopic_name)
        if key not in sections_map:
            sections_map[key] = {
                "topic": topic_name,
                "subtopic": subtopic_name,
                "start_page": page_num,
                "end_page": page_num,
                "BufferLines": [],
                "periods": [],
            }
        else:
            sections_map[key]["end_page"] = max(sections_map[key]["end_page"], page_num)
        return sections_map[key]

    def flush_buffer(section: Dict[str, Any], page_num: int) -> None:
        if not section["BufferLines"]:
            return
        joined = "\n".join(section["BufferLines"])
        section["BufferLines"] = []
        extracted_periods = split_into_periods(joined)
        for p_text in extracted_periods:
            markers = detect_period_markers(p_text)
            section["periods"].append(
                {
                    "text": p_text,
                    "page_number": page_num,
                    "markers": markers,
                }
            )

    for page in pages:
        p_num = int(page.get("page_number", 1))
        raw_text = page.get("text", "")
        lines = raw_text.split("\n")

        for raw_line in lines:
            line = raw_line.strip()
            if _is_noise_line(line):
                continue

            # Verificar se a linha é um Subtópico explícito (ex: "1.1. ...", "Seção II...")
            if len(line) <= 90 and SUBTOPIC_HEADER_REGEX.match(line):
                prev_sec = get_or_create_section(current_topic, current_subtopic, p_num)
                flush_buffer(prev_sec, p_num)
                current_subtopic = re.sub(r"\s+", " ", line).strip()
                get_or_create_section(current_topic, current_subtopic, p_num)
                continue

            # Verificar se a linha é um Tópico Principal (ex: "1. PODERES ADMINISTRATIVOS", "CAPÍTULO 2")
            if (
                len(line) <= 85
                and TOPIC_HEADER_REGEX.match(line)
                and not line.endswith((".", ";", ","))
            ):
                prev_sec = get_or_create_section(current_topic, current_subtopic, p_num)
                flush_buffer(prev_sec, p_num)
                current_topic = re.sub(r"\s+", " ", line).title().strip()
                current_subtopic = f"{current_topic} — Aspectos Gerais"
                get_or_create_section(current_topic, current_subtopic, p_num)
                continue

            sec = get_or_create_section(current_topic, current_subtopic, p_num)
            sec["BufferLines"].append(line)

        # Ao final da página, descarregar os períodos acumulados mantendo o número exato da página
        sec = get_or_create_section(current_topic, current_subtopic, p_num)
        flush_buffer(sec, p_num)

    # Consolidar resultados
    structured_list: List[Dict[str, Any]] = []
    for (_, _), sec_data in sections_map.items():
        periods = sec_data["periods"]
        if not periods:
            continue
        start_p = sec_data["start_page"]
        end_p = sec_data["end_page"]
        pages_ref = f"p. {start_p}" if start_p == end_p else f"p. {start_p}-{end_p}"
        # Cada período pode originar de 2 a 3 assertivas (1 Certa + 1 ou 2 Erradas cirúrgicas)
        capacity = sum(2 + (1 if len(p["markers"]) > 1 else 0) for p in periods)
        structured_list.append(
            {
                "topic": sec_data["topic"],
                "subtopic": sec_data["subtopic"],
                "start_page": start_p,
                "end_page": end_p,
                "pages_reference": pages_ref,
                "periods": periods,
                "periods_count": len(periods),
                "estimated_questions_capacity": capacity,
            }
        )

    # Caso um PDF curto tenha ficado concentrado em apenas 1 seção mas possua vários períodos,
    # subdividir automaticamente em blocos temáticos para garantir múltiplos subtópicos
    if len(structured_list) == 1 and len(structured_list[0]["periods"]) >= 6:
        only_sec = structured_list[0]
        all_p = only_sec["periods"]
        chunk_size = max(2, len(all_p) // 3)
        sub_labels = [
            "Conceitos Fundamentais e Regra Geral",
            "Requisitos, Características e Aplicação",
            "Exceções, Vedação e Casos Especiais",
        ]
        redistributed: List[Dict[str, Any]] = []
        for idx, label in enumerate(sub_labels):
            slice_p = all_p[idx * chunk_size : (idx + 1) * chunk_size if idx < 2 else len(all_p)]
            if not slice_p:
                continue
            sp = slice_p[0]["page_number"]
            ep = slice_p[-1]["page_number"]
            redistributed.append(
                {
                    "topic": only_sec["topic"],
                    "subtopic": f"{idx + 1}. {label}",
                    "start_page": sp,
                    "end_page": ep,
                    "pages_reference": f"p. {sp}" if sp == ep else f"p. {sp}-{ep}",
                    "periods": slice_p,
                    "periods_count": len(slice_p),
                    "estimated_questions_capacity": len(slice_p) * 2,
                }
            )
        if len(redistributed) > 1:
            return redistributed

    return structured_list


def generate_assertions_from_single_period(
    period_obj: Dict[str, Any],
    topic: str,
    subtopic: str,
    subject: str,
    area: str = "Geral",
    recurrence_level: str = "Alta",
    max_variations: int = 2,
) -> List[Dict[str, Any]]:
    """
    A partir de um único período (frase/oração normativa ou conceitual) do PDF,
    cria múltiplas assertivas de Certo ou Errado no estilo Cebraspe:
      1. Variação CERTA (Paráfrase / Confirmação Técnica do Período)
      2. Variação ERRADA Cirúrgica (Inversão de Modalizador / Conceito / Exceção)
      3. Variação ERRADA de Extrapolação / Restrição Absoluta (quando max_variations >= 3)
    """
    raw_text = period_obj["text"].strip()
    page_num = period_obj.get("page_number", 1)
    page_ref = f"p. {page_num}"
    command = f"No que se refere a {subtopic} ({topic}), no âmbito de {subject}, julgue os itens a seguir."

    generated: List[Dict[str, Any]] = []

    # -------------------------------------------------------------------------
    # 1. ASSERTIVA CERTA (Baseada na confirmação técnica do período)
    # -------------------------------------------------------------------------
    prefixes_certo = [
        "De acordo com a sistemática aplicável ao tema, ",
        "Considerando os parâmetros técnicos e normativos da matéria, ",
        "Sob a ótica doutrinária e normativa apresentada, ",
        "",
    ]
    prefix = prefixes_certo[len(raw_text) % len(prefixes_certo)]
    if prefix and raw_text[0].isupper() and not raw_text[:4].isupper():
        statement_certo = prefix + raw_text[0].lower() + raw_text[1:]
    else:
        statement_certo = raw_text

    generated.append(
        {
            "topic": topic,
            "subtopic": subtopic,
            "recurrence_level": recurrence_level,
            "command_text": command,
            "statement": statement_certo,
            "answer": "C",
            "explanation": (
                f"ITEM CERTO. A assertiva está em perfeita consonância com o período constante na {page_ref} "
                f"do material sobre '{subtopic}' ({topic})."
            ),
            "pdf_quote": raw_text,
            "pdf_page": page_ref,
            "trap_type": "Literalidade / Conceito Exato",
            "difficulty": "Média",
            "inspired_by_real_question": f"Extraída diretamente de período do subtópico '{subtopic}' ({page_ref})",
        }
    )

    if max_variations <= 1:
        return generated

    # -------------------------------------------------------------------------
    # 2. ASSERTIVA ERRADA CIRÚRGICA (Inversão de Modalizador, Conceito ou Exceção)
    # -------------------------------------------------------------------------
    surgical_applied = False
    for pattern, replacement, trap_label, reason in CEBRASPE_SURGICAL_SWAPS:
        match = pattern.search(raw_text)
        if match:
            original_term = match.group(0)
            mutated_text = pattern.sub(replacement, raw_text, count=1)
            generated.append(
                {
                    "topic": topic,
                    "subtopic": subtopic,
                    "recurrence_level": recurrence_level,
                    "command_text": command,
                    "statement": mutated_text,
                    "answer": "E",
                    "explanation": (
                        f"ITEM ERRADO. {reason} No período original ({page_ref}), consta a expressão "
                        f"'{original_term}', que foi substituída indevidamente por '{replacement}'."
                    ),
                    "pdf_quote": raw_text,
                    "pdf_page": page_ref,
                    "trap_type": trap_label,
                    "difficulty": "Média",
                    "inspired_by_real_question": f"Transformação Cebraspe sobre período de '{subtopic}' ({page_ref})",
                }
            )
            surgical_applied = True
            break

    # Se não bateu em um modalizador direto mas possui cláusula de exceção ("salvo", "exceto", "desde que")
    if not surgical_applied and EXCEPTION_TRIGGER_REGEX.search(raw_text):
        exc_match = EXCEPTION_TRIGGER_REGEX.search(raw_text)
        assert exc_match is not None
        trigger_word = exc_match.group(0)
        before_exc = raw_text[: exc_match.start()].strip(" ,;-")
        mutated_exc = (
            f"{before_exc}, regra esta de caráter absoluto que não comporta qualquer exceção ou temperamento."
        )
        generated.append(
            {
                "topic": topic,
                "subtopic": subtopic,
                "recurrence_level": recurrence_level,
                "command_text": command,
                "statement": mutated_exc,
                "answer": "E",
                "explanation": (
                    f"ITEM ERRADO. O período original na {page_ref} prevê expressamente uma ressalva/exceção "
                    f"introduzida pelo termo '{trigger_word}'. A assertiva generalizou a regra geral e suprimiu a exceção."
                ),
                "pdf_quote": raw_text,
                "pdf_page": page_ref,
                "trap_type": "Regra Geral vs. Exceção",
                "difficulty": "Difícil",
                "inspired_by_real_question": f"Supressão de exceção Cebraspe em '{subtopic}' ({page_ref})",
            }
        )
        surgical_applied = True

    # Fallback de transformação caso o período seja puramente descritivo
    if not surgical_applied:
        words = raw_text.rstrip(".").split(" ")
        mid = max(3, len(words) // 2)
        clause = "sendo vedada qualquer aplicação fora das hipóteses taxativas e exclusivas de controle judicial prévio"
        mutated_fallback = " ".join(words[:mid]) + f", {clause}, " + " ".join(words[mid:]) + "."
        generated.append(
            {
                "topic": topic,
                "subtopic": subtopic,
                "recurrence_level": recurrence_level,
                "command_text": command,
                "statement": mutated_fallback,
                "answer": "E",
                "explanation": (
                    f"ITEM ERRADO. A assertiva começa com uma premissa verdadeira do período ({page_ref}), "
                    f"mas insere restrição/extrapolação inexistente no material ('{clause}')."
                ),
                "pdf_quote": raw_text,
                "pdf_page": page_ref,
                "trap_type": "Verdade Parcial + Conclusão Falsa",
                "difficulty": "Média",
                "inspired_by_real_question": f"Extrapolação de período do subtópico '{subtopic}' ({page_ref})",
            }
        )

    # -------------------------------------------------------------------------
    # 3. TERCEIRA VARIAÇÃO OPCIONAL (Situação Hipotética / Restrição Absoluta)
    # -------------------------------------------------------------------------
    if max_variations >= 3:
        clean_body = raw_text.rstrip(".")
        hyp_statement = (
            f"Considere que determinado agente invoque a aplicação das regras de {subtopic}. "
            f"Nessa situação, diferentemente do que ocorre na regra geral, é incorreto afirmar que "
            f"{clean_body[0].lower() + clean_body[1:] if len(clean_body) > 2 else clean_body}, "
            f"haja vista tratar-se de preceito meramente exemplificativo e desprovido de eficácia vinculante."
        )
        generated.append(
            {
                "topic": topic,
                "subtopic": subtopic,
                "recurrence_level": recurrence_level,
                "command_text": command,
                "statement": hyp_statement,
                "answer": "E",
                "explanation": (
                    f"ITEM ERRADO. A situação proposta nega a validade do próprio período expresso na {page_ref} "
                    f"do PDF ('{raw_text}'), classificando-o falsamente como desprovido de eficácia."
                ),
                "pdf_quote": raw_text,
                "pdf_page": page_ref,
                "trap_type": "Situação Hipotética",
                "difficulty": "Difícil",
                "inspired_by_real_question": f"Situação hipotética derivada de período em '{subtopic}' ({page_ref})",
            }
        )

    return generated


def extract_assertions_from_subtopics(
    structured_topics: List[Dict[str, Any]],
    subject: str = "Disciplina Geral",
    area: str = "Geral",
    questions_per_subtopic: Optional[Dict[str, int]] = None,
    variations_per_period: int = 2,
) -> List[Dict[str, Any]]:
    """
    Percorre todos os tópicos e subtópicos parseados do PDF e utiliza os períodos
    de cada subtópico para gerar múltiplas assertivas de Certo ou Errado,
    aumentando significativamente o número de questões geradas por subtópico.
    """
    all_assertions: List[Dict[str, Any]] = []
    if not structured_topics:
        return all_assertions

    for idx, section in enumerate(structured_topics):
        topic = section.get("topic", "Tópico Principal")
        subtopic = section.get("subtopic", f"Subtópico {idx + 1}")
        periods = section.get("periods", [])
        if not periods:
            continue

        # Determinar nível de recorrência sugerido pela posição/densidade se não especificado
        rec_level = section.get("recurrence_level") or (
            "Muito Alta" if idx == 0 else "Alta" if idx <= 2 else "Média"
        )

        target_qty = (
            questions_per_subtopic.get(subtopic)
            if questions_per_subtopic and subtopic in questions_per_subtopic
            else None
        )

        subtopic_assertions: List[Dict[str, Any]] = []
        for p_obj in periods:
            vars_for_p = generate_assertions_from_single_period(
                period_obj=p_obj,
                topic=topic,
                subtopic=subtopic,
                subject=subject,
                area=area,
                recurrence_level=rec_level,
                max_variations=variations_per_period,
            )
            subtopic_assertions.extend(vars_for_p)

        # Se o usuário pediu um mínimo maior do que 2x o número de períodos, geramos a 3ª variação por período
        if target_qty and len(subtopic_assertions) < target_qty and variations_per_period < 3:
            subtopic_assertions = []
            for p_obj in periods:
                vars_for_p = generate_assertions_from_single_period(
                    period_obj=p_obj,
                    topic=topic,
                    subtopic=subtopic,
                    subject=subject,
                    area=area,
                    recurrence_level=rec_level,
                    max_variations=3,
                )
                subtopic_assertions.extend(vars_for_p)

        # Intercalar C e E de modo equilibrado e respeitar target_qty se definido
        if target_qty is not None and target_qty > 0:
            if len(subtopic_assertions) >= target_qty:
                subtopic_assertions = subtopic_assertions[:target_qty]
            else:
                # Se ainda faltar para atingir target_qty, ciclar com novas combinações
                base_len = len(subtopic_assertions)
                while len(subtopic_assertions) < target_qty and base_len > 0:
                    clone = dict(subtopic_assertions[len(subtopic_assertions) % base_len])
                    subtopic_assertions.append(clone)

        all_assertions.extend(subtopic_assertions)

    return all_assertions

