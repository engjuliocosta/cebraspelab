"""
Empacotador Comercial para Venda na Hotmart / Kiwify / Eduzz (`empacotar_hotmart.py`).

Gera:
  1. `dist/CebraspeLab-Universal.pyz` (Executável Único Universal Windows / Linux / macOS)
  2. `dist/Pacote_Hotmart_CebraspeLab.zip` (Arquivo `.zip` pronto para cadastrar na área de membros
     da Hotmart, permitindo ao comprador usar TANTO a interface de alto nível do GitHub Pages conectada
     ao banco local do PC dele QUANTO o executável 100% local offline).
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import empacotar_universal
from local_bridge import DEFAULT_TOP_LEVEL_PAGES_URL, build_hotmart_customer_package


def main() -> None:
    pyz_path = empacotar_universal.build_universal_pyz()
    zip_out = ROOT_DIR / "dist" / "Pacote_Hotmart_CebraspeLab.zip"
    built_zip = build_hotmart_customer_package(
        output_zip_path=zip_out,
        top_level_pages_url=DEFAULT_TOP_LEVEL_PAGES_URL,
        universal_pyz_path=pyz_path,
        polyglot_cmd_path=ROOT_DIR / "CebraspeLab-Universal.cmd",
    )
    size_kb = round(built_zip.stat().st_size / 1024, 1)
    print(f"[OK] Pacote Comercial Hotmart gerado em: {built_zip} ({size_kb} KB)")


if __name__ == "__main__":
    main()

