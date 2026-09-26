# Inicia o Bot Trader localmente no Windows.
#
#   .\start.ps1          -> instala o que faltar, compila o frontend e abre http://localhost:8000
#   .\start.ps1 -Dev     -> modo desenvolvimento: API com auto-reload + frontend em http://localhost:5173
#   .\start.ps1 -Test    -> roda os testes do backend
#
# Se o PowerShell bloquear o script:  powershell -ExecutionPolicy Bypass -File .\start.ps1

param([switch]$Dev, [switch]$Test)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$py = Join-Path $backend ".venv\Scripts\python.exe"

# ---- Python ----
if (-not (Test-Path $py)) {
    Write-Host "Criando ambiente Python (backend\.venv)..." -ForegroundColor Cyan
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv (Join-Path $backend ".venv")
        if (-not $?) { & py -3 -m venv (Join-Path $backend ".venv") }
    } else {
        & python -m venv (Join-Path $backend ".venv")
    }
    & $py -m pip install --upgrade pip
    & $py -m pip install -r (Join-Path $backend "requirements-dev.txt")
}

if ($Test) {
    Push-Location $backend
    & $py -m pytest -q
    Pop-Location
    exit $LASTEXITCODE
}

# ---- Node ----
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "Node.js não encontrado. Instale a versão 22 ou mais nova em https://nodejs.org"
}
if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Write-Host "Instalando dependências do frontend..." -ForegroundColor Cyan
    Push-Location $frontend
    npm install
    Pop-Location
}

if ($Dev) {
    Write-Host "API em http://127.0.0.1:8000 (auto-reload) | Frontend em http://localhost:5173" -ForegroundColor Green
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$backend'; & '$py' -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
    Push-Location $frontend
    npm run dev
    Pop-Location
    exit
}

Write-Host "Compilando o frontend..." -ForegroundColor Cyan
Push-Location $frontend
npm run build
Pop-Location

Write-Host ""
Write-Host "Bot Trader rodando em http://localhost:8000  (Ctrl+C para parar)" -ForegroundColor Green
Write-Host ""
Start-Process "http://localhost:8000"
Push-Location $backend
& $py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Pop-Location
