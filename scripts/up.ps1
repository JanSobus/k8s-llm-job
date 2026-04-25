param(
    [string]$ContainerName = "cern-ml-demo-minio",
    [string]$VolumeName = "cern-ml-demo-minio-data",
    [string]$AccessKey = "minioadmin",
    [string]$SecretKey = "minioadmin"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is required to run local MinIO. Install/start Docker Desktop and retry."
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
    $running = docker ps --filter "name=^/$ContainerName$" --filter "status=running" --format "{{.Names}}"
    if ($running -ne $ContainerName) {
        docker start $ContainerName | Out-Null
    }
} else {
    docker volume create $VolumeName | Out-Null
    docker run `
        --detach `
        --name $ContainerName `
        --publish 9000:9000 `
        --publish 9001:9001 `
        --env "MINIO_ROOT_USER=$AccessKey" `
        --env "MINIO_ROOT_PASSWORD=$SecretKey" `
        --volume "${VolumeName}:/data" `
        quay.io/minio/minio:latest server /data --console-address ":9001" | Out-Null
}

Write-Host "MinIO is running."
Write-Host "API:     http://localhost:9000"
Write-Host "Console: http://localhost:9001"
Write-Host "Bucket:  cern-ml-demo (created by the app on first use)"
Write-Host "User:    $AccessKey"
Write-Host "Pass:    $SecretKey"
