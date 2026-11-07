@echo off
chcp 65001 >nul
title Gerador de Executavel (.EXE) - CebraspeLab
echo ============================================================================
echo   GERANDO EXECUTAVEL STANDALONE (CebraspeLab.exe) PARA WINDOWS
echo ============================================================================

cd /d "%~dp0"

echo [1/3] Compilando a interface visual (React Frontend)...
call npm run build --prefix frontend

echo [2/3] Garantindo PyInstaller no ambiente Python...
uv run --directory backend pip install pyinstaller

echo [3/3] Empacotando CebraspeLab.exe...
uv run --directory backend pyinstaller --noconfirm --onefile --name "CebraspeLab" --add-data "../frontend/dist;frontend/dist" launcher.py

echo.
echo ============================================================================
echo   CONCLUIDO! O executavel foi gerado em: backend\dist\CebraspeLab.exe
echo ============================================================================
pause

