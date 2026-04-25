param(
    [string]$Url = "http://localhost:8000/healthz",
    [int]$Requests = 10
)

$ErrorActionPreference = "Stop"

for ($i = 1; $i -le $Requests; $i++) {
    Invoke-RestMethod -Uri $Url | Out-Null
}

Write-Host "Completed $Requests requests against $Url"
