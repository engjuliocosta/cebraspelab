import json
import sys
import unittest
from pathlib import Path
import pymupdf as fitz

sys.path.insert(0, str(Path(__file__).parent.parent))

from pdf_processor import (
    extract_pdf_pages,
    extract_questions_heuristic,
    parse_extra_questions_file,
)


def _create_sample_pdf_bytes() -> bytes:
    doc = fitz.open()
    page1 = doc.new_page()
    page1.insert_textbox(
        fitz.Rect(40, 40, 550, 780),
        "1. CONTROLE DA ADMINISTRAÇÃO PÚBLICA\n"
        "O controle administrativo decorre do poder de autotutela e permite anular atos ilegais.\n"
        "(CEBRASPE / TCU - 2024) Acerca do controle administrativo, julgue o item:\n"
        "A administração pode anular seus próprios atos ilegais com efeitos ex tunc.\n"
        "Gabarito: Certo\n\n"
        "(CESPE / PF - 2023) O Poder Judiciário pode revogar ato administrativo discricionário do Executivo por mérito.\n"
        "Gabarito: Errado",
    )
    page2 = doc.new_page()
    page2.insert_textbox(
        fitz.Rect(40, 40, 550, 780),
        "1.1. Controle Legislativo e Tribunal de Contas\n"
        "O controle externo a cargo do Congresso Nacional é exercido com o auxílio do Tribunal de Contas da União.",
    )
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class TestPdfProcessor(unittest.TestCase):
    def test_extract_pdf_pages_and_questions_heuristic(self) -> None:
        pdf_bytes = _create_sample_pdf_bytes()
        pages = extract_pdf_pages(pdf_bytes, "aula_controle.pdf")
        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[0]["page_number"], 1)
        self.assertEqual(pages[1]["page_number"], 2)
        self.assertIn("autotutela", pages[0]["text"])

        questions = extract_questions_heuristic(pages)
        self.assertGreaterEqual(len(questions), 2)
        answers = [q["answer"] for q in questions]
        self.assertIn("C", answers)
        self.assertIn("E", answers)

    def test_parse_extra_questions_file_json_and_txt(self) -> None:
        json_payload = json.dumps(
            [
                {
                    "banca": "CEBRASPE - 2024",
                    "enunciado": "A autotutela permite à administração rever seus próprios atos quando ilegais.",
                    "gabarito": "C",
                    "assunto": "Controle",
                }
            ]
        ).encode("utf-8")

        parsed_json = parse_extra_questions_file(json_payload, "caderno.json")
        self.assertEqual(len(parsed_json), 1)
        self.assertEqual(parsed_json[0]["answer"], "C")
        self.assertEqual(parsed_json[0]["subtopic"], "Controle")

        txt_payload = (
            "1. A competência administrativa é irrenunciável, salvo os casos de delegação e avocação legalmente admitidos.\n"
            "2. O ato administrativo complexo se aperfeiçoa com a manifestação de um único órgão singular.\n"
        ).encode("utf-8")
        parsed_txt = parse_extra_questions_file(txt_payload, "questoes.txt")
        self.assertEqual(len(parsed_txt), 2)


if __name__ == "__main__":
    unittest.main()

