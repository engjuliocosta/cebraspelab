import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import database
import local_bridge
import storage_manager


class TestLocalBridgeAndGitHubPages(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp_dir.name)
        self.orig_db_path = database.DB_PATH
        self.orig_vault = storage_manager.VAULT_DIR
        self.orig_nosql = storage_manager.NOSQL_PATH

        database.DB_PATH = tmp_path / "test_bridge.db"
        storage_manager.VAULT_DIR = tmp_path / "pdf_vault"
        storage_manager.NOSQL_PATH = tmp_path / "nosql_bridge.json"

        database.init_db()
        storage_manager.init_storage_tables()

    def tearDown(self) -> None:
        database.DB_PATH = self.orig_db_path
        storage_manager.VAULT_DIR = self.orig_vault
        storage_manager.NOSQL_PATH = self.orig_nosql
        self.tmp_dir.cleanup()

    def test_pna_cors_headers_for_top_level_github_pages_origin(self) -> None:
        headers = local_bridge.compute_pna_cors_headers(
            origin="https://app.cebraspelab.com.br",
            request_pna="true",
        )
        self.assertEqual(headers["Access-Control-Allow-Origin"], "https://app.cebraspelab.com.br")
        self.assertEqual(headers["Access-Control-Allow-Private-Network"], "true")
        self.assertEqual(headers["Access-Control-Allow-Credentials"], "true")

    def test_bridge_status_dual_mode_github_pages_and_local_direct(self) -> None:
        # 1. Quando acessado via URL de alto nível do GitHub Pages
        status_remote = local_bridge.build_bridge_status(
            request_origin="https://app.cebraspelab.com.br"
        )
        self.assertTrue(status_remote["bridge_online"])
        self.assertEqual(status_remote["ui_mode"], "github_pages_connected_to_local_pc")
        self.assertIn("test_bridge.db", status_remote["local_storage"]["sql_db_path"])

        # 2. Quando acessado diretamente via servidor local
        status_local = local_bridge.build_bridge_status(
            request_origin="http://127.0.0.1:8000"
        )
        self.assertEqual(status_local["ui_mode"], "local_direct_ui")

    def test_ingest_browser_selected_files_batch_deduplicates_and_stores_locally(self) -> None:
        sample_txt = (
            "1. Atos Administrativos\n"
            "1.1. Extinção do Ato\n"
            "A anulação ocorre por vício de legalidade e produz efeitos ex tunc, podendo ser decretada pela Administração ou pelo Judiciário. "
            "A revogação ocorre por conveniência e oportunidade com efeitos ex nunc, sendo privativa da Administração Pública."
        ).encode("utf-8")

        res = local_bridge.ingest_browser_selected_files_batch(
            files_payload=[
                {"filename": "resumo_atos_1.txt", "content_bytes": sample_txt},
                {"filename": "copia_duplicada_atos.txt", "content_bytes": sample_txt},
            ],
            folder_label="Meus_Estudos_Pages",
            subject_hint="Direito Administrativo",
            area_hint="Tribunais / Jurídico",
            questions_per_file=4,
        )
        self.assertEqual(res["processed_files_count"], 1)
        self.assertEqual(res["duplicates_skipped_count"], 1)
        self.assertGreater(res["battery_id"], 0)
        self.assertGreaterEqual(len(res["battery"]["assertions"]), 2)

    def test_activate_license_and_build_hotmart_customer_package(self) -> None:
        lic = local_bridge.activate_product_license(
            license_key="HP987654321",
            buyer_email="aluno@concurso.com.br",
            custom_pages_url="https://app.cebraspelab.com.br",
        )
        self.assertTrue(lic["is_activated"])
        self.assertEqual(lic["buyer_email"], "aluno@concurso.com.br")
        self.assertEqual(lic["top_level_pages_url"], "https://app.cebraspelab.com.br")

        with tempfile.TemporaryDirectory() as pkg_dir:
            zip_path = Path(pkg_dir) / "Pacote_Hotmart_CebraspeLab.zip"
            built = local_bridge.build_hotmart_customer_package(
                output_zip_path=zip_path,
                top_level_pages_url="https://app.cebraspelab.com.br",
            )
            self.assertTrue(built.exists())
            self.assertTrue(zipfile.is_zipfile(built))
            with zipfile.ZipFile(built, "r") as zf:
                names = set(zf.namelist())
                self.assertIn("Abrir_Interface_Web_CebraspeLab.html", names)
                self.assertIn("LEIA_ME_ACESSO_ALUNO.txt", names)
                self.assertIn("CebraspeLab-Universal.cmd", names)

    def test_gitflow_and_top_level_pages_config_files_exist(self) -> None:
        vite_cfg = (ROOT_DIR / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
        self.assertIn("base:", vite_cfg)

        spa_404 = ROOT_DIR / "frontend" / "public" / "404.html"
        self.assertTrue(spa_404.exists())

        nojekyll = ROOT_DIR / "frontend" / "public" / ".nojekyll"
        self.assertTrue(nojekyll.exists())

        workflow = ROOT_DIR / ".github" / "workflows" / "deploy-github-pages-gitflow.yml"
        self.assertTrue(workflow.exists())
        wf_text = workflow.read_text(encoding="utf-8")
        self.assertIn("release/**", wf_text)
        self.assertIn("hotfix/**", wf_text)
        self.assertIn("develop", wf_text)
        self.assertIn("actions/deploy-pages@v4", wf_text)


if __name__ == "__main__":
    unittest.main()

