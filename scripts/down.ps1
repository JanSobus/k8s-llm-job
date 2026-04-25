param(
    [string]$ContainerName = "cern-ml-demo-minio",
    [string]$VolumeName = "cern-ml-demo-minio-data",
    [switch]$RemoveData
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is required to manage local MinIO."
}

$previousPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
docker info *> $null
$dockerInfoExitCode = $LASTEXITCODE
$ErrorActionPreference = $previousPreference
if ($dockerInfoExitCode -ne 0) {
    throw "Docker is installed but the daemon is not reachable. Start Docker Desktop and retry."
}

$existing = docker ps -a --filter "name=^/$ContainerName$" --format "{{.Names}}"
if ($existing -eq $ContainerName) {
    docker rm --force $ContainerName | Out-Null
    Write-Host "Removed MinIO container $ContainerName."
} else {
    Write-Host "MinIO container $ContainerName does not exist."
}

if ($RemoveData) {
    docker volume rm $VolumeName | Out-Null
    Write-Host "Removed MinIO volume $VolumeName."
} else {
    Write-Host "Preserved MinIO volume $VolumeName. Pass -RemoveData to delete it."
}
