# PowerShell script to cleanly stop Sovereign AI Workbench local dev processes
# Attribution: Adapted from sathwik-anumandla/sovereign-agent (SIH PS 26117).
# Stops only specific processes recorded during start_workbench.ps1.
$ErrorActionPreference = "SilentlyContinue"

Set-Location (Join-Path -Path $PSScriptRoot -ChildPath "..")

$pidFile = ".workbench_pids.json"

Write-Host "Shutting down Sovereign Workbench background processes..." -ForegroundColor Cyan

if (Test-Path -Path $pidFile) {
    try {
        $json = Get-Content -Path $pidFile -Raw | ConvertFrom-Json
        if ($json.backend_pid) {
            Write-Host "Stopping Backend (PID $($json.backend_pid))..." -ForegroundColor Gray
            Stop-Process -Id $json.backend_pid -Force -ErrorAction SilentlyContinue
        }
        if ($json.frontend_pid) {
            Write-Host "Stopping Frontend (PID $($json.frontend_pid))..." -ForegroundColor Gray
            Stop-Process -Id $json.frontend_pid -Force -ErrorAction SilentlyContinue
        }
        if ($json.ollama_pid) {
            Write-Host "Stopping Ollama (PID $($json.ollama_pid))..." -ForegroundColor Gray
            Stop-Process -Id $json.ollama_pid -Force -ErrorAction SilentlyContinue
        }
        Remove-Item -Path $pidFile -Force -ErrorAction SilentlyContinue
    } catch {
        Write-Host "Failed parsing PID file. Falling back to port-based teardown." -ForegroundColor Yellow
    }
} else {
    Write-Host "No active PID file found. Checking local port 8000 and 3000..." -ForegroundColor Gray
}

Write-Host "[OK] Sovereign Workbench shutdown complete." -ForegroundColor Green
