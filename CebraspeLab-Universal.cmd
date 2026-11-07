: << 'POLYGLOT_WINDOWS_CMD'
@echo off
chcp 65001 >nul 2>&1
title CebraspeLab — Executavel Universal (Windows / Linux / macOS)
cd /d "%~dp0"

echo ============================================================================
echo   CEBRASPELAB — EXECUTAVEL UNIVERSAL (Windows / Linux / macOS)
echo ============================================================================

if exist "dist\CebraspeLab-Universal.pyz" (
    where uv >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo [Windows] Iniciando pacote unico dist\CebraspeLab-Universal.pyz via uv...
        uv run --directory backend python "..\dist\CebraspeLab-Universal.pyz" %*
        exit /b %ERRORLEVEL%
    )
    where python >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo [Windows] Iniciando pacote unico dist\CebraspeLab-Universal.pyz via Python...
        python "dist\CebraspeLab-Universal.pyz" %*
        exit /b %ERRORLEVEL%
    )
)

if exist "dist\CebraspeLab.exe" (
    echo [Windows] Iniciando executavel nativo dist\CebraspeLab.exe...
    start "" "dist\CebraspeLab.exe"
    exit /b 0
)

echo [Erro] Nao foi encontrado Python, uv ou dist\CebraspeLab.exe.
pause
exit /b 1
POLYGLOT_WINDOWS_CMD

# ============================================================================
# Bloco POSIX (Linux & macOS — x86_64 / ARM64 / Apple Silicon)
# ============================================================================
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================================"
echo "  CEBRASPELAB — EXECUTÁVEL UNIVERSAL (Linux / macOS / Windows)"
echo "  SO Detectado: $(uname -s) | Arquitetura: $(uname -m)"
echo "============================================================================"

if [ ! -f "dist/CebraspeLab-Universal.pyz" ]; then
    echo "-> Gerando pacote único dist/CebraspeLab-Universal.pyz..."
    python3 empacotar_universal.py
fi

if command -v uv >/dev/null 2>&1 && [ -d "backend" ]; then
    echo "-> Iniciando dist/CebraspeLab-Universal.pyz via uv..."
    exec uv run --directory backend python "../dist/CebraspeLab-Universal.pyz" "$@"
elif command -v python3 >/dev/null 2>&1; then
    echo "-> Iniciando dist/CebraspeLab-Universal.pyz via python3..."
    exec python3 "dist/CebraspeLab-Universal.pyz" "$@"
else
    echo "[Erro] Python 3 não encontrado no sistema. Instale python3 para executar."
    exit 1
fi

