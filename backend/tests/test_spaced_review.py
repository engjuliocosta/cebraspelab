import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import database
import spaced_review
import storage_manager


class TestSpacedReviewModule(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)
        self.db_path = self.base_path / "test_spaced_review.db"
        self.vault_path = self.base_path / "pdf_vault"
        self.nosql_path = self.base_path / "nosql_store.json"

        self.orig_db_path = database.DB_PATH
        self.orig_vault_dir = storage_manager.VAULT_DIR
        self.orig_nosql_path = storage_manager.NOSQL_PATH

        database.DB_PATH = self.db_path
        storage_manager.VAULT_DIR = self.vault_path
        storage_manager.NOSQL_PATH = self.nosql_path

        database.init_db()
        storage_manager.init_storage_tables()
        spaced_review.init_spaced_review_tables()
        self.nosql_store = storage_manager.NoSQLDocumentStore(self.nosql_path)

        # Inserir material e bateria com questão errada para apresentar o conceito ao aluno
        self.mat_id = database.save_study_material(
            title="1. Tutela Provisória",
            subject="Direito Processual Civil",
            area="Jurídica",
            total_pages=2,
            pages=[
                {
                    "page_number": 1,
                    "text": "1. Tutela Provisória\n1.1 Tutela de Urgência\nA tutela de urgência será concedida quando houver elementos que evidenciem a probabilidade do direito e o perigo de dano.",
                }
            ],
            extracted_questions=[],
            recurrence_map=[
                {
                    "topic": "1. Tutela Provisória",
                    "subtopic": "1.1 Tutela de Urgência",
                    "recurrence_level": "Muito Alta",
                    "estimated_percentage": 40.0,
                    "focus_points": ["Probabilidade do direito e perigo de dano"],
                    "common_traps": ["Troca de requisitos cumulativos por alternativos"],
                    "pages_reference": "p. 1",
                }
            ],
        )

        self.battery_id = database.save_question_battery(
            material_id=self.mat_id,
            title="1. Tutela Provisória",
            subject="Direito Processual Civil",
            area="Jurídica",
            depth="Todo o PDF",
            recurrence_summary=[],
            assertions=[
                {
                    "subtopic": "1.1 Tutela de Urgência",
                    "recurrence_level": "Muito Alta",
                    "command_text": "Julgue o item a seguir.",
                    "statement": "A tutela de urgência dispensa a demonstração do perigo de dano bastando a probabilidade do direito.",
                    "answer": "E",
                    "explanation": "ITEM ERRADO. Exige cumulativamente probabilidade do direito e perigo de dano.",
                    "pdf_quote": "A tutela de urgência será concedida quando houver elementos que evidenciem a probabilidade do direito e o perigo de dano.",
                    "pdf_page": "p. 1",
                    "trap_type": "Inversão de Requisito Cumulativo",
                    "difficulty": "Média",
                }
            ],
        )
        bat = database.get_battery(self.battery_id)
        self.assertion_id = bat["assertions"][0]["id"]
        # Aluno erra a questão (marca 'C' quando o gabarito é 'E')
        database.record_assertion_answer(self.assertion_id, "C")

    def tearDown(self):
        database.DB_PATH = self.orig_db_path
        storage_manager.VAULT_DIR = self.orig_vault_dir
        storage_manager.NOSQL_PATH = self.orig_nosql_path
        self.temp_dir.cleanup()

    def test_present_concepts_and_save_student_error_summary_with_hierarchy(self):
        # 1. Verificar apresentação do conceito a partir das questões erradas e tópicos disponíveis
        hierarchy_data = spaced_review.get_available_concepts_and_hierarchy(self.mat_id)
        self.assertGreaterEqual(len(hierarchy_data["presented_concepts_from_errors"]), 1)
        self.assertGreaterEqual(len(hierarchy_data["available_topics_and_subtopics"]), 1)

        presented = hierarchy_data["presented_concepts_from_errors"][0]
        self.assertEqual(presented["assertion_id"], self.assertion_id)
        self.assertEqual(presented["suggested_subtopic"], "1.1 Tutela de Urgência")

        # 2. Aluno cria o resumo da resposta errada indicando Tópico -> Subtópico -> Conceito -> Subconceito
        saved = spaced_review.create_student_error_summary_note(
            topic="1. Tutela Provisória",
            subtopic="1.1 Tutela de Urgência",
            concept="Requisitos da Tutela de Urgência (Art. 300 do CPC)",
            subconcept="Cumulatividade entre fumus boni iuris e periculum in mora",
            student_summary="A concessão da tutela provisória de urgência exige, de forma cumulativa, a probabilidade do direito e o perigo de dano ou o risco ao resultado útil do processo.",
            personal_notes="Cuidado: Cebraspe troca 'e' por 'ou' dizendo que basta um dos requisitos.",
            presented_concept_context=presented["presented_concept_context"],
            subject="Direito Processual Civil",
            material_id=self.mat_id,
            assertion_id=self.assertion_id,
            trap_type=presented["trap_type"],
            pdf_page="p. 1",
            review_interval_days=3,
            nosql_store=self.nosql_store,
        )

        self.assertGreater(saved["id"], 0)
        self.assertGreater(saved["relationship_link_id"], 0)
        self.assertEqual(saved["review_interval_days"], 3)
        self.assertEqual(saved["review_cycle_count"], 0)

        # Verificar persistência NoSQL
        nosql_doc = self.nosql_store.find_by_id(
            "student_error_summaries_overview", str(saved["id"])
        )
        self.assertIsNotNone(nosql_doc)
        self.assertEqual(
            nosql_doc["concept"], "Requisitos da Tutela de Urgência (Art. 300 do CPC)"
        )

        # Verificar criação do relacionamento na árvore Tópico -> Subtópico -> Conceito -> Subconceito
        updated_hierarchy = spaced_review.get_available_concepts_and_hierarchy(self.mat_id)
        self.assertEqual(len(updated_hierarchy["concept_relationships"]), 1)
        rel = updated_hierarchy["concept_relationships"][0]
        self.assertEqual(rel["topic"], "1. Tutela Provisória")
        self.assertEqual(rel["subtopic"], "1.1 Tutela de Urgência")
        self.assertEqual(rel["concept"], "Requisitos da Tutela de Urgência (Art. 300 do CPC)")
        self.assertEqual(
            rel["subconcept"], "Cumulatividade entre fumus boni iuris e periculum in mora"
        )
        self.assertIn(saved["id"], rel["summary_ids"])

    def test_3day_spaced_review_schedule_and_generate_10_questions(self):
        # 1. Salvar resumo de erro do aluno
        saved = spaced_review.create_student_error_summary_note(
            topic="1. Tutela Provisória",
            subtopic="1.1 Tutela de Urgência",
            concept="Requisitos da Tutela de Urgência",
            subconcept="Probabilidade do direito e perigo de dano",
            student_summary="A tutela de urgência somente pode ser deferida quando presentes cumulativamente a probabilidade do direito e o perigo de dano ou risco ao resultado útil do processo.",
            personal_notes="Revisar art. 300 do CPC a cada 3 dias.",
            presented_concept_context="A tutela de urgência será concedida quando houver elementos que evidenciem a probabilidade do direito e o perigo de dano.",
            subject="Direito Processual Civil",
            material_id=self.mat_id,
            assertion_id=self.assertion_id,
            review_interval_days=3,
            nosql_store=self.nosql_store,
        )

        # 2. No momento da criação (dia 0), ainda não venceu o ciclo de 3 dias
        overview_day0 = spaced_review.list_student_error_summaries_overview(
            material_id=self.mat_id
        )
        self.assertEqual(overview_day0["total_summaries"], 1)
        self.assertEqual(overview_day0["due_for_review_count"], 0)
        self.assertFalse(overview_day0["review_alert_active"])
        self.assertFalse(overview_day0["items"][0]["is_due_for_3day_review"])
        self.assertEqual(overview_day0["items"][0]["days_until_review"], 3)

        # 3. Avançar o relógio em 3 dias + 1 hora -> O sistema detecta que a revisão de 3 em 3 dias está vencida!
        future_3days = datetime.now() + timedelta(days=3, hours=1)
        overview_day3 = spaced_review.list_student_error_summaries_overview(
            material_id=self.mat_id,
            reference_time=future_3days,
        )
        self.assertEqual(overview_day3["due_for_review_count"], 1)
        self.assertTrue(overview_day3["review_alert_active"])
        self.assertTrue(overview_day3["items"][0]["is_due_for_3day_review"])

        # 4. Disparar a revisão de 3 em 3 dias -> Deve gerar exatamente 10 questões sobre o tópico/conceito anotado
        trigger_res = spaced_review.trigger_3day_spaced_review_and_generate_10_questions(
            questions_count=10,
            force_all_if_none_due=False,
            reference_time=future_3days,
            nosql_store=self.nosql_store,
        )
        self.assertEqual(trigger_res["reviewed_summaries_count"], 1)
        self.assertEqual(trigger_res["questions_generated_count"], 10)
        self.assertEqual(len(trigger_res["battery"]["assertions"]), 10)

        # Verificar que existem assertivas C e E nas 10 questões geradas
        answers = {a["answer"] for a in trigger_res["battery"]["assertions"]}
        self.assertIn("C", answers)
        self.assertIn("E", answers)

        # 5. Verificar que o ciclo foi incrementado (`review_cycle_count = 1`) e reagendado para +3 dias (dia 6)
        overview_after_trigger = spaced_review.list_student_error_summaries_overview(
            material_id=self.mat_id,
            reference_time=future_3days,
        )
        self.assertEqual(overview_after_trigger["due_for_review_count"], 0)
        self.assertEqual(overview_after_trigger["items"][0]["review_cycle_count"], 1)
        self.assertEqual(overview_after_trigger["items"][0]["days_until_review"], 3)
        self.assertEqual(len(overview_after_trigger["cycles_history"]), 1)

        # 6. Testar disparo direto pela árvore de relacionamento (`relationship_link_id`)
        rel_trigger = spaced_review.trigger_3day_spaced_review_and_generate_10_questions(
            relationship_link_id=saved["relationship_link_id"],
            questions_count=10,
            nosql_store=self.nosql_store,
        )
        self.assertEqual(rel_trigger["questions_generated_count"], 10)

    def test_adaptive_spaced_intervals_3_7_15_30_based_on_85pct_accuracy(self):
        # 1. Criar resumo de erro com intervalo inicial = 3 dias
        saved = spaced_review.create_student_error_summary_note(
            topic="1. Tutela Provisória",
            subtopic="1.1 Tutela de Urgência",
            concept="Requisitos da Tutela de Urgência",
            subconcept="Cumulatividade de requisitos",
            student_summary="A tutela de urgência exige cumulativamente probabilidade do direito e perigo de dano.",
            material_id=self.mat_id,
            assertion_id=self.assertion_id,
            review_interval_days=3,
            nosql_store=self.nosql_store,
        )

        # 2. Disparar revisão de 3 dias (gera 10 questões)
        triggered = spaced_review.trigger_3day_spaced_review_and_generate_10_questions(
            summary_ids=[saved["id"]],
            questions_count=10,
            nosql_store=self.nosql_store,
        )
        cycle_id = triggered["cycle_id"]
        assertions = triggered["battery"]["assertions"]

        # 3. Aluno responde acertando 9 de 10 questões (90% >= 85%) -> intervalo deve subir de 3 para 7 dias!
        for idx, a in enumerate(assertions):
            choice = a["answer"] if idx < 9 else ("E" if a["answer"] == "C" else "C")
            database.record_assertion_answer(a["id"], choice)

        eval_7d = spaced_review.evaluate_spaced_review_cycle_and_adapt_intervals(
            cycle_id=cycle_id, nosql_store=self.nosql_store
        )
        self.assertTrue(eval_7d["mastery_achieved"])
        self.assertEqual(eval_7d["accuracy_percentage"], 90.0)
        self.assertEqual(eval_7d["updated_summaries"][0]["review_interval_days"], 7)

        # 4. Novo ciclo com >= 85% (10/10 = 100%) -> intervalo sobe de 7 para 15 dias, e depois para 30 dias!
        self.assertEqual(spaced_review.compute_next_adaptive_interval(7, 0.90), 15)
        self.assertEqual(spaced_review.compute_next_adaptive_interval(15, 0.85), 30)
        self.assertEqual(spaced_review.compute_next_adaptive_interval(30, 1.00), 30)

        # 5. Se o aluno errar mais que 15% (ex: acertar 6 de 10 = 60% < 85%), o intervalo volta para 3 dias!
        for idx, a in enumerate(assertions):
            choice = a["answer"] if idx < 6 else ("E" if a["answer"] == "C" else "C")
            database.record_assertion_answer(a["id"], choice)

        eval_reset_3d = spaced_review.evaluate_spaced_review_cycle_and_adapt_intervals(
            cycle_id=cycle_id, nosql_store=self.nosql_store
        )
        self.assertFalse(eval_reset_3d["mastery_achieved"])
        self.assertEqual(eval_reset_3d["updated_summaries"][0]["review_interval_days"], 3)

    def test_acertei_com_duvida_queues_assertion_directly_to_3day_review(self):
        # Aluno respondeu a questão acertando o gabarito ('E'), mas clicou em "Acertei com Dúvida"
        database.record_assertion_answer(self.assertion_id, "E")
        queued = spaced_review.queue_doubt_assertion_to_3day_review(
            assertion_id=self.assertion_id,
            student_doubt_note="Acertei que era Errado, mas fiquei em dúvida se cabia em tutela da evidência.",
            nosql_store=self.nosql_store,
        )
        self.assertFalse(queued["already_queued"])
        self.assertTrue(queued["assertion"]["answered_with_doubt"])
        self.assertTrue(queued["assertion"]["is_favorite"])
        self.assertEqual(queued["summary_record"]["review_interval_days"], 3)

        overview = spaced_review.list_student_error_summaries_overview(material_id=self.mat_id)
        self.assertEqual(overview["total_summaries"], 1)

    def test_contrastive_concept_battle_generator(self):
        pairs = spaced_review.list_contrastive_concept_pairs()
        self.assertGreaterEqual(len(pairs), 4)

        battle = spaced_review.generate_contrastive_concept_battle_battery(
            pair_id="anulacao_vs_revogacao",
            questions_count=8,
        )
        self.assertEqual(len(battle["battery"]["assertions"]), 8)
        answers = {a["answer"] for a in battle["battery"]["assertions"]}
        self.assertEqual(answers, {"C", "E"})


if __name__ == "__main__":
    unittest.main()
