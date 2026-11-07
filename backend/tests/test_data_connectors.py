import json
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pymupdf as fitz

sys.path.insert(0, str(Path(__file__).parent.parent))

import data_connectors
import database
import spaced_review
import storage_manager


class TestDataConnectorsInfrastructure(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.tmp_dir.name)

        self.orig_db = database.DB_PATH
        self.orig_vault = storage_manager.VAULT_DIR
        self.orig_nosql = storage_manager.NOSQL_PATH

        database.DB_PATH = self.base_path / "test_connectors.db"
        storage_manager.VAULT_DIR = self.base_path / "pdf_vault"
        storage_manager.NOSQL_PATH = self.base_path / "nosql_connectors.json"

        database.init_db()
        storage_manager.init_storage_tables()
        spaced_review.init_spaced_review_tables()
        data_connectors.init_connectors_tables()
        self.nosql_store = storage_manager.NoSQLDocumentStore(storage_manager.NOSQL_PATH)

        # Criar pasta simulada de Downloads / Nuvem com múltiplos formatos (PDF, JSON, CSV, XML)
        self.study_folder = self.base_path / "Downloads_Estudo"
        self.study_folder.mkdir(parents=True, exist_ok=True)

        # 1. Criar arquivo PDF real
        doc = fitz.open()
        page = doc.new_page()
        page.insert_textbox(
            fitz.Rect(40, 40, 550, 750),
            "1. Controle da Administração Pública\n"
            "1.1 Controle Judicial e Mérito Administrativo\n"
            "O controle judicial dos atos administrativos abrange exclusivamente o exame de legalidade e legitimidade, "
            "sendo vedado ao Poder Judiciário invadir o mérito administrativo (conveniência e oportunidade).\n"
            "A Administração Pública pode anular seus próprios atos quando eivados de vícios que os tornem ilegais, "
            "ou revogá-los por motivo de conveniência ou oportunidade, respeitados os direitos adquiridos.",
            fontsize=11,
        )
        pdf_bytes = doc.tobytes()
        doc.close()
        (self.study_folder / "controle_administracao.pdf").write_bytes(pdf_bytes)

        # 2. Criar arquivo JSON de estudo e questões
        json_payload = [
            {
                "subtopic": "Responsabilidade Civil do Estado",
                "statement": "As pessoas jurídicas de direito público e as de direito privado prestadoras de serviços públicos responderão pelos danos que seus agentes, nessa qualidade, causarem a terceiros, assegurado o direito de regresso nos casos de dolo ou culpa.",
                "answer": "C",
                "exam_info": "CEBRASPE - 2024 - PF",
            },
            {
                "subtopic": "Teoria do Risco Administrativo",
                "statement": "A responsabilidade objetiva do Estado adota como regra a teoria do risco integral, não admitindo excludentes como culpa exclusiva da vítima.",
                "answer": "E",
                "exam_info": "CEBRASPE - 2024 - TRF",
            },
        ]
        (self.study_folder / "questoes_responsabilidade.json").write_text(
            json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # 3. Criar arquivo CSV de estudo
        csv_content = (
            "topico;enunciado;gabarito\n"
            "Licitações (Lei 14.133/2021);O diálogo competitivo é modalidade de licitação restrita a contratações de inovação tecnológica ou técnica em que a Administração não pode definir especificações com precisão.;C\n"
            "Dispensa e Inexigibilidade;É inexigível a licitação quando houver inviabilidade de competição, em especial para aquisição de materiais com fornecedor exclusivo, admitida a preferência por marca específica.;E\n"
        )
        (self.study_folder / "licitacoes_resumo.csv").write_text(csv_content, encoding="utf-8")

        # 4. Criar arquivo XML de estudo
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<caderno disciplina="Direito Constitucional">
    <questao topico="Direitos e Garantias Fundamentais" gabarito="C">
        <enunciado>A casa é asilo inviolável do indivíduo, ninguém nela podendo penetrar sem consentimento do morador, salvo em caso de flagrante delito ou desastre, ou para prestar socorro, ou, durante o dia, por determinação judicial.</enunciado>
    </questao>
    <questao topico="Remédios Constitucionais" gabarito="E">
        <enunciado>Conceder-se-á habeas data para assegurar o conhecimento de informações relativas à pessoa de terceiros constantes de registros de entidades governamentais, independentemente de sigilo imprescindível à segurança do Estado.</enunciado>
    </questao>
</caderno>
"""
        (self.study_folder / "direitos_fundamentais.xml").write_text(xml_content, encoding="utf-8")

    def tearDown(self) -> None:
        database.DB_PATH = self.orig_db
        storage_manager.VAULT_DIR = self.orig_vault
        storage_manager.NOSQL_PATH = self.orig_nosql
        self.tmp_dir.cleanup()

    def test_register_local_network_and_cloud_connections_with_keys(self) -> None:
        # 1. Cadastrar conexão File System Local (Downloads)
        local_conn = data_connectors.create_or_update_connection(
            name="Meus Downloads de Concursos",
            provider_type="local_fs",
            target_path_or_folder_id=str(self.study_folder),
            subject_hint="Direito Administrativo",
            area_hint="Policial / Tribunais",
            nosql_store=self.nosql_store,
        )
        self.assertGreater(local_conn["id"], 0)
        self.assertEqual(local_conn["provider_type"], "local_fs")

        # 2. Cadastrar conexão Google Drive com chave de API e Token OAuth do usuário
        gdrive_conn = data_connectors.create_or_update_connection(
            name="Google Drive - Pasta Cebraspe 2025",
            provider_type="google_drive",
            target_path_or_folder_id="1AbCdEfGhIjKlMnOpQrStUvWxYz",
            subject_hint="Direito Constitucional",
            api_key="AIzaSyGoogleDriveUserKey987654",
            access_token="ya29.a0AfH6SMB_GoogleDriveToken_123456",
            local_sync_mirror_path=str(self.study_folder),
            nosql_store=self.nosql_store,
        )
        self.assertTrue(gdrive_conn["has_api_key"])
        self.assertTrue(gdrive_conn["has_access_token"])
        self.assertIn("...", gdrive_conn["api_key_masked"])

        # 3. Cadastrar conexão Dropbox com Access Token e App Key do usuário
        dropbox_conn = data_connectors.create_or_update_connection(
            name="Dropbox - PDFs e XMLs de Estudo",
            provider_type="dropbox",
            target_path_or_folder_id="/Estudos/Cebraspe",
            access_token="sl.BlahDropboxTokenSecret99887766",
            app_key="dpbx_app_key_12345",
            local_sync_mirror_path=str(self.study_folder),
            nosql_store=self.nosql_store,
        )
        self.assertEqual(dropbox_conn["provider_type"], "dropbox")
        self.assertTrue(dropbox_conn["has_access_token"])

        all_conns = data_connectors.list_connections()
        self.assertEqual(len(all_conns), 3)

        # Remover uma conexão
        deleted = data_connectors.delete_connection(dropbox_conn["id"], nosql_store=self.nosql_store)
        self.assertTrue(deleted)
        self.assertEqual(len(data_connectors.list_connections()), 2)

    def test_scan_sync_multi_format_files_relate_concepts_and_present_questions(self) -> None:
        # Cadastrar conexão apontando para a pasta com PDF, JSON, CSV e XML
        conn_rec = data_connectors.create_or_update_connection(
            name="Pasta de Estudos Multi-Formato",
            provider_type="local_fs",
            target_path_or_folder_id=str(self.study_folder),
            subject_hint="Direito Público Cebraspe",
            area_hint="Tribunais",
            auto_generate_questions=True,
            nosql_store=self.nosql_store,
        )

        # Escanear, rastrear, relacionar e gerar questões automaticamente
        sync_res = data_connectors.sync_connection_and_build_questions(
            connection_id=conn_rec["id"],
            auto_ingest_and_generate=True,
            questions_per_file=6,
            nosql_store=self.nosql_store,
        )

        self.assertEqual(sync_res["total_discovered_files"], 4)
        self.assertEqual(sync_res["newly_ingested_files_count"], 4)
        self.assertEqual(len(sync_res["generated_batteries"]), 4)

        # Verificar que todos os 4 formatos (.pdf, .json, .csv, .xml) geraram baterias e relacionamentos
        exts_found = {f["file_ext"] for f in sync_res["discovered_files"]}
        self.assertEqual(exts_found, {".pdf", ".json", ".csv", ".xml"})

        for tracked in sync_res["discovered_files"]:
            self.assertEqual(tracked["status"], "questions_generated")
            self.assertIsNotNone(tracked["material_id"])
            self.assertIsNotNone(tracked["battery_id"])
            self.assertGreaterEqual(tracked["extracted_questions_count"], 4)
            self.assertGreaterEqual(len(tracked["related_topics"]), 1)

        # Verificar que a árvore de relacionamentos conceituais foi populada no banco
        hierarchy = spaced_review.get_available_concepts_and_hierarchy()
        self.assertGreaterEqual(len(hierarchy["concept_relationships"]), 4)

    def test_resync_is_idempotent_and_detects_changed_files_by_sha256(self) -> None:
        conn_rec = data_connectors.create_or_update_connection(
            name="Pasta Resync",
            provider_type="network_share",
            target_path_or_folder_id=str(self.study_folder),
            subject_hint="Direito Público",
            nosql_store=self.nosql_store,
        )
        first = data_connectors.sync_connection_and_build_questions(
            connection_id=conn_rec["id"], questions_per_file=4, nosql_store=self.nosql_store
        )
        self.assertEqual(first["newly_ingested_files_count"], 4)

        # 2ª sincronização sem alterações: nada é reprocessado e nenhum arquivo é duplicado
        second = data_connectors.sync_connection_and_build_questions(
            connection_id=conn_rec["id"], questions_per_file=4, nosql_store=self.nosql_store
        )
        self.assertEqual(second["newly_ingested_files_count"], 0)
        self.assertEqual(second["total_discovered_files"], 4)

        # Alterar o conteúdo de 1 arquivo -> hash SHA-256 muda -> apenas ele é reprocessado
        csv_path = self.study_folder / "licitacoes_resumo.csv"
        csv_path.write_text(
            csv_path.read_text(encoding="utf-8")
            + "Contratação Direta;A contratação direta por dispensa exige processo administrativo instruído com justificativa de preço.;C\n",
            encoding="utf-8",
        )
        third = data_connectors.sync_connection_and_build_questions(
            connection_id=conn_rec["id"], questions_per_file=4, nosql_store=self.nosql_store
        )
        self.assertEqual(third["newly_ingested_files_count"], 1)
        self.assertEqual(third["total_discovered_files"], 4)

    def test_scan_skips_unsupported_ignored_dirs_empty_and_oversized_files(self) -> None:
        (self.study_folder / "foto_aula.png").write_bytes(b"\x89PNG fake image")
        (self.study_folder / "vazio.txt").write_bytes(b"")
        deps_dir = self.study_folder / "node_modules" / "pacote"
        deps_dir.mkdir(parents=True)
        (deps_dir / "readme.md").write_text("# Arquivo de dependência", encoding="utf-8")

        original_limit = data_connectors.MAX_STUDY_FILE_SIZE_BYTES
        try:
            found = data_connectors._scan_filesystem_directory(str(self.study_folder))
            names = {f["file_name"] for f in found}
            self.assertEqual(
                names,
                {
                    "controle_administracao.pdf",
                    "questoes_responsabilidade.json",
                    "licitacoes_resumo.csv",
                    "direitos_fundamentais.xml",
                },
            )
            for f in found:
                self.assertEqual(len(f["sha256_hash"]), 64)

            # Reduzir o limite de tamanho para 1 KB: o PDF (maior) deve ser ignorado
            data_connectors.MAX_STUDY_FILE_SIZE_BYTES = 1024
            small_only = data_connectors._scan_filesystem_directory(str(self.study_folder))
            self.assertNotIn("controle_administracao.pdf", {f["file_name"] for f in small_only})
        finally:
            data_connectors.MAX_STUDY_FILE_SIZE_BYTES = original_limit

        with self.assertRaises(ValueError):
            data_connectors._scan_filesystem_directory(str(self.base_path / "pasta_inexistente"))

    def test_parse_study_file_bytes_extracts_questions_from_each_format(self) -> None:
        for fname, expected_min_questions in (
            ("questoes_responsabilidade.json", 2),
            ("licitacoes_resumo.csv", 2),
            ("direitos_fundamentais.xml", 2),
        ):
            raw = (self.study_folder / fname).read_bytes()
            parsed = data_connectors.parse_study_file_bytes(raw, fname, subject_hint="Direito")
            self.assertGreaterEqual(len(parsed["extracted_questions"]), expected_min_questions, fname)
            self.assertGreaterEqual(len(parsed["pages"]), 1)
            self.assertGreaterEqual(len(parsed["parsed_topics"]), 1)
            answers = {q["answer"] for q in parsed["extracted_questions"]}
            self.assertEqual(answers, {"C", "E"}, fname)

        pdf_parsed = data_connectors.parse_study_file_bytes(
            (self.study_folder / "controle_administracao.pdf").read_bytes(),
            "controle_administracao.pdf",
        )
        self.assertIn("mérito administrativo", pdf_parsed["pages"][0]["text"])

    def test_cloud_connectors_without_credentials_raise_clear_errors(self) -> None:
        with self.assertRaises(ValueError) as ctx_drive:
            data_connectors._fetch_google_drive_files(
                {"target_path_or_folder_id": "FOLDER_ID_SEM_CHAVE", "api_key": "", "access_token": ""}
            )
        self.assertIn("Google Drive", str(ctx_drive.exception))

        with self.assertRaises(ValueError) as ctx_dbx:
            data_connectors._fetch_dropbox_files(
                {"target_path_or_folder_id": "/Estudos", "api_key": "", "access_token": ""}
            )
        self.assertIn("Dropbox", str(ctx_dbx.exception))

        with self.assertRaises(ValueError):
            data_connectors.create_or_update_connection(
                name="Provedor Inválido",
                provider_type="ftp_desconhecido",
                target_path_or_folder_id="/x",
                nosql_store=self.nosql_store,
            )

    def test_google_drive_api_connector_with_user_keys_mocked(self) -> None:
        json_bytes = (self.study_folder / "questoes_responsabilidade.json").read_bytes()
        captured_requests = []

        def fake_urlopen(req, timeout=0):
            captured_requests.append(req)
            url = req.full_url
            if "/drive/v3/files?" in url and "alt=media" not in url:
                body = json.dumps(
                    {
                        "files": [
                            {"id": "FILE_JSON_1", "name": "responsabilidade.json", "mimeType": "application/json"},
                            {"id": "FILE_IMG_2", "name": "capa.png", "mimeType": "image/png"},
                        ]
                    }
                ).encode("utf-8")
            elif "FILE_JSON_1" in url and "alt=media" in url:
                body = json_bytes
            else:
                raise AssertionError(f"URL inesperada: {url}")
            resp = MagicMock()
            resp.read.return_value = body
            resp.__enter__.return_value = resp
            resp.__exit__.return_value = False
            return resp

        conn_rec = data_connectors.create_or_update_connection(
            name="Google Drive API",
            provider_type="google_drive",
            target_path_or_folder_id="FOLDER_GDRIVE_123",
            subject_hint="Direito Administrativo",
            api_key="AIzaSyChaveDoUsuario123456",
            access_token="ya29.TokenOAuthDoUsuario",
            nosql_store=self.nosql_store,
        )

        with patch("data_connectors.urllib.request.urlopen", side_effect=fake_urlopen):
            res = data_connectors.sync_connection_and_build_questions(
                connection_id=conn_rec["id"], questions_per_file=4, nosql_store=self.nosql_store
            )

        # Apenas o .json é suportado (o .png é ignorado)
        self.assertEqual(res["total_discovered_files"], 1)
        self.assertEqual(res["newly_ingested_files_count"], 1)
        tracked = res["discovered_files"][0]
        self.assertEqual(tracked["file_path_or_remote_id"], "gdrive://FILE_JSON_1/responsabilidade.json")
        self.assertEqual(tracked["status"], "questions_generated")

        # As chaves cadastradas pelo usuário foram usadas na requisição à API
        listing_req = captured_requests[0]
        self.assertIn("key=AIzaSyChaveDoUsuario123456", listing_req.full_url)
        self.assertIn("FOLDER_GDRIVE_123", urllib.parse.unquote(listing_req.full_url))
        self.assertEqual(listing_req.get_header("Authorization"), "Bearer ya29.TokenOAuthDoUsuario")

    def test_dropbox_api_connector_with_access_token_mocked(self) -> None:
        xml_bytes = (self.study_folder / "direitos_fundamentais.xml").read_bytes()
        captured_requests = []

        def fake_urlopen(req, timeout=0):
            captured_requests.append(req)
            url = req.full_url
            if url.endswith("/2/files/list_folder"):
                payload = json.loads(req.data.decode("utf-8"))
                self.assertEqual(payload["path"], "/Estudos/Cebraspe")
                body = json.dumps(
                    {
                        "entries": [
                            {".tag": "folder", "name": "Antigos", "path_lower": "/estudos/cebraspe/antigos"},
                            {".tag": "file", "name": "garantias.xml", "path_lower": "/estudos/cebraspe/garantias.xml"},
                        ]
                    }
                ).encode("utf-8")
            elif url.endswith("/2/files/download"):
                arg = json.loads(req.get_header("Dropbox-api-arg"))
                self.assertEqual(arg["path"], "/estudos/cebraspe/garantias.xml")
                body = xml_bytes
            else:
                raise AssertionError(f"URL inesperada: {url}")
            resp = MagicMock()
            resp.read.return_value = body
            resp.__enter__.return_value = resp
            resp.__exit__.return_value = False
            return resp

        conn_rec = data_connectors.create_or_update_connection(
            name="Dropbox API",
            provider_type="dropbox",
            target_path_or_folder_id="/Estudos/Cebraspe",
            subject_hint="Direito Constitucional",
            access_token="sl.TokenDropboxDoUsuario999",
            nosql_store=self.nosql_store,
        )

        with patch("data_connectors.urllib.request.urlopen", side_effect=fake_urlopen):
            res = data_connectors.sync_connection_and_build_questions(
                connection_id=conn_rec["id"], questions_per_file=4, nosql_store=self.nosql_store
            )

        self.assertEqual(res["total_discovered_files"], 1)
        self.assertEqual(res["newly_ingested_files_count"], 1)
        self.assertEqual(
            res["discovered_files"][0]["file_path_or_remote_id"],
            "dropbox:///estudos/cebraspe/garantias.xml",
        )
        self.assertEqual(
            captured_requests[0].get_header("Authorization"), "Bearer sl.TokenDropboxDoUsuario999"
        )

    def test_update_connection_keeps_secrets_when_masked_value_is_sent(self) -> None:
        created = data_connectors.create_or_update_connection(
            name="Drive Original",
            provider_type="google_drive",
            target_path_or_folder_id="FOLDER_A",
            api_key="AIzaSyChaveOriginalSecreta",
            nosql_store=self.nosql_store,
        )
        # O frontend reenvia o valor mascarado ("AIza...reta"): a chave real deve ser preservada
        updated = data_connectors.create_or_update_connection(
            connection_id=created["id"],
            name="Drive Renomeado",
            provider_type="google_drive",
            target_path_or_folder_id="FOLDER_B",
            api_key=created["api_key_masked"],
            nosql_store=self.nosql_store,
        )
        self.assertEqual(updated["name"], "Drive Renomeado")
        self.assertEqual(updated["api_key_masked"], created["api_key_masked"])

        conn = database.get_connection()
        row = conn.execute(
            "SELECT api_key, target_path_or_folder_id FROM storage_connections WHERE id = ?",
            (created["id"],),
        ).fetchone()
        conn.close()
        self.assertEqual(row["api_key"], "AIzaSyChaveOriginalSecreta")
        self.assertEqual(row["target_path_or_folder_id"], "FOLDER_B")

        # O documento NoSQL guarda apenas a versão mascarada (nunca o segredo em texto puro)
        nosql_doc = self.nosql_store.find_by_id("storage_connections", str(created["id"]))
        self.assertNotIn("AIzaSyChaveOriginalSecreta", json.dumps(nosql_doc))


if __name__ == "__main__":
    unittest.main()
