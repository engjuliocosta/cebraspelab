"""
Inicializador de 1 Clique para Usuários Não-Técnicos (`launcher.py`).

Inicia o servidor integrado do CebraspeLab (que serve tanto a interface gráfica React
compilada em `frontend/dist` quanto a API FastAPI + Banco Híbrido SQL/NoSQL na porta 8000),
permite pré-carregar 1 ou mais pastas passadas por parâmetro (`--folder`) e abre
automaticamente o navegador padrão do computador em `http://127.0.0.1:8000`.
"""

import argparse
import threading
import time
import webbrowser
from pathlib import Path
from typing import List

import uvicorn

import main
import multi_folder_workspace


def open_browser_delayed(url: str, delay_seconds: float = 1.5) -> None:
    def _target() -> None:
        time.sleep(delay_seconds)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()


def run_launcher(
    host: str = "127.0.0.1",
    port: int = 8000,
    initial_folders: List[str] | None = None,
    open_browser: bool = True,
) -> None:
    if initial_folders:
        valid_folders = [f for f in initial_folders if Path(f).exists() and Path(f).is_dir()]
        if valid_folders:
            print(f"[CebraspeLab] Sincronizando {len(valid_folders)} pasta(s) inicial(is)...")
            try:
                multi_folder_workspace.scan_and_sync_multiple_folders(
                    workspace_name="Pastas Carregadas na Inicialização",
                    folders=valid_folders,
                    questions_per_file=6,
                    create_unified_battery=True,
                )
            except Exception as exc:
                print(f"[Aviso] Não foi possível sincronizar pastas iniciais: {exc}")

    url = f"http://{host}:{port}"
    print("=" * 68)
    print("  CEBRASPELAB - PLATAFORMA LOCAL DE ESTUDO POR QUESTOES (C/E)")
    print(f"  Acesse no navegador: {url}")
    print("  Para encerrar o programa, basta fechar esta janela ou pressionar Ctrl+C.")
    print("=" * 68)

    if open_browser:
        open_browser_delayed(url)

    uvicorn.run(main.app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Inicializador local do CebraspeLab para usuários não-técnicos."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host local (padrão: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Porta local (padrão: 8000)")
    parser.add_argument(
        "--folder",
        action="append",
        dest="folders",
        help="Caminho de uma pasta com arquivos de estudo (pode repetir --folder para várias pastas)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Não abrir o navegador automaticamente",
    )
    args = parser.parse_args()
    run_launcher(
        host=args.host,
        port=args.port,
        initial_folders=args.folders,
        open_browser=not args.no_browser,
    )

