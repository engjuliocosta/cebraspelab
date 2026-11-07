import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import adaptive_tutor
import database
import main
import storage_manager


class TestAdaptiveTutorAndDiscursive(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp_dir.name)
        self.orig_db = database.DB_PATH
        self.orig_vault = storage_manager.VAULT_DIR
        self.orig_nosql = storage_manager.NOSQL_PATH

        database.DB_PATH = tmp_path / "test_tutor.db"
        storage_manager.VAULT_DIR = tmp_path / "pdf_vault"
        storage_manager.NOSQL_PATH = tmp_path / "nosql_tutor.json"

        database.init_db()
        storage_manager.init_storage_tables()

    def tearDown(self) -> None:
        database.DB_PATH = self.orig_db
        storage_manager.VAULT_DIR = self.orig_vault
        storage_manager.NOSQL_PATH = self.orig_nosql
        self.tmp_dir.cleanup()

    def test_weakness_diagnosis_summary_fixation_and_5lines_discursive(self) -> None:
        # 1. Criar bateria base e registrar um erro do aluno
        demo_bat = main.create_demo_battery()
        mat_id = demo_bat["material_id"]
        first_assertion = demo_bat["assertions"][0]
        wrong_choice = "C" if first_assertion["answer"] == "E" else "E"
        database.record_assertion_answer(first_assertion["id"], wrong_choice)

        # 2. Gerar diagnóstico a partir do PDF armazenado
        diag = adaptive_tutor.build_weakness_diagnosis_and_study_plan(material_id=mat_id)
        self.assertEqual(diag["material_id"], mat_id)
        self.assertIn("content_summary", diag)
        self.assertEqual(
            diag["content_summary"]["target_subtopic"],
            first_assertion["subtopic"],
        )
        self.assertGreaterEqual(len(diag["content_summary"]["key_periods_from_pdf"]), 1)

        # 3. Verificar questão discursiva de 5 linhas gerada sobre o conceito errado
        disc_q = diag["discursive_question"]
        self.assertEqual(disc_q["max_lines"], 5)
        self.assertIn(first_assertion["subtopic"], disc_q["prompt_text"])

        # 4. Aluno digita resposta de até 5 linhas e salva no banco de dados (SQL + NoSQL)
        student_answer = (
            "A revogação do ato administrativo decorre de juízo de mérito (conveniência e oportunidade) "
            "e compete exclusivamente à Administração Pública que editou o ato, com efeitos ex nunc.\n"
            "Já o Poder Judiciário exerce apenas controle de legalidade (anulação com efeitos ex tunc), "
            "sendo-lhe vedado revogar atos administrativos de outros Poderes."
        )
        saved_eval = adaptive_tutor.submit_and_save_discursive_5lines_answer(
            question_id=disc_q["id"],
            student_text=student_answer,
            api_key="",
        )
        self.assertGreater(saved_eval["response_id"], 0)
        self.assertLessEqual(saved_eval["lines_used"], 5)
        self.assertGreaterEqual(saved_eval["score"], 5.0)

        # 5. Verificar que a resposta discursiva ficou persistida no SQL e no NoSQL
        history = adaptive_tutor.list_saved_discursive_responses(material_id=mat_id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["student_text"], student_answer)

        nosql_store = storage_manager.NoSQLDocumentStore(storage_manager.NOSQL_PATH)
        nosql_eval = nosql_store.find_by_id("discursive_evaluations", str(saved_eval["response_id"]))
        self.assertIsNotNone(nosql_eval)

        # 6. Gerar mais questões de fixação a partir do PDF armazenado
        fixation_bat = adaptive_tutor.generate_more_fixation_questions_from_stored_pdf(
            material_id=mat_id,
            target_subtopic=first_assertion["subtopic"],
            variations_per_period=3,
        )
        self.assertGreaterEqual(len(fixation_bat["assertions"]), 4)


if __name__ == "__main__":
    unittest.main()

