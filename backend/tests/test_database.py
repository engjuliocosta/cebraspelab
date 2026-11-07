import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import database


class TestDatabase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.orig_db_path = database.DB_PATH
        database.DB_PATH = Path(self.tmp_dir.name) / "test_cebraspe.db"
        database.init_db()

    def tearDown(self) -> None:
        database.DB_PATH = self.orig_db_path
        self.tmp_dir.cleanup()

    def test_settings_crud(self) -> None:
        initial = database.get_settings()
        self.assertEqual(initial["gemini_model"], "gemini-2.5-flash")

        updated = database.update_settings(
            {"gemini_api_key": "AIzaTestKey123456", "gemini_model": "gemini-2.5-pro"}
        )
        self.assertEqual(updated["gemini_api_key"], "AIzaTestKey123456")
        self.assertEqual(updated["gemini_model"], "gemini-2.5-pro")

    def test_materials_and_batteries_lifecycle_and_net_score(self) -> None:
        mat_id = database.save_study_material(
            title="Aula 01 - Poderes Administrativos",
            subject="Direito Administrativo",
            area="Policial",
            total_pages=10,
            pages=[{"page_number": 1, "text": "Poder de polícia é a atividade da administração..."}],
            extracted_questions=[
                {
                    "subtopic": "Poder de Polícia",
                    "exam_info": "CEBRASPE 2024",
                    "statement": "O poder de polícia possui autoexecutoriedade em todas as suas medidas.",
                    "answer": "E",
                }
            ],
            recurrence_map=[{"subtopic": "Poder de Polícia", "recurrence_level": "Muito Alta"}],
        )
        self.assertGreater(mat_id, 0)

        mat = database.get_study_material(mat_id)
        self.assertIsNotNone(mat)
        assert mat is not None
        self.assertEqual(mat["subject"], "Direito Administrativo")
        self.assertEqual(len(mat["extracted_questions"]), 1)

        bat_id = database.save_question_battery(
            material_id=mat_id,
            title="Bateria Poder de Polícia",
            subject="Direito Administrativo",
            area="Policial",
            depth="Misto Padrão Cebraspe",
            recurrence_summary=[{"subtopic": "Poder de Polícia", "recurrence_level": "Muito Alta"}],
            assertions=[
                {
                    "subtopic": "Poder de Polícia",
                    "recurrence_level": "Muito Alta",
                    "command_text": "Julgue os itens a seguir.",
                    "statement": "Item 1 verdadeiro.",
                    "answer": "C",
                    "explanation": "Explicação 1",
                    "pdf_quote": "Citação 1",
                    "pdf_page": "p. 1",
                    "trap_type": "Literalidade",
                },
                {
                    "subtopic": "Poder de Polícia",
                    "recurrence_level": "Muito Alta",
                    "command_text": "Julgue os itens a seguir.",
                    "statement": "Item 2 falso.",
                    "answer": "E",
                    "explanation": "Explicação 2",
                    "pdf_quote": "Citação 2",
                    "pdf_page": "p. 2",
                    "trap_type": "Inversão de Conceito",
                },
                {
                    "subtopic": "Poder de Polícia",
                    "recurrence_level": "Alta",
                    "command_text": "Julgue os itens a seguir.",
                    "statement": "Item 3 verdadeiro.",
                    "answer": "C",
                    "explanation": "Explicação 3",
                    "pdf_quote": "Citação 3",
                    "pdf_page": "p. 3",
                    "trap_type": "Literalidade",
                },
            ],
        )

        bat = database.get_battery(bat_id)
        self.assertIsNotNone(bat)
        assert bat is not None
        assertions = bat["assertions"]
        self.assertEqual(len(assertions), 3)

        # Responder Item 1 Corretamente (C == C -> +1)
        r1 = database.record_assertion_answer(assertions[0]["id"], "C")
        self.assertEqual(r1["is_correct"], 1)

        # Responder Item 2 Erradamente (C != E -> -1, e favoritar)
        r2 = database.record_assertion_answer(
            assertions[1]["id"],
            "C",
            is_favorite=True,
            annotations=[{"wordIndex": 1, "type": "strike"}],
        )
        self.assertEqual(r2["is_correct"], 0)
        self.assertTrue(r2["is_favorite"])
        self.assertEqual(len(r2["annotations"]), 1)

        # Deixar Item 3 em Branco (BLANK -> 0)
        r3 = database.record_assertion_answer(assertions[2]["id"], "BLANK")
        self.assertIsNone(r3["is_correct"])
        self.assertEqual(r3["user_answer"], "BLANK")

        # Verificar Escore Líquido Cebraspe: 1 certa - 1 errada = 0 líquido
        all_bats = database.list_batteries()
        stats = all_bats[0]["stats"]
        self.assertEqual(stats["correct"], 1)
        self.assertEqual(stats["wrong"], 1)
        self.assertEqual(stats["blank"], 1)
        self.assertEqual(stats["net_score"], 0)

        # Verificar Caderno de Erros
        err_nb = database.get_error_notebook()
        self.assertEqual(len(err_nb["items"]), 1)
        self.assertEqual(err_nb["items"][0]["id"], assertions[1]["id"])
        self.assertEqual(err_nb["trap_stats"][0]["trap_type"], "Inversão de Conceito")


if __name__ == "__main__":
    unittest.main()

