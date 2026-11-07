@echo off
chcp 65001 >nul
title CebraspeLab - Plataforma de Estudo por Questoes (Certo/Errado)
echo ============================================================================
echo   CEBRASPELAB - INICIALIZADOR FACIL (2 CLIQUES PARA USUARIOS NAO-TECNICOS)
echo ============================================================================
echo.
echo   Iniciando o sistema local e abrindo o seu navegador automaticamente...
echo   Voce podera escolher 1 ou varias pastas com seus PDFs e arquivos na tela!
echo.

cd /d "%~dp0"

if not exist "frontend\dist\index.html" (
    echo [1/2] Preparando interface visual pela primeira vez...
    call npm run build --prefix frontend
)

echo [2/2] Abrindo o CebraspeLab em http://127.0.0.1:8000 ...
uv run --directory backend python launcher.py %*

pause

