import csv
import hashlib
import io
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List
import genanki
from fpdf import FPDF


def _sanitize_tag(text: str) -> str:
    clean = re.sub(r"[^\w\-]", "_", text.strip())
    return re.sub(r"_+", "_", clean).strip("_") or "Geral"


def filter_assertions_for_export(assertions: List[Dict[str, Any]], filter_mode: str = "all") -> List[Dict[str, Any]]:
    """
    Filtra as assertivas conforme escolha do usuário:
    - 'all': Todas as assertivas da bateria
    - 'errors_or_favorites': Apenas as que o usuário errou (is_correct == 0) ou favoritou (is_favorite == True)
    - 'errors_only': Apenas as que o usuário errou
    - 'favorites_only': Apenas as favoritadas
    """
    if filter_mode == "errors_or_favorites":
        filtered = [a for a in assertions if a.get("is_correct") == 0 or a.get("is_favorite")]
        return filtered if filtered else assertions
    if filter_mode == "errors_only":
        filtered = [a for a in assertions if a.get("is_correct") == 0]
        return filtered if filtered else assertions
    if filter_mode == "favorites_only":
        filtered = [a for a in assertions if a.get("is_favorite")]
        return filtered if filtered else assertions
    return assertions


def export_to_anki_apkg(battery: Dict[str, Any], filter_mode: str = "all") -> bytes:
    assertions = filter_assertions_for_export(battery.get("assertions", []), filter_mode)
    subject = battery.get("subject", "Concurso")
    title = battery.get("title", "Bateria Cebraspe")
    deck_name = f"Cebraspe::{subject}::{title}"
    deck_id = int(hashlib.sha256(deck_name.encode("utf-8")).hexdigest()[:8], 16) % (10**10)
    model_id = 1948572941

    cebraspe_model = genanki.Model(
        model_id,
        "Cebraspe Assertiva Pro (Gerador)",
        fields=[
            {"name": "Subject"},
            {"name": "Subtopic"},
            {"name": "Recurrence"},
            {"name": "Command"},
            {"name": "Statement"},
            {"name": "AnswerBadge"},
            {"name": "Explanation"},
            {"name": "PdfReference"},
            {"name": "TrapType"},
        ],
        templates=[
            {
                "name": "Card Cebraspe C/E",
                "qfmt": """
                <div class="card-container">
                    <div class="meta-bar">
                        <span class="badge subject">{{Subject}}</span>
                        <span class="badge subtopic">{{Subtopic}}</span>
                        <span class="badge recurrence">Recorrência: {{Recurrence}}</span>
                    </div>
                    <div class="command">{{Command}}</div>
                    <div class="statement">{{Statement}}</div>
                    <div class="ce-prompt">Julgue o item: <strong>( ) CERTO</strong> &nbsp;&nbsp;|&nbsp;&nbsp; <strong>( ) ERRADO</strong></div>
                </div>
                """,
                "afmt": """
                {{FrontSide}}
                <hr id="answer">
                <div class="answer-container">
                    <div class="answer-header">
                        {{AnswerBadge}}
                        <span class="badge trap">Pegadinha / Técnica: {{TrapType}}</span>
                    </div>
                    <div class="explanation">
                        <strong>Comentário Cebraspe:</strong><br>{{Explanation}}
                    </div>
                    {{#PdfReference}}
                    <div class="pdf-quote">
                        <strong>Trecho do Material (PDF):</strong><br>{{PdfReference}}
                    </div>
                    {{/PdfReference}}
                </div>
                """,
            }
        ],
        css="""
        .card {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 16px;
            line-height: 1.55;
            color: #1e293b;
            background-color: #f8fafc;
            padding: 16px;
            text-align: left;
        }
        .card-container, .answer-container {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 18px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }
        .meta-bar {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-bottom: 12px;
        }
        .badge {
            font-size: 11px;
            font-weight: 600;
            padding: 3px 8px;
            border-radius: 999px;
            background: #f1f5f9;
            color: #334155;
        }
        .badge.subject { background: #e0e7ff; color: #3730a3; }
        .badge.recurrence { background: #fef3c7; color: #92400e; }
        .badge.trap { background: #f3e8ff; color: #6b21a8; }
        .command {
            font-size: 13px;
            color: #64748b;
            font-style: italic;
            margin-bottom: 10px;
        }
        .statement {
            font-size: 17px;
            font-weight: 500;
            color: #0f172a;
            margin-bottom: 14px;
        }
        .ce-prompt {
            font-size: 12px;
            color: #475569;
            border-top: 1px dashed #cbd5e1;
            padding-top: 8px;
        }
        .ans-c {
            display: inline-block;
            background: #16a34a;
            color: white;
            font-weight: 700;
            padding: 4px 12px;
            border-radius: 6px;
            margin-right: 8px;
        }
        .ans-e {
            display: inline-block;
            background: #dc2626;
            color: white;
            font-weight: 700;
            padding: 4px 12px;
            border-radius: 6px;
            margin-right: 8px;
        }
        .explanation {
            margin-top: 12px;
            font-size: 15px;
            color: #1e293b;
        }
        .pdf-quote {
            margin-top: 12px;
            padding: 10px 12px;
            background: #f8fafc;
            border-left: 4px solid #3b82f6;
            font-size: 13px;
            color: #334155;
        }
        """,
    )

    deck = genanki.Deck(deck_id, deck_name)

    for a in assertions:
        ans = a.get("answer", "C")
        ans_badge = (
            '<span class="ans-c">GABARITO: CERTO</span>'
            if ans == "C"
            else '<span class="ans-e">GABARITO: ERRADO</span>'
        )
        pdf_ref = ""
        if a.get("pdf_quote") or a.get("pdf_page"):
            page_str = f" ({a['pdf_page']})" if a.get("pdf_page") else ""
            pdf_ref = f"<em>\"{a.get('pdf_quote', '')}\"</em>{page_str}"

        note = genanki.Note(
            model=cebraspe_model,
            fields=[
                str(subject),
                str(a.get("subtopic", "Geral")),
                str(a.get("recurrence_level", "Alta")),
                str(a.get("command_text", "")),
                f"<strong>{a.get('item_number', '')}.</strong> {a.get('statement', '')}",
                ans_badge,
                str(a.get("explanation", "")),
                pdf_ref,
                str(a.get("trap_type", "Conceito")),
            ],
            tags=[
                "Cebraspe",
                f"Materia::{_sanitize_tag(subject)}",
                f"Subtopico::{_sanitize_tag(a.get('subtopic', 'Geral'))}",
                f"Recorrencia::{_sanitize_tag(a.get('recurrence_level', 'Alta'))}",
            ],
        )
        deck.add_note(note)

    with tempfile.NamedTemporaryFile(suffix=".apkg", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    pkg = genanki.Package(deck)
    pkg.write_to_file(str(tmp_path))
    data = tmp_path.read_bytes()
    try:
        tmp_path.unlink()
    except Exception:
        pass
    return data


def export_to_anki_csv(battery: Dict[str, Any], filter_mode: str = "all") -> str:
    assertions = filter_assertions_for_export(battery.get("assertions", []), filter_mode)
    subject = battery.get("subject", "Concurso")

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    for a in assertions:
        ans_str = "CERTO" if a.get("answer") == "C" else "ERRADO"
        front = f"[{subject} — {a.get('subtopic', '')}] {a.get('command_text', '')}<br><br><b>{a.get('item_number')}. {a.get('statement', '')}</b>"
        back = (
            f"<b>GABARITO: {ans_str}</b> ({a.get('trap_type', '')})<br><br>"
            f"{a.get('explanation', '')}<br><br>"
            f"<i>Trecho PDF ({a.get('pdf_page', '')}): \"{a.get('pdf_quote', '')}\"</i>"
        )
        tags = f"Cebraspe {_sanitize_tag(subject)} {_sanitize_tag(a.get('subtopic', 'Geral'))}"
        writer.writerow([front, back, tags])
    return output.getvalue()


def export_to_markdown(battery: Dict[str, Any], filter_mode: str = "all") -> str:
    assertions = filter_assertions_for_export(battery.get("assertions", []), filter_mode)
    subject = battery.get("subject", "Disciplina")
    title = battery.get("title", "Bateria Cebraspe")
    area = battery.get("area", "Geral")

    lines = [
        f"# Caderno de Assertivas Cebraspe — {title}",
        f"**Disciplina:** {subject} | **Área:** {area} | **Total de Itens:** {len(assertions)}",
        "",
        "> **Instruções (Padrão Cebraspe):** Julgue cada item a seguir como **CERTO (C)** ou **ERRADO (E)**. Clique em *Ver Gabarito e Comentário* abaixo de cada item para conferir a resolução fundamentada no seu PDF.",
        "",
        "---",
        "",
    ]

    last_cmd = None
    for a in assertions:
        cmd = a.get("command_text", "")
        if cmd != last_cmd:
            lines.append(f"### {cmd}")
            lines.append("")
            last_cmd = cmd

        ans_full = "CERTO" if a.get("answer") == "C" else "ERRADO"
        lines.append(
            f"**{a.get('item_number')}.** *[{a.get('subtopic')} | Recorrência: {a.get('recurrence_level')}]* {a.get('statement')}"
        )
        lines.append("- `( ) CERTO`   `( ) ERRADO`")
        lines.append("")
        lines.append("<details>")
        lines.append(f"<summary><strong>Ver Gabarito e Comentário (Item {a.get('item_number')})</strong></summary>")
        lines.append("")
        lines.append(f"- **Gabarito Oficial:** `{ans_full}`")
        lines.append(f"- **Técnica / Pegadinha Cebraspe:** `{a.get('trap_type', 'Conceito')}`")
        lines.append(f"- **Comentário:** {a.get('explanation', '')}")
        if a.get("pdf_quote") or a.get("pdf_page"):
            lines.append(f"- **Referência no PDF ({a.get('pdf_page', '')}):** *\"{a.get('pdf_quote', '')}\"*")
        if a.get("inspired_by_real_question"):
            lines.append(f"- **Base de Incidência:** {a.get('inspired_by_real_question')}")
        lines.append("")
        lines.append("</details>")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _latin1_safe(text: str) -> str:
    replacements = {
        "\u2013": "-",
        "\u2014": " - ",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2022": "*",
        "\u2026": "...",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode("latin-1", errors="replace").decode("latin-1")


class CebraspeExamPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(80, 90, 105)
        self.cell(0, 7, _latin1_safe("CEBRASPE / CESPE - CADERNO DE ASSERTIVAS INEDITAS ORIENTADAS POR RECORRENCIA"), border="B", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 130, 140)
        self.cell(0, 10, _latin1_safe(f"Pagina {self.page_no()}"), align="C")


def export_to_pdf_bytes(battery: Dict[str, Any], filter_mode: str = "all") -> bytes:
    assertions = filter_assertions_for_export(battery.get("assertions", []), filter_mode)
    subject = battery.get("subject", "Disciplina")
    title = battery.get("title", "Bateria Cebraspe")
    area = battery.get("area", "Geral")

    pdf = CebraspeExamPDF()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()

    def write_block(h: float, txt: str, fill: bool = False) -> None:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, h, _latin1_safe(txt), fill=fill, new_x="LMARGIN", new_y="NEXT")

    # Título da Prova
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(15, 23, 42)
    write_block(7, f"{subject.upper()} - {title}")
    pdf.ln(1)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(71, 85, 105)
    write_block(
        5,
        f"Area: {area}  |  Total de Itens: {len(assertions)}  |  Sistema de Pontuacao: 1 errada anula 1 certa (Gabarito nas paginas finais)",
    )
    pdf.ln(4)

    # Parte 1: Caderno de Questões
    last_cmd = None
    for a in assertions:
        cmd = a.get("command_text", "")
        if cmd != last_cmd:
            pdf.ln(2)
            pdf.set_font("Helvetica", "BI", 10)
            pdf.set_text_color(30, 41, 59)
            write_block(5.5, cmd)
            pdf.ln(1)
            last_cmd = cmd

        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(100, 116, 139)
        write_block(
            4.5,
            f"[Subtopico: {a.get('subtopic', '')} | Recorrencia Cebraspe: {a.get('recurrence_level', '')}]",
        )

        pdf.set_font("Helvetica", "", 10.5)
        pdf.set_text_color(15, 23, 42)
        write_block(5.5, f"{a.get('item_number')}. {a.get('statement', '')}")

        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(51, 65, 85)
        pdf.set_x(pdf.l_margin)
        pdf.cell(0, 6, _latin1_safe("Julgue:   (   ) CERTO       (   ) ERRADO       (   ) EM BRANCO"), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    # Parte 2: Gabarito Definitivo e Comentado no Final
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(15, 23, 42)
    pdf.set_x(pdf.l_margin)
    pdf.cell(0, 8, _latin1_safe("GABARITO OFICIAL E COMENTARIOS DETALHADOS"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # Grade de Gabarito Rápido
    quick_grid = "  |  ".join([f"{a.get('item_number')}: {a.get('answer')}" for a in assertions])
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_fill_color(241, 245, 249)
    write_block(6, f"Gabarito Rapido:  {quick_grid}", fill=True)
    pdf.ln(5)

    for a in assertions:
        ans_label = "CERTO" if a.get("answer") == "C" else "ERRADO"
        pdf.set_font("Helvetica", "B", 10.5)
        if a.get("answer") == "C":
            pdf.set_text_color(22, 101, 52)
        else:
            pdf.set_text_color(185, 28, 28)

        write_block(
            5.5,
            f"Item {a.get('item_number')} - GABARITO: {ans_label}  [{a.get('trap_type', 'Conceito')} | {a.get('pdf_page', '')}]",
        )

        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(30, 41, 59)
        write_block(5, f"Comentario: {a.get('explanation', '')}")

        if a.get("pdf_quote"):
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_text_color(71, 85, 105)
            write_block(4.8, f"Trecho do PDF ({a.get('pdf_page', '')}): \"{a.get('pdf_quote', '')}\"")

        pdf.ln(3)

    return bytes(pdf.output())
