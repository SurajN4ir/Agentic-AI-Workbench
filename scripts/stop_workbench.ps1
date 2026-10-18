# PowerShell script to cleanly stop Sovereign AI Workbench local dev processes
$ErrorActionPreference = "SilentlyContinue"

Write-Host "Shutting down Sovereign Workbench background processes..." -ForegroundColor Cyan

# Stop Uvicorn/FastAPI backend
Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*uvicorn app.main:app*" } | Stop-Process -Force
# Stop Vite / Node dev server
Get-Process node -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*vite*" } | Stop-Process -Force

Write-Host "[OK] Sovereign Workbench stopped cleanly." -ForegroundColor Green
