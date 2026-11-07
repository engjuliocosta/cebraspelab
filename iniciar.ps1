# Script para iniciar Backend (FastAPI :8000) e Frontend (Vite :5173) do CebraspeLab
Write-Host "Iniciando CebraspeLab Backend (porta 8000) e Frontend (porta 5173)..." -ForegroundColor Cyan

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$PSScriptRoot\backend'; uv run uvicorn main:app --host 127.0.0.1 --port 8000 --reload"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$PSScriptRoot\frontend'; npm run dev"

Write-Host "Servidores iniciados! Acesse http://localhost:5173 no seu navegador." -ForegroundColor Green

