param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

Write-Host "Starting CERN ML Demo on http://localhost:$Port"
Write-Host "Using uv-managed FastAPI app. Stop with Ctrl+C."
Write-Host "Run .\scripts\up.ps1 first to enable MinIO-backed uploads."

uv run uvicorn backend.app.main:app --host 0.0.0.0 --port $Port --reload
