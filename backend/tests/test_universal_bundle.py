import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import empacotar_universal


class TestUniversalBundle(unittest.TestCase):
    def test_build_universal_pyz_contains_backend_and_frontend_and_runs_self_test(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_pyz = Path(tmpdir) / "CebraspeLab-Universal.pyz"
            built_path = empacotar_universal.build_universal_pyz(out_pyz)
            self.assertTrue(built_path.exists())
            self.assertGreater(built_path.stat().st_size, 50_000)

            # Verificar se tem o shebang #!/usr/bin/env python3 no cabeçalho
            with open(built_path, "rb") as f:
                first_line = f.readline()
            self.assertTrue(first_line.startswith(b"#!/usr/bin/env python3"))

            # Verificar se todos os módulos backend e o frontend compilado estão embutidos no .pyz
            self.assertTrue(zipfile.is_zipfile(built_path))
            with zipfile.ZipFile(built_path, "r") as zf:
                names = set(zf.namelist())
                self.assertIn("__main__.py", names)
                self.assertIn("main.py", names)
                self.assertIn("database.py", names)
                self.assertIn("spaced_review.py", names)
                self.assertIn("multi_folder_workspace.py", names)
                self.assertIn("data_connectors.py", names)
                self.assertIn("frontend_dist/index.html", names)

            # Executar o arquivo .pyz com --self-test e verificar a extração automática
            proc = subprocess.run(
                [sys.executable, str(built_path), "--self-test"],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("SELF_TEST_OK", proc.stdout)
            extracted_index = Path(tmpdir) / ".cebraspelab_runtime" / "frontend_dist" / "index.html"
            self.assertTrue(extracted_index.exists())

    def test_polyglot_launcher_script_exists_and_has_valid_headers(self):
        polyglot_path = ROOT_DIR / "CebraspeLab-Universal.cmd"
        self.assertTrue(polyglot_path.exists())
        content = polyglot_path.read_text(encoding="utf-8")
        self.assertTrue(content.startswith(": << 'POLYGLOT_WINDOWS_CMD'"))
        self.assertIn("@echo off", content)
        self.assertIn("POLYGLOT_WINDOWS_CMD", content)
        self.assertIn("uname -s", content)


if __name__ == "__main__":
    unittest.main()

