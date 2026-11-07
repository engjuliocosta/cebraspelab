import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from gemini_service import (
    _build_pdf_context,
    analyze_pdf_recurrence,
    generate_cebraspe_assertions,
    generate_error_reinforcement,
    test_gemini_connection,
)


class TestGeminiService(unittest.TestCase):
    def setUp(self) -> None:
        self.pages = [
            {
                "page_number": 1,
                "source_file": "licitacoes.pdf",
                "text": (
                    "1. LICITAÇÕES E CONTRATOS (LEI 14.133/2021)\n"
                    "1.1. Modalidades de Licitação\n"
                    "São modalidades de licitação o pregão, a concorrência, o concurso, o leilão e o diálogo competitivo, "
                    "sendo expressamente vedada a criação de outras modalidades ou a combinação destas.\n"
                    "O pregão deve ser adotado obrigatoriamente para aquisição de bens e serviços comuns.\n"
                    "1.2. Dispensa e Inexigibilidade de Licitação\n"
                    "É inexigível a licitação quando inviável a competição, em especial nos casos de fornecedor exclusivo "
                    "e contratação de serviços técnicos especializados de natureza predominantemente intelectual.\n"
                ),
            }
        ]

    def test_build_pdf_context_includes_page_markers(self) -> None:
        ctx = _build_pdf_context(self.pages, max_chars=5000)
        self.assertIn("[Página 1]", ctx)
        self.assertIn("diálogo competitivo", ctx)

    def test_test_gemini_connection_empty_key(self) -> None:
        res = test_gemini_connection("")
        self.assertFalse(res["ok"])
        self.assertIn("Chave de API vazia", res["message"])

    def test_analyze_pdf_recurrence_fallback_uses_parsed_topics_and_periods(self) -> None:
        res = analyze_pdf_recurrence(
            pages=self.pages,
            heuristic_questions=[],
            area="Controle / Fiscal",
            api_key="",  # Testa o motor local determinístico baseado em períodos
            custom_subject_hint="Direito Administrativo",
        )
        self.assertEqual(res["detected_subject"], "Direito Administrativo")
        self.assertGreaterEqual(len(res["subtopics"]), 2)
        for sub in res["subtopics"]:
            self.assertGreaterEqual(sub["periods_count"], 1)
            self.assertGreaterEqual(sub["min_recommended_questions"], 2)

    def test_generate_cebraspe_assertions_fallback_respects_plan_counts(self) -> None:
        analysis = analyze_pdf_recurrence(
            pages=self.pages,
            heuristic_questions=[],
            area="Controle / Fiscal",
            api_key="",
        )
        subtopic_plan = analysis["subtopics"]
        expected_total = sum(s["min_recommended_questions"] for s in subtopic_plan)

        assertions = generate_cebraspe_assertions(
            pages=self.pages,
            real_questions=[],
            subtopic_plan=subtopic_plan,
            subject="Direito Administrativo",
            title="Lei 14.133/2021",
            area="Controle / Fiscal",
            depth="Misto Padrão Cebraspe",
            api_key="",
        )
        self.assertEqual(len(assertions), expected_total)
        answers = {a["answer"] for a in assertions}
        self.assertIn("C", answers)
        self.assertIn("E", answers)

    def test_generate_error_reinforcement_fallback(self) -> None:
        wrong_items = [
            {
                "item_number": 3,
                "subject": "Direito Administrativo",
                "subtopic": "1.1. Modalidades de Licitação",
                "recurrence_level": "Muito Alta",
                "statement": "O pregão pode ser combinado com o leilão.",
                "answer": "E",
                "explanation": "A Lei 14.133/2021 veda a combinação de modalidades.",
                "pdf_quote": "São modalidades de licitação o pregão, a concorrência, o concurso, o leilão e o diálogo competitivo, sendo vedada a combinação destas.",
                "pdf_page": "p. 1",
                "trap_type": "Modalizador / Permissão Indevida",
            }
        ]
        reinforced = generate_error_reinforcement(
            wrong_assertions=wrong_items,
            api_key="",
            questions_per_error=2,
        )
        self.assertEqual(len(reinforced), 2)
        self.assertEqual(reinforced[0]["subtopic"], "1.1. Modalidades de Licitação")


if __name__ == "__main__":
    unittest.main()

