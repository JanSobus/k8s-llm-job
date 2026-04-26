param(
    [ValidateSet("local-fast", "kserve-cpu")]
    [string]$Profile = "local-fast",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent

Write-Host "K8s LLM Job — profile: $Profile"
Write-Host ""

if ($Profile -eq "local-fast") {
    Write-Host "Checking MinIO..."
    $running = docker ps --filter "name=^/k8s-llm-job-minio$" --filter "status=running" --format "{{.Names}}" 2>$null
    if ($running -ne "k8s-llm-job-minio") {
        Write-Host "MinIO not running. Starting via up.ps1..."
        & "$PSScriptRoot\up.ps1" -Mode local
    }
    Write-Host ""
    Write-Host "Starting backend on http://localhost:$Port"
    Write-Host "Provider comes from .env (set APP_LLM_PROVIDER to switch)."
    Write-Host ".env.example starts with APP_LLM_FAKE_MODE=true; set it to false for real provider responses."
    Write-Host "Stop with Ctrl+C."
    Write-Host ""
    Set-Location $Root
    uv run --all-extras uvicorn backend.app.main:app --host 0.0.0.0 --port $Port --reload
}

if ($Profile -eq "kserve-cpu") {
    Write-Host "kserve-cpu profile: opens the kind-backed demo URLs."
    Write-Host "Run 'scripts\up.ps1 -Mode kind -WithKServe' first to install KServe and wire the backend to vLLM."
    Write-Host ""
    Write-Host "  Backend:  http://localhost:8000"
    Write-Host "  vLLM:     http://localhost:8080/v1"
    Write-Host "  MinIO:    http://localhost:9001"
    Write-Host "  Grafana:  http://localhost:3000  (after observability is deployed)"
    Write-Host ""
    Write-Host "To open in browser:"
    Start-Process "http://localhost:$Port"
}
