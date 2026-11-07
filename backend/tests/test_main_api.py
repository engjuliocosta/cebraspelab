import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import database
import main
import storage_manager


class TestMainApiEndpoints(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp_dir.name)
        self.orig_db_path = database.DB_PATH
        self.orig_vault = storage_manager.VAULT_DIR
        self.orig_nosql = storage_manager.NOSQL_PATH

        database.DB_PATH = tmp_path / "test_api.db"
        storage_manager.VAULT_DIR = tmp_path / "pdf_vault"
        storage_manager.NOSQL_PATH = tmp_path / "nosql_api.json"

        database.init_db()
        storage_manager.init_storage_tables()

    def tearDown(self) -> None:
        database.DB_PATH = self.orig_db_path
        storage_manager.VAULT_DIR = self.orig_vault
        storage_manager.NOSQL_PATH = self.orig_nosql
        self.tmp_dir.cleanup()

    def test_full_api_workflow_sync(self) -> None:
        # 1. Health & Settings
        h = main.health_check()
        self.assertEqual(h["status"], "ok")

        s = main.save_settings_endpoint(
            main.SettingsUpdateRequest(default_area="Tribunais / Jurídico")
        )
        self.assertEqual(s["default_area"], "Tribunais / Jurídico")

        # 2. Criar bateria demo e verificar persistência de material
        demo_bat = main.create_demo_battery()
        mat_id = demo_bat["material_id"]
        self.assertGreater(mat_id, 0)

        # 3. Extrair múltiplas assertivas diretamente de todos os períodos dos subtópicos (3x por período)
        period_battery = main.extract_period_assertions_endpoint(
            material_id=mat_id,
            payload=main.ExtractPeriodsRequest(
                variations_per_period=3,
                title="Bateria Completa por Períodos",
                subject="Direito Administrativo",
                area="Tribunais / Jurídico",
            ),
        )
        self.assertGreaterEqual(len(period_battery["assertions"]), 12)

        # 4. Responder item com erro e testar Mentoria + Discursiva 5 Linhas
        first_item = period_battery["assertions"][0]
        wrong_choice = "E" if first_item["answer"] == "C" else "C"
        ans_res = main.answer_assertion_endpoint(
            assertion_id=first_item["id"],
            payload=main.AnswerAssertionRequest(user_answer=wrong_choice, is_favorite=True),
        )
        self.assertEqual(ans_res["is_correct"], 0)

        diag = main.tutor_diagnosis_endpoint(material_id=mat_id)
        self.assertEqual(diag["material_id"], mat_id)
        disc_q_id = diag["discursive_question"]["id"]

        disc_sub = main.tutor_submit_discursive_endpoint(
            main.SubmitDiscursiveAnswerRequest(
                question_id=disc_q_id,
                student_text="A revogação é ato privativo da Administração por mérito com efeitos ex nunc, enquanto a anulação decorre de ilegalidade e tem efeitos ex tunc.",
            )
        )
        self.assertGreater(disc_sub["response_id"], 0)

        hist = main.tutor_discursive_history_endpoint(material_id=mat_id)
        self.assertEqual(len(hist), 1)

        fix_bat = main.tutor_generate_fixation_endpoint(
            main.GenerateFixationFromPdfRequest(
                material_id=mat_id,
                target_subtopic=first_item["subtopic"],
                variations_per_period=2,
            )
        )
        self.assertGreaterEqual(len(fix_bat["assertions"]), 4)

        # 5. Exportar nos 4 formatos (apkg, csv, pdf, md)
        for fmt in ("apkg", "csv", "pdf", "md"):
            resp = main.export_battery_endpoint(period_battery["id"], fmt, filter_mode="all")
            self.assertEqual(resp.status_code, 200)
            self.assertGreater(len(resp.body), 100)

        # 6. Testar endpoints de Revisão Espaçada de 3 em 3 Dias + Relacionamento Tópico -> Subtópico -> Conceito -> Subconceito
        concepts_data = main.spaced_review_concepts_hierarchy_endpoint(material_id=mat_id)
        self.assertGreaterEqual(len(concepts_data["presented_concepts_from_errors"]), 1)

        created_sum = main.create_spaced_review_summary_endpoint(
            main.CreateErrorSummaryNoteRequest(
                material_id=mat_id,
                assertion_id=first_item["id"],
                subject="Direito Administrativo",
                topic="Extinção dos Atos Administrativos",
                subtopic=first_item["subtopic"],
                concept="Diferença entre Anulação e Revogação",
                subconcept="Efeitos ex tunc vs ex nunc e competência",
                student_summary="A revogação recai sobre ato válido por mérito administrativo com efeitos ex nunc, enquanto a anulação recai sobre ato ilegal com efeitos ex tunc.",
                personal_notes="Revisar Súmula 473 do STF no ciclo de 3 em 3 dias.",
                review_interval_days=3,
            )
        )
        self.assertGreater(created_sum["id"], 0)

        overview = main.spaced_review_overview_endpoint(material_id=mat_id, only_due=False)
        self.assertEqual(overview["total_summaries"], 1)

        triggered = main.trigger_spaced_review_endpoint(
            main.TriggerSpacedReviewRequest(
                summary_ids=[created_sum["id"]],
                questions_count=10,
                force_all_if_none_due=True,
            )
        )
        self.assertEqual(triggered["questions_generated_count"], 10)
        self.assertEqual(len(triggered["battery"]["assertions"]), 10)

        # 6b. Testar endpoints de Intervalo Adaptativo (3->7->15->30d), "Acertei com Dúvida" e Pares Contrastivos
        for item in triggered["battery"]["assertions"]:
            main.answer_assertion_endpoint(
                assertion_id=item["id"],
                payload=main.AnswerAssertionRequest(user_answer=item["answer"]),
            )
        adaptive_eval = main.evaluate_adaptive_interval_endpoint(
            main.EvaluateAdaptiveIntervalRequest(
                cycle_id=triggered["cycle_id"],
                battery_id=triggered["battery"]["id"],
            )
        )
        self.assertTrue(adaptive_eval["achieved_mastery"])
        self.assertEqual(adaptive_eval["updated_summaries"][0]["review_interval_days"], 7)

        second_item = period_battery["assertions"][1]
        doubt_queued = main.queue_doubt_assertion_endpoint(
            main.QueueDoubtAssertionRequest(
                assertion_id=second_item["id"],
                student_doubt_note="Acertei mas fiquei inseguro quanto à exceção.",
            )
        )
        self.assertGreater(doubt_queued["summary_record"]["id"], 0)

        cp_list = main.list_contrastive_pairs_endpoint()
        self.assertGreaterEqual(len(cp_list), 4)

        battle = main.generate_contrastive_battle_endpoint(
            main.GenerateContrastiveBattleRequest(
                pair_id="anulacao_vs_revogacao",
                questions_count=6,
            )
        )
        self.assertGreater(battle["battery_id"], 0)
        self.assertEqual(len(battle["battery"]["assertions"]), 6)

        # 7. Testar endpoints de Conectores (FS Local, Rede, Google Drive, Dropbox)
        providers_info = main.list_connector_providers_endpoint()
        self.assertGreaterEqual(len(providers_info["providers"]), 4)
        self.assertIn(".pdf", providers_info["supported_extensions"])
        self.assertIn(".xml", providers_info["supported_extensions"])


if __name__ == "__main__":
    unittest.main()
