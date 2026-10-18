# PowerShell startup script for Sovereign AI Workbench on Windows
$ErrorActionPreference = "Continue"

Set-Location (Join-Path -Path $PSScriptRoot -ChildPath "..")

if (-not (Test-Path -Path "logs")) {
    New-Item -ItemType Directory -Path "logs" | Out-Null
}

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "      [START] STARTING SOVEREIGN AI WORKBENCH (WINDOWS POWERSHELL)" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

# 1. Ollama Server Check
Write-Host -NoNewline "[1/4] Checking Ollama server (http://127.0.0.1:11434)... "
try {
    $ollamaCheck = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -ErrorAction Stop
    Write-Host "[OK] Running" -ForegroundColor Green
} catch {
    Write-Host "[WARNING] Not running. Launching 'ollama serve' in background..." -ForegroundColor Yellow
    Start-Process -FilePath "ollama" -ArgumentList "serve" -RedirectStandardOutput "logs\ollama.log" -RedirectStandardError "logs\ollama_err.log" -WindowStyle Hidden
    Start-Sleep -Seconds 3
}

# 2. Check Models
Write-Host "[2/4] Verifying available Ollama models..."
try {
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags"
    $modelList = ($tags.models | ForEach-Object { $_.name }) -join ", "
    Write-Host "     Models installed: $modelList" -ForegroundColor Gray
} catch {
    Write-Host "     Unable to fetch model tags." -ForegroundColor Yellow
}

# 3. FastAPI Backend
Write-Host -NoNewline "[3/4] Checking FastAPI backend server (http://localhost:8000)... "
try {
    $backendCheck = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -ErrorAction Stop
    Write-Host "[OK] Already Running" -ForegroundColor Green
} catch {
    Write-Host "[LAUNCHING] Starting Uvicorn backend on port 8000..." -ForegroundColor Cyan
    Start-Process -FilePath ".venv\Scripts\python.exe" -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" -RedirectStandardOutput "logs\backend.log" -RedirectStandardError "logs\backend_err.log" -WindowStyle Hidden
    Start-Sleep -Seconds 3
}

# 4. React Frontend
Write-Host -NoNewline "[4/4] Checking React Frontend dev server (http://localhost:3000)... "
try {
    $frontendCheck = Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -ErrorAction Stop
    Write-Host "[OK] Already Running" -ForegroundColor Green
} catch {
    Write-Host "[LAUNCHING] Starting React frontend dev server on port 3000..." -ForegroundColor Cyan
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c cd frontend && npm run dev > ..\logs\frontend.log 2>&1" -WindowStyle Hidden
    Start-Sleep -Seconds 2
}

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  [SUCCESS] SOVEREIGN AGENT AI WORKBENCH IS UP AND READY!" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  • Web Dashboard      : http://localhost:3000" -ForegroundColor White
Write-Host "  • Backend API & Docs : http://localhost:8000/docs" -ForegroundColor White
Write-Host "  • Health Probes      : http://localhost:8000/health" -ForegroundColor White
Write-Host "  • Local Inference    : http://127.0.0.1:11434" -ForegroundColor White
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "To shut down the workbench cleanly, run: .\scripts\stop_workbench.ps1" -ForegroundColor Gray
