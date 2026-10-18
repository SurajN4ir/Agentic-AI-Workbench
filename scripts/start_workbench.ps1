# PowerShell startup script for Sovereign AI Workbench on Windows
# Attribution: Adapted from sathwik-anumandla/sovereign-agent (SIH PS 26117).
# Hardened to record exact process IDs for isolated teardown and poll health checks.
$ErrorActionPreference = "Continue"

Set-Location (Join-Path -Path $PSScriptRoot -ChildPath "..")

if (-not (Test-Path -Path "logs")) {
    New-Item -ItemType Directory -Path "logs" | Out-Null
}

$pidFile = ".workbench_pids.json"
$pidsData = @{}

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
    $ollamaProc = Start-Process -FilePath "ollama" -ArgumentList "serve" -RedirectStandardOutput "logs\ollama.log" -RedirectStandardError "logs\ollama_err.log" -WindowStyle Hidden -PassThru
    $pidsData["ollama_pid"] = $ollamaProc.Id
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

# 3. FastAPI Backend with Health Polling
Write-Host -NoNewline "[3/4] Checking FastAPI backend server (http://127.0.0.1:8000)... "
try {
    $backendCheck = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -ErrorAction Stop
    Write-Host "[OK] Already Running" -ForegroundColor Green
} catch {
    Write-Host "[LAUNCHING] Starting Uvicorn backend on 127.0.0.1:8000..." -ForegroundColor Cyan
    $backendProc = Start-Process -FilePath ".venv\Scripts\python.exe" -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" -RedirectStandardOutput "logs\backend.log" -RedirectStandardError "logs\backend_err.log" -WindowStyle Hidden -PassThru
    $pidsData["backend_pid"] = $backendProc.Id

    # Health polling loop
    $healthy = $false
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 1
        try {
            $h = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -ErrorAction Stop
            if ($h.StatusCode -eq 200) {
                $healthy = $true
                break
            }
        } catch { }
    }
    if ($healthy) {
        Write-Host "     [OK] Backend healthy and responding." -ForegroundColor Green
    } else {
        Write-Host "     [WARNING] Backend startup taking longer than expected. Check logs\backend.log." -ForegroundColor Yellow
    }
}

# 4. React Frontend
Write-Host -NoNewline "[4/4] Checking React Frontend dev server (http://localhost:3000)... "
try {
    $frontendCheck = Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -ErrorAction Stop
    Write-Host "[OK] Already Running" -ForegroundColor Green
} catch {
    Write-Host "[LAUNCHING] Starting React frontend dev server on port 3000..." -ForegroundColor Cyan
    $frontendProc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c cd frontend && npm run dev > ..\logs\frontend.log 2>&1" -WindowStyle Hidden -PassThru
    $pidsData["frontend_pid"] = $frontendProc.Id
    Start-Sleep -Seconds 2
}

# Save active PIDs for isolated teardown
$pidsData | ConvertTo-Json | Set-Content -Path $pidFile -Encoding UTF8

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  [SUCCESS] SOVEREIGN AGENT AI WORKBENCH IS UP AND READY!" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  • Web Dashboard      : http://localhost:3000" -ForegroundColor White
Write-Host "  • Backend API & Docs : http://127.0.0.1:8000/docs" -ForegroundColor White
Write-Host "  • Health Probes      : http://127.0.0.1:8000/health" -ForegroundColor White
Write-Host "  • Local Inference    : http://127.0.0.1:11434" -ForegroundColor White
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "To shut down the workbench cleanly, run: .\scripts\stop_workbench.ps1" -ForegroundColor Gray
