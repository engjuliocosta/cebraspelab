import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from exporters import (
    export_to_anki_apkg,
    export_to_anki_csv,
    export_to_markdown,
    export_to_pdf_bytes,
    filter_assertions_for_export,
)


class TestExporters(unittest.TestCase):
    def setUp(self) -> None:
        self.sample_battery = {
            "id": 99,
            "title": "Bateria Teste Exportação",
            "subject": "Direito Constitucional",
            "area": "Tribunais / Jurídico",
            "assertions": [
                {
                    "id": 1,
                    "item_number": 1,
                    "subtopic": "Direitos e Garantias Individuais",
                    "recurrence_level": "Muito Alta",
                    "command_text": "Acerca dos direitos fundamentais, julgue o item.",
                    "statement": "A casa é asilo inviolável do indivíduo, ninguém nela podendo penetrar sem consentimento do morador, salvo em caso de flagrante delito ou desastre, ou para prestar socorro, ou, durante o dia, por determinação judicial.",
                    "answer": "C",
                    "explanation": "Literalidade do art. 5º, XI, da CF/88.",
                    "pdf_quote": "Art. 5º, XI - a casa é asilo inviolável...",
                    "pdf_page": "p. 3",
                    "trap_type": "Literalidade / Conceito Exato",
                    "is_correct": 1,
                    "is_favorite": False,
                },
                {
                    "id": 2,
                    "item_number": 2,
                    "subtopic": "Remédios Constitucionais",
                    "recurrence_level": "Alta",
                    "command_text": "Acerca dos remédios constitucionais, julgue o item.",
                    "statement": "Qualquer pessoa física ou jurídica é parte legítima para propor ação popular que vise anular ato lesivo ao patrimônio público.",
                    "answer": "E",
                    "explanation": "Somente o CIDADÃO (no gozo dos direitos políticos) tem legitimidade ativa para propor ação popular (art. 5º, LXXIII).",
                    "pdf_quote": "Qualquer cidadão é parte legítima para propor ação popular...",
                    "pdf_page": "p. 9",
                    "trap_type": "Inversão de Conceito",
                    "is_correct": 0,
                    "is_favorite": True,
                },
            ],
        }

    def test_filter_assertions_for_export(self) -> None:
        items = self.sample_battery["assertions"]
        self.assertEqual(len(filter_assertions_for_export(items, "all")), 2)
        self.assertEqual(len(filter_assertions_for_export(items, "errors_only")), 1)
        self.assertEqual(len(filter_assertions_for_export(items, "favorites_only")), 1)
        self.assertEqual(len(filter_assertions_for_export(items, "errors_or_favorites")), 1)

    def test_export_to_anki_apkg_generates_valid_zip_package(self) -> None:
        apkg_bytes = export_to_anki_apkg(self.sample_battery, filter_mode="all")
        self.assertGreater(len(apkg_bytes), 500)
        # Arquivos .apkg são arquivos ZIP iniciados por PK\x03\x04
        self.assertEqual(apkg_bytes[:2], b"PK")

    def test_export_to_anki_csv(self) -> None:
        csv_str = export_to_anki_csv(self.sample_battery, filter_mode="all")
        self.assertIn("GABARITO: CERTO", csv_str)
        self.assertIn("GABARITO: ERRADO", csv_str)
        self.assertIn("Direito_Constitucional", csv_str)

    def test_export_to_markdown_with_collapsible_details(self) -> None:
        md_str = export_to_markdown(self.sample_battery, filter_mode="all")
        self.assertIn("<details>", md_str)
        self.assertIn("Ver Gabarito e Comentário", md_str)
        self.assertIn("Inversão de Conceito", md_str)

    def test_export_to_pdf_bytes_generates_valid_pdf(self) -> None:
        pdf_bytes = export_to_pdf_bytes(self.sample_battery, filter_mode="all")
        self.assertGreater(len(pdf_bytes), 1000)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()

