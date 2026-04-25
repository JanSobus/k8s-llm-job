param(
    [ValidateSet("local-fast", "kserve-cpu")]
    [string]$Profile = "local-fast",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent

Write-Host "CERN ML Demo — profile: $Profile"
Write-Host ""

if ($Profile -eq "local-fast") {
    Write-Host "Checking MinIO..."
    $running = docker ps --filter "name=^/cern-ml-demo-minio$" --filter "status=running" --format "{{.Names}}" 2>$null
    if ($running -ne "cern-ml-demo-minio") {
        Write-Host "MinIO not running. Starting via up.ps1..."
        & "$PSScriptRoot\up.ps1" -Mode local
    }
    Write-Host ""
    Write-Host "Starting backend on http://localhost:$Port"
    Write-Host "Provider: OpenAI (set APP_LLM_PROVIDER in .env to switch)"
    Write-Host "Stop with Ctrl+C."
    Write-Host ""
    Set-Location $Root
    uv run uvicorn backend.app.main:app --host 0.0.0.0 --port $Port --reload
}

if ($Profile -eq "kserve-cpu") {
    Write-Host "kserve-cpu profile: ensures kind cluster is running, then opens browser."
    Write-Host "Run 'scripts\up.ps1 -Mode kind' first if the cluster is not yet up."
    Write-Host ""
    Write-Host "  Backend:  http://localhost:8000"
    Write-Host "  MinIO:    http://localhost:9001"
    Write-Host "  Grafana:  http://localhost:3000  (after observability is deployed)"
    Write-Host ""
    Write-Host "To open in browser:"
    Start-Process "http://localhost:$Port"
}
