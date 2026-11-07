import json
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf as fitz

sys.path.insert(0, str(Path(__file__).parent.parent))

import data_connectors
import database
import main
import multi_folder_workspace
import spaced_review
import storage_manager


class TestMultiFolderWorkspace(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.tmp_dir.name)

        self.orig_db = database.DB_PATH
        self.orig_vault = storage_manager.VAULT_DIR
        self.orig_nosql = storage_manager.NOSQL_PATH

        database.DB_PATH = self.base_path / "test_multifolder.db"
        storage_manager.VAULT_DIR = self.base_path / "pdf_vault"
        storage_manager.NOSQL_PATH = self.base_path / "nosql_multifolder.json"

        database.init_db()
        storage_manager.init_storage_tables()
        spaced_review.init_spaced_review_tables()
        data_connectors.init_connectors_tables()
        multi_folder_workspace.init_multi_folder_tables()
        self.nosql_store = storage_manager.NoSQLDocumentStore(storage_manager.NOSQL_PATH)

        # Criar 3 pastas de estudo diferentes para simular a escolha de múltiplas pastas pelo aluno
        self.folder_const = self.base_path / "Pasta_1_Constitucional"
        self.folder_adm = self.base_path / "Pasta_2_Administrativo"
        self.folder_extra = self.base_path / "Pasta_3_Informatica_e_Backup"

        self.folder_const.mkdir(parents=True, exist_ok=True)
        self.folder_adm.mkdir(parents=True, exist_ok=True)
        self.folder_extra.mkdir(parents=True, exist_ok=True)

        # Arquivo 1 na Pasta 1 (PDF de Direito Constitucional)
        doc = fitz.open()
        page = doc.new_page()
        page.insert_textbox(
            fitz.Rect(40, 40, 550, 750),
            "1. Poder Constituinte\n"
            "1.1 Poder Constituinte Originário e Derivado\n"
            "O poder constituinte originário é inicial, autônomo, ilimitado juridicamente e incondicionado, "
            "não se submetendo a limites materiais impostos pela ordem constitucional anterior.\n"
            "Por sua vez, o poder constituinte derivado reformador submete-se a limitações circunstanciais, "
            "formais e materiais (cláusulas pétreas), sendo vedada a deliberação de proposta de emenda tendente a abolir a forma federativa de Estado.",
            fontsize=11,
        )
        self.pdf_bytes = doc.tobytes()
        doc.close()
        (self.folder_const / "poder_constituinte.pdf").write_bytes(self.pdf_bytes)

        # Arquivo 2 na Pasta 2 (JSON de Direito Administrativo)
        adm_json = [
            {
                "subtopic": "Agentes Públicos e Improbidade",
                "statement": "A configuração dos atos de improbidade administrativa previstos na Lei 8.429/1992 exige a comprovação de conduta dolosa, tendo sido extinta a modalidade culposa após a Lei 14.230/2021.",
                "answer": "C",
                "exam_info": "CEBRASPE - 2024",
            },
            {
                "subtopic": "Nepotismo (Súmula Vinculante 13)",
                "statement": "A vedação ao nepotismo prevista na Súmula Vinculante 13 do STF exige edição de lei formal específica de cada ente federativo para produzir eficácia imediata.",
                "answer": "E",
                "exam_info": "CEBRASPE - 2024",
            },
        ]
        (self.folder_adm / "improbidade_nepotismo.json").write_text(
            json.dumps(adm_json, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Arquivo 3 na Pasta 3 (CSV de Segurança da Informação) + cópia idêntica do PDF da Pasta 1 (para testar deduplicação SHA-256)
        csv_ti = (
            "topico;enunciado;gabarito\n"
            "Segurança da Informação;O ransomware é um tipo de malware que sequestra dados por meio de criptografia e exige pagamento de resgate para restaurar o acesso.;C\n"
            "Assinatura Digital;A assinatura digital garante a confidencialidade da mensagem por padrão, impedindo que terceiros leiam seu conteúdo em trânsito.;E\n"
        )
        (self.folder_extra / "seguranca_redes.csv").write_text(csv_ti, encoding="utf-8")
        # Cópia duplicada exata do PDF da Pasta 1 dentro da Pasta 3
        (self.folder_extra / "copia_backup_poder_constituinte.pdf").write_bytes(self.pdf_bytes)

    def tearDown(self) -> None:
        database.DB_PATH = self.orig_db
        storage_manager.VAULT_DIR = self.orig_vault
        storage_manager.NOSQL_PATH = self.orig_nosql
        self.tmp_dir.cleanup()

    def test_browse_local_folders_and_drives_for_non_technical_users(self) -> None:
        drives_info = multi_folder_workspace.list_available_drives_and_quick_folders()
        self.assertIn("drives", drives_info)
        self.assertGreaterEqual(len(drives_info["drives"]), 1)

        # Navegar na pasta raiz do teste: deve listar as 3 subpastas criadas
        browsed = multi_folder_workspace.browse_local_folders(str(self.base_path))
        subfolder_names = {sf["name"] for sf in browsed["subfolders"]}
        self.assertIn("Pasta_1_Constitucional", subfolder_names)
        self.assertIn("Pasta_2_Administrativo", subfolder_names)
        self.assertIn("Pasta_3_Informatica_e_Backup", subfolder_names)

        # Navegar dentro da Pasta 1: deve detectar 1 arquivo de estudo (.pdf)
        browsed_f1 = multi_folder_workspace.browse_local_folders(str(self.folder_const))
        self.assertEqual(browsed_f1["study_files_count"], 1)
        self.assertEqual(browsed_f1["study_files_in_current"][0]["name"], "poder_constituinte.pdf")

        # Tentar navegar em pasta inexistente deve lançar erro claro
        with self.assertRaises(ValueError):
            multi_folder_workspace.browse_local_folders(str(self.base_path / "nao_existe"))

    def test_workspace_crud_add_and_remove_multiple_folders(self) -> None:
        ws = multi_folder_workspace.create_or_update_multi_folder_workspace(
            name="Meu Pacote de Estudos (2 Pastas)",
            folders=[
                {"path": str(self.folder_const), "label": "Constitucional", "subject": "Direito Constitucional"},
                {"path": str(self.folder_adm), "label": "Administrativo", "subject": "Direito Administrativo"},
            ],
            subject_hint="Direito Público",
            area_hint="Tribunais",
            nosql_store=self.nosql_store,
        )
        self.assertEqual(ws["folders_count"], 2)
        self.assertEqual(len(ws["connection_ids"]), 2)

        # Adicionar uma 3ª pasta ao conjunto existente
        ws_3 = multi_folder_workspace.add_folders_to_workspace(
            workspace_id=ws["id"],
            new_folders=[{"path": str(self.folder_extra), "label": "Informática", "subject": "TI"}],
            nosql_store=self.nosql_store,
        )
        self.assertEqual(ws_3["folders_count"], 3)

        # Remover a 2ª pasta do conjunto
        ws_2 = multi_folder_workspace.remove_folder_from_workspace(
            workspace_id=ws["id"],
            folder_path_to_remove=str(self.folder_adm),
            nosql_store=self.nosql_store,
        )
        self.assertEqual(ws_2["folders_count"], 2)

        all_ws = multi_folder_workspace.list_multi_folder_workspaces()
        self.assertEqual(len(all_ws), 1)

        deleted = multi_folder_workspace.delete_multi_folder_workspace(
            ws["id"], nosql_store=self.nosql_store
        )
        self.assertTrue(deleted)
        self.assertEqual(len(multi_folder_workspace.list_multi_folder_workspaces()), 0)

    def test_scan_multiple_folders_deduplicates_sha256_and_builds_unified_battery(self) -> None:
        # Escanear as 3 pastas simultaneamente via endpoint do FastAPI
        scan_res = main.scan_multiple_folders_endpoint(
            main.ScanMultipleFoldersRequest(
                workspace_name="Combo 3 Pastas Locais",
                folders=[
                    str(self.folder_const),
                    str(self.folder_adm),
                    str(self.folder_extra),
                ],
                subject_hint="Revisão Multidisciplinar Cebraspe",
                area_hint="Policial / Tribunais",
                questions_per_file=4,
                create_unified_battery=True,
            )
        )

        # Foram escaneadas 3 pastas; existem 4 arquivos físicos, mas 1 deles é cópia idêntica (SHA-256 igual)
        self.assertEqual(scan_res["folders_scanned_count"], 3)
        self.assertEqual(scan_res["total_unique_files"], 3)
        self.assertEqual(scan_res["duplicates_skipped_count"], 1)

        # Deve ter gerado a Bateria Unificada Multi-Pasta combinando as 3 fontes únicas (3 * 4 = 12 questões)
        self.assertIsNotNone(scan_res["unified_battery_id"])
        self.assertIsNotNone(scan_res["unified_battery"])
        self.assertGreaterEqual(len(scan_res["unified_battery"]["assertions"]), 10)
        self.assertEqual(len(scan_res["individual_batteries"]), 3)


if __name__ == "__main__":
    unittest.main()

