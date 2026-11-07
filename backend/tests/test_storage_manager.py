import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import database
import storage_manager


class TestStorageManager(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp_dir.name)
        self.orig_db = database.DB_PATH
        self.orig_vault = storage_manager.VAULT_DIR
        self.orig_nosql = storage_manager.NOSQL_PATH

        database.DB_PATH = tmp_path / "test_storage.db"
        storage_manager.VAULT_DIR = tmp_path / "pdf_vault"
        storage_manager.NOSQL_PATH = tmp_path / "nosql_store.json"

        database.init_db()
        storage_manager.init_storage_tables()

    def tearDown(self) -> None:
        database.DB_PATH = self.orig_db
        storage_manager.VAULT_DIR = self.orig_vault
        storage_manager.NOSQL_PATH = self.orig_nosql
        self.tmp_dir.cleanup()

    def test_sql_and_vault_pdf_binary_persistence(self) -> None:
        fake_pdf = b"%PDF-1.7 Conteudo binario do PDF de estudo do usuario para persistir"
        saved = storage_manager.store_uploaded_file(
            file_bytes=fake_pdf,
            filename="aula_direito_penal.pdf",
            material_id=1,
            file_role="study_pdf",
            mime_type="application/pdf",
        )
        self.assertGreater(saved["file_id"], 0)
        self.assertEqual(saved["file_size"], len(fake_pdf))

        listed = storage_manager.list_stored_files(material_id=1)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["filename"], "aula_direito_penal.pdf")

        loaded = storage_manager.get_stored_file_With_bytes(saved["file_id"])
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded["bytes"], fake_pdf)

    def test_nosql_document_store_crud_and_knowledge_tree(self) -> None:
        store = storage_manager.NoSQLDocumentStore(storage_manager.NOSQL_PATH)
        doc = store.upsert_document(
            "pdf_knowledge_trees",
            "10",
            {"title": " Direito Constitucional", "total_periods": 18},
        )
        self.assertEqual(doc["_id"], "10")
        self.assertEqual(doc["total_periods"], 18)

        found = store.find_by_id("pdf_knowledge_trees", "10")
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found["title"], " Direito Constitucional")

        tree_doc = storage_manager.save_material_knowledge_tree_nosql(
            material_id=25,
            title="Aula Atos",
            subject="Direito Administrativo",
            area="Geral",
            parsed_topics=[{"topic": "T1", "subtopic": "S1", "periods": [{"text": "P1"}], "periods_count": 1}],
            recurrence_map=[{"subtopic": "S1", "recurrence_level": "Alta"}],
            stored_file_ids=[1],
            nosql_store=store,
        )
        self.assertEqual(tree_doc["total_subtopics"], 1)
        self.assertEqual(tree_doc["total_periods"], 1)

        loaded_tree = storage_manager.get_material_knowledge_tree_nosql(25, nosql_store=store)
        self.assertIsNotNone(loaded_tree)
        assert loaded_tree is not None
        self.assertEqual(loaded_tree["subject"], "Direito Administrativo")

        deleted = store.delete_by_id("pdf_knowledge_trees", "10")
        self.assertTrue(deleted)
        self.assertIsNone(store.find_by_id("pdf_knowledge_trees", "10"))


if __name__ == "__main__":
    unittest.main()

