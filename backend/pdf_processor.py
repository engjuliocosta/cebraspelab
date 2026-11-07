import json
import re
from typing import Any, Dict, List, Tuple
import pymupdf as fitz


CEBRASPE_HEADER_PATTERN = re.compile(
    r"(?:\(\s*(?:CEBRASPE|CESPE|UnB)[^)]+\)|\b(?:CEBRASPE|CESPE|UnB)\b[^\n]{0,120}\b(?:20\d{2}|199\d)\b)",
    re.IGNORECASE,
)

GABARITO_PATTERN = re.compile(
    r"(?:Gabarito\s*[:\-]\s*(Certo|Errado|C|E)\b|Resposta\s*[:\-]\s*(Certo|Errado|C|E)\b)",
    re.IGNORECASE,
)


def extract_pdf_pages(file_bytes: bytes, filename: str = "documento.pdf") -> List[Dict[str, Any]]:
    """Extrai o texto de cada página de um arquivo PDF usando PyMuPDF."""
    pages: List[Dict[str, Any]] = []
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    for page_index in range(len(doc)):
        page = doc.load_page(page_index)
        text = page.get_text("text")
        cleaned = re.sub(r"\n{3,}", "\n\n", text).strip()
        if cleaned:
            pages.append(
                {
                    "page_number": page_index + 1,
                    "text": cleaned,
                    "source_file": filename,
                }
            )
    doc.close()
    return pages


def extract_questions_heuristic(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Detecta questões reais da Cebraspe/Cespe presentes tanto no final de PDFs de cursinho
    (ex: Estratégia, Gran, Direção) quanto em cadernos do TEC Concursos / QConcursos.
    """
    extracted: List[Dict[str, Any]] = []
    full_text_by_page = [(p["page_number"], p["text"]) for p in pages]

    for page_num, text in full_text_by_page:
        matches = list(CEBRASPE_HEADER_PATTERN.finditer(text))
        for idx, match in enumerate(matches):
            header = match.group(0).strip()
            start_pos = match.end()
            end_pos = matches[idx + 1].start() if idx + 1 < len(matches) else min(len(text), start_pos + 1800)
            block = text[start_pos:end_pos].strip()
            if len(block) < 35:
                continue

            ans = ""
            gab_match = GABARITO_PATTERN.search(block)
            commentary = ""
            statement = block

            if gab_match:
                raw_ans = (gab_match.group(1) or gab_match.group(2) or "").strip().upper()
                ans = "C" if raw_ans.startswith("C") else "E"
                statement = block[: gab_match.start()].strip()
                commentary = block[gab_match.end() :].strip()[:600]
            else:
                # Corta no primeiro "Comentário:" se houver
                com_split = re.split(r"\bComent[áa]rios?\s*[:\-]", block, maxsplit=1, flags=re.IGNORECASE)
                if len(com_split) > 1:
                    statement = com_split[0].strip()
                    commentary = com_split[1].strip()[:600]
                    gab_in_com = GABARITO_PATTERN.search(commentary)
                    if gab_in_com:
                        raw_ans = (gab_in_com.group(1) or gab_in_com.group(2) or "").strip().upper()
                        ans = "C" if raw_ans.startswith("C") else "E"

            statement = re.sub(r"\s+", " ", statement).strip()
            if 35 <= len(statement) <= 1200:
                extracted.append(
                    {
                        "exam_info": header,
                        "statement": statement,
                        "answer": ans,
                        "commentary": re.sub(r"\s+", " ", commentary).strip(),
                        "page_number": page_num,
                        "subtopic": "Identificado no PDF",
                    }
                )

    # Deduplicar por statement
    seen = set()
    unique_questions = []
    for q in extracted:
        key = q["statement"][:120].lower()
        if key not in seen:
            seen.add(key)
            unique_questions.append(q)

    return unique_questions


def parse_extra_questions_file(file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    """
    Suporta arquivos extras de questões da Cebraspe enviados como PDF, JSON ou TXT/MD.
    """
    lower = filename.lower()
    if lower.endswith(".pdf"):
        pages = extract_pdf_pages(file_bytes, filename)
        questions = extract_questions_heuristic(pages)
        if not questions:
            # Se o PDF de questões não usar cabeçalho padrão (CEBRASPE/2024), extrai blocos numerados
            for p in pages:
                items = re.split(r"\n(?=\d{1,3}\s*[\.\-\)]\s+)", p["text"])
                for item in items:
                    clean = re.sub(r"\s+", " ", item).strip()
                    if 45 <= len(clean) <= 1000:
                        questions.append(
                            {
                                "exam_info": f"Caderno Cebraspe ({filename})",
                                "statement": clean,
                                "answer": "",
                                "commentary": "",
                                "page_number": p["page_number"],
                                "subtopic": "Caderno Anexo",
                            }
                        )
        return questions[:150]

    text = file_bytes.decode("utf-8", errors="ignore")
    if lower.endswith(".json"):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                out = []
                for item in data:
                    if isinstance(item, dict):
                        out.append(
                            {
                                "exam_info": str(item.get("exam_info") or item.get("banca") or "Cebraspe"),
                                "statement": str(item.get("statement") or item.get("enunciado") or item.get("texto") or ""),
                                "answer": str(item.get("answer") or item.get("gabarito") or ""),
                                "commentary": str(item.get("commentary") or item.get("comentario") or ""),
                                "subtopic": str(item.get("subtopic") or item.get("assunto") or "Geral"),
                            }
                        )
                return [q for q in out if q["statement"]]
        except Exception:
            pass

    # Fallback texto/markdown
    lines = [ln.strip() for ln in text.split("\n") if len(ln.strip()) > 35]
    return [
        {
            "exam_info": f"Base Anexo ({filename})",
            "statement": ln,
            "answer": "",
            "commentary": "",
            "subtopic": "Geral",
        }
        for ln in lines[:100]
    ]
