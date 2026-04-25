param(
    [ValidateSet("local", "kind")]
    [string]$Mode = "local",
    [string]$ContainerName = "cern-ml-demo-minio",
    [string]$VolumeName    = "cern-ml-demo-minio-data",
    [switch]$RemoveData
)

$ErrorActionPreference = "Stop"

function Assert-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker is required."
    }
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    docker info *> $null
    $code = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    if ($code -ne 0) { throw "Docker daemon is not reachable. Start Docker Desktop and retry." }
}

if ($Mode -eq "local") {
    Assert-Docker
    $existing = docker ps -a --filter "name=^/$ContainerName$" --format "{{.Names}}"
    if ($existing -eq $ContainerName) {
        docker rm --force $ContainerName | Out-Null
        Write-Host "Removed MinIO container $ContainerName."
    } else {
        Write-Host "MinIO container $ContainerName does not exist."
    }
    if ($RemoveData) {
        docker volume rm $VolumeName --force 2>$null | Out-Null
        Write-Host "Removed MinIO volume $VolumeName."
    } else {
        Write-Host "Preserved MinIO volume $VolumeName. Pass -RemoveData to delete it."
    }
    exit 0
}

# kind mode
if (-not (Get-Command kind -ErrorAction SilentlyContinue)) {
    throw "'kind' not found. winget install Kubernetes.kind"
}
$clusters = kind get clusters 2>$null
if ($clusters -contains "cern-ml-demo") {
    Write-Host "Deleting kind cluster 'cern-ml-demo'..."
    kind delete cluster --name cern-ml-demo
    Write-Host "Cluster deleted."
} else {
    Write-Host "Kind cluster 'cern-ml-demo' does not exist."
}
