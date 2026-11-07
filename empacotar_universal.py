"""
Empacotador Universal Multi-OS e Multi-Arquitetura (`empacotar_universal.py`).

Agrupa todo o projeto CebraspeLab (Backend FastAPI + Banco Híbrido SQL/NoSQL + Frontend React compilado)
em um ÚNICO arquivo executável universal (`dist/CebraspeLab-Universal.pyz`) compatível com:
  - Windows (x86_64 / ARM64)
  - Linux (x86_64 / aarch64 / ARM64)
  - macOS (Intel x86_64 / Apple Silicon M1, M2, M3, M4 ARM64)

Como funciona a portabilidade em arquivo único entre SOs e Arquiteturas:
  - Binários nativos puros (PE `.exe` no Windows, `ELF` no Linux, `Mach-O` no macOS) são atrelados
    ao kernel e à CPU de um único sistema operacional.
  - Já o pacote executável universal `.pyz` (PEP 441 Python ZipApp com cabeçalho `#!/usr/bin/env python3`)
    embute 100% do código do Backend + 100% dos assets estáticos do Frontend (`frontend/dist`) em um
    único arquivo compacto (~120 KB) independente de arquitetura de CPU e de Sistema Operacional.
  - Ao ser executado em qualquer máquina (Windows, Linux ou Mac), o `__main__.py` embutido:
      1. Extrai os arquivos estáticos do Frontend React (`frontend/dist`) para uma pasta de cache local;
      2. Verifica se as bibliotecas (`fastapi`, `uvicorn`, `pypdf`, `reportlab`, `genanki`) estão presentes
         no ambiente; caso não estejam, utiliza `uv` ou cria automaticamente um ambiente virtual local
         (`.cebraspelab_env`) instalando as dependências na primeira execução;
      3. Inicia o servidor local em `http://127.0.0.1:8000` e abre o navegador padrão automaticamente.
"""

import os
import shutil
import stat
import tempfile
import zipapp
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIST_DIR = ROOT_DIR / "frontend" / "dist"
DIST_DIR = ROOT_DIR / "dist"

UNIVERSAL_ENTRYPOINT_CODE = '''# -*- coding: utf-8 -*-
"""
Entrypoint Universal do CebraspeLab (Windows / Linux / macOS — x86_64 & ARM64).
Executado automaticamente ao rodar `CebraspeLab-Universal.pyz`.
"""
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
import zipfile
from pathlib import Path

REQUIRED_PACKAGES = [
    "fastapi>=0.115.0",
    "uvicorn>=0.30.0",
    "python-multipart>=0.0.9",
    "pypdf>=4.3.0",
    "genanki>=0.13.0",
    "reportlab>=4.2.0",
    "pydantic>=2.8.0",
]


def _ensure_dependencies_and_reexec_if_needed(archive_path: Path, runtime_home: Path) -> None:
    """
    Verifica se FastAPI e Uvicorn estão disponíveis no interpretador Python atual.
    Caso o usuário esteja executando o arquivo `.pyz` com o Python padrão do sistema
    sem dependências instaladas, cria/usa automaticamente um venv em `runtime_home / "venv"`
    (ou usa `uv` se instalado) e re-executa este mesmo `.pyz` dentro dele.
    """
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
        import pypdf  # noqa: F401
        return
    except ImportError:
        pass

    if os.environ.get("CEBRASPELAB_BOOTSTRAPPED") == "1":
        raise RuntimeError(
            "Não foi possível carregar as dependências do CebraspeLab mesmo após o bootstrap."
        )

    print("==================================================================")
    print("  CebraspeLab Universal — Preparando Ambiente (1ª Execução)...")
    print("==================================================================")

    venv_dir = runtime_home / "venv"
    if sys.platform == "win32":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"

    if not venv_python.exists():
        print("-> Criando ambiente isolado em:", venv_dir)
        subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])

    # Verifica se já tem fastapi no venv_python
    check = subprocess.run(
        [str(venv_python), "-c", "import fastapi, uvicorn, pypdf, genanki, reportlab"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if check.returncode != 0:
        print("-> Instalando bibliotecas necessárias (FastAPI, Uvicorn, PyPDF, ReportLab, Genanki)...")
        subprocess.check_call(
            [str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "--quiet"]
        )
        subprocess.check_call(
            [str(venv_python), "-m", "pip", "install", *REQUIRED_PACKAGES]
        )

    env = os.environ.copy()
    env["CEBRASPELAB_BOOTSTRAPPED"] = "1"
    cmd = [str(venv_python), str(archive_path), *sys.argv[1:]]
    raise SystemExit(subprocess.call(cmd, env=env))


def _extract_embedded_Assets(archive_path: Path, runtime_home: Path) -> Path:
    """
    Extrai os arquivos estáticos do frontend (`frontend_dist/`) de dentro do `.pyz`
    para `runtime_home / "frontend_dist"` para que o FastAPI possa servi-los com alta performance.
    """
    target_frontend = runtime_home / "frontend_dist"
    if archive_path.is_file() and zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path, "r") as zf:
            for member in zf.namelist():
                if member.startswith("frontend_dist/") and not member.endswith("/"):
                    rel_path = member[len("frontend_dist/"):]
                    dest_file = target_frontend / rel_path
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(dest_file, "wb") as dst:
                        shutil.copyfileobj(src, dst)
    return target_frontend


def main() -> None:
    archive_path = Path(__file__).resolve().parent
    # Diretório onde o banco SQL+NoSQL e o cache estático ficam salvos ao lado do executável
    base_dir = archive_path.parent if archive_path.is_file() else Path.cwd()
    runtime_home = base_dir / ".cebraspelab_runtime"
    runtime_home.mkdir(parents=True, exist_ok=True)

    data_dir = base_dir / "cebraspelab_dados"
    data_dir.mkdir(parents=True, exist_ok=True)

    if "--self-test" in sys.argv:
        frontend_dir = _extract_embedded_Assets(archive_path, runtime_home)
        print("SELF_TEST_OK", str(frontend_dir), str(data_dir))
        return

    _ensure_dependencies_and_reexec_if_needed(archive_path, runtime_home)
    frontend_dir = _extract_embedded_Assets(archive_path, runtime_home)

    os.environ["CEBRASPELAB_FRONTEND_DIST"] = str(frontend_dir)
    os.environ["CEBRASPELAB_DATA_DIR"] = str(data_dir)

    if str(archive_path) not in sys.path:
        sys.path.insert(0, str(archive_path))

    import uvicorn
    import main as backend_main

    host = os.environ.get("CEBRASPELAB_HOST", "127.0.0.1")
    port = int(os.environ.get("CEBRASPELAB_PORT", "8000"))
    url = f"http://{host}:{port}"

    print("==================================================================")
    print("  CebraspeLab — Executável Universal (Windows / Linux / macOS)")
    print(f"  Acesse no navegador: {url}")
    print(f"  Banco de Dados SQL+NoSQL salvo em: {data_dir}")
    print("  (Para encerrar, pressione Ctrl+C nesta janela)")
    print("==================================================================")

    if os.environ.get("CEBRASPELAB_NO_BROWSER") != "1":
        def _open_browser() -> None:
            time.sleep(1.5)
            try:
                webbrowser.open(url)
            except Exception:
                pass

        threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(backend_main.app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
'''


def build_universal_pyz(output_path: Path = None) -> Path:
    """
    Constrói o arquivo único universal `dist/CebraspeLab-Universal.pyz` contendo:
      - Todos os módulos Python do backend (`backend/*.py`)
      - Todos os arquivos estáticos compilados do frontend (`frontend/dist/**/*` em `frontend_dist/`)
      - Entrypoint `__main__.py` com auto-bootstrap multi-OS (Windows, Linux, macOS)
    """
    if output_path is None:
        DIST_DIR.mkdir(parents=True, exist_ok=True)
        output_path = DIST_DIR / "CebraspeLab-Universal.pyz"
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        stage_dir = Path(tmpdir) / "bundle"
        stage_dir.mkdir(parents=True, exist_ok=True)

        # 1. Copiar módulos Python do backend
        for py_file in BACKEND_DIR.glob("*.py"):
            if py_file.name == "launcher_desktop.py":
                continue
            shutil.copy2(py_file, stage_dir / py_file.name)

        # 2. Copiar o build estático do frontend (frontend/dist -> bundle/frontend_dist)
        if FRONTEND_DIST_DIR.exists():
            shutil.copytree(FRONTEND_DIST_DIR, stage_dir / "frontend_dist")

        # 3. Escrever __main__.py universal
        (stage_dir / "__main__.py").write_text(UNIVERSAL_ENTRYPOINT_CODE, encoding="utf-8")

        # 4. Empacotar como Python ZipApp executável com shebang POSIX (Linux/macOS/Windows py launcher)
        zipapp.create_archive(
            source=stage_dir,
            target=output_path,
            interpreter="/usr/bin/env python3",
            compressed=True,
        )

    # Tornar executável no Linux/macOS (chmod +x)
    try:
        current_mode = output_path.stat().st_mode
        output_path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        pass

    return output_path


if __name__ == "__main__":
    out = build_universal_pyz()
    size_kb = round(out.stat().st_size / 1024, 1)
    print(f"[OK] Executável Universal Multi-OS gerado em: {out} ({size_kb} KB)")

