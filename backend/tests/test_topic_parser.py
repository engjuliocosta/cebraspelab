import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from topic_parser import (
    detect_period_markers,
    extract_assertions_from_subtopics,
    generate_assertions_from_single_period,
    parse_pdf_topics_and_subtopics,
    split_into_periods,
)


class TestTopicParser(unittest.TestCase):
    def setUp(self) -> None:
        self.sample_pages = [
            {
                "page_number": 1,
                "source_file": "direito_adm.pdf",
                "text": (
                    "1. ATOS ADMINISTRATIVOS\n"
                    "1.1. Conceito e Atributos dos Atos Administrativos\n"
                    "O ato administrativo constitui manifestação unilateral de vontade da administração pública que "
                    "tem por fim imediato adquirir, resguardar, transferir, modificar, extinguir e declarar direitos.\n"
                    "A presunção de legitimidade dos atos administrativos possui natureza relativa (juris tantum), "
                    "admitindo prova em contrário por parte do administrado.\n"
                    "1.2. Extinção: Anulação e Revogação\n"
                    "A administração deve anular seus próprios atos quando eivados de vício de legalidade, "
                    "produzindo efeitos ex tunc, salvo no caso de decadência quinquenal de boa-fé.\n"
                    "Por outro lado, a administração pode revogar o ato discricionário válido por motivo de "
                    "conveniência ou oportunidade, respeitados os direitos adquiridos e produzindo efeitos ex nunc.\n"
                ),
            },
            {
                "page_number": 2,
                "source_file": "direito_adm.pdf",
                "text": (
                    "2. ORGANIZAÇÃO ADMINISTRATIVA\n"
                    "2.1. Desconcentração e Descentralização\n"
                    "A desconcentração administrativa consiste na distribuição interna de competências dentro da "
                    "mesma pessoa jurídica, prescindindo da criação de um novo ente personalizado.\n"
                    "Já a descentralização depende da transferência de atribuições para pessoa jurídica distinta, "
                    "mediante outorga legal ou delegação negocial.\n"
                ),
            },
        ]

    def test_split_into_periods_protects_abbreviations(self) -> None:
        text = (
            "Nos termos do Art. 54 da Lei n. 9.784/1999, o direito da Administração de anular os atos "
            "administrativos de que decorram efeitos favoráveis para os destinatários decai em 5 anos, "
            "salvo comprovada má-fé. "
            "Conforme ensina o Prof. Celso Antônio, a revogação opera efeitos ex nunc e respeita o direito adquirido."
        )
        periods = split_into_periods(text)
        self.assertEqual(len(periods), 2)
        self.assertIn("Art. 54", periods[0])
        self.assertIn("Prof. Celso", periods[1])

    def test_detect_period_markers_identifies_traps(self) -> None:
        p1 = "A administração deve anular os atos ilegais com efeitos ex tunc, salvo comprovada má-fé no prazo de 5 anos."
        markers = detect_period_markers(p1)
        self.assertIn("Exceção / Ressalva", markers)
        self.assertIn("Modalizador (Deve vs. Pode)", markers)
        self.assertIn("Inversão de Conceito (Ex Tunc vs. Ex Nunc)", markers)
        self.assertIn("Prazo / Critério Numérico", markers)

    def test_parse_pdf_topics_and_subtopics_hierarchy(self) -> None:
        structured = parse_pdf_topics_and_subtopics(self.sample_pages)
        self.assertGreaterEqual(len(structured), 3)
        subtopic_names = [s["subtopic"] for s in structured]
        self.assertTrue(any("1.1" in s for s in subtopic_names))
        self.assertTrue(any("1.2" in s for s in subtopic_names))
        self.assertTrue(any("2.1" in s for s in subtopic_names))

        for sec in structured:
            self.assertGreaterEqual(sec["periods_count"], 2)
            self.assertEqual(sec["periods_count"], len(sec["periods"]))
            self.assertGreaterEqual(sec["estimated_questions_capacity"], sec["periods_count"] * 2)

    def test_generate_assertions_from_single_period_creates_certo_and_errado(self) -> None:
        period_obj = {
            "text": "A presunção de legitimidade dos atos administrativos possui natureza relativa (juris tantum), admitindo prova em contrário.",
            "page_number": 4,
            "markers": ["Inversão de Conceito (Relativa vs. Absoluta)"],
        }
        assertions = generate_assertions_from_single_period(
            period_obj=period_obj,
            topic="1. Atos Administrativos",
            subtopic="1.1. Atributos",
            subject="Direito Administrativo",
            max_variations=3,
        )
        self.assertEqual(len(assertions), 3)
        answers = [a["answer"] for a in assertions]
        self.assertIn("C", answers)
        self.assertIn("E", answers)
        # Verifica que a variação errada trocou 'relativa' por 'absoluta'
        wrong_statements = " ".join(a["statement"] for a in assertions if a["answer"] == "E")
        self.assertIn("absoluta", wrong_statements.lower())
        for a in assertions:
            self.assertEqual(a["pdf_page"], "p. 4")
            self.assertEqual(a["pdf_quote"], period_obj["text"])

    def test_extract_assertions_from_subtopics_multiplies_questions(self) -> None:
        structured = parse_pdf_topics_and_subtopics(self.sample_pages)
        total_periods = sum(s["periods_count"] for s in structured)

        # Com variations_per_period=2, deve gerar 2x o número total de períodos
        assertions_2x = extract_assertions_from_subtopics(
            structured_topics=structured,
            subject="Direito Administrativo",
            area="Tribunais / Jurídico",
            variations_per_period=2,
        )
        self.assertEqual(len(assertions_2x), total_periods * 2)

        # Com variations_per_period=3, deve gerar 3x o número total de períodos
        assertions_3x = extract_assertions_from_subtopics(
            structured_topics=structured,
            subject="Direito Administrativo",
            area="Tribunais / Jurídico",
            variations_per_period=3,
        )
        self.assertEqual(len(assertions_3x), total_periods * 3)

        # Verificar respeito a meta customizada por subtópico (questions_per_subtopic)
        custom_map = {s["subtopic"]: 6 for s in structured}
        assertions_custom = extract_assertions_from_subtopics(
            structured_topics=structured,
            subject="Direito Administrativo",
            questions_per_subtopic=custom_map,
            variations_per_period=2,
        )
        self.assertEqual(len(assertions_custom), 6 * len(structured))


if __name__ == "__main__":
    unittest.main()

