param(
    [ValidateSet("local", "kind")]
    [string]$Mode = "local",
    [string]$ContainerName = "k8s-llm-job-minio",
    [string]$VolumeName    = "k8s-llm-job-minio-data",
    [switch]$RemoveData
)

$ErrorActionPreference = "Stop"

function Stop-KServePortForward {
    $portForwards = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match "^kubectl(.exe)?$" -and
            $_.CommandLine -like "*port-forward*service/vllm-predictor*8080:80*"
        }
    foreach ($proc in $portForwards) {
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped KServe port-forward process $($proc.ProcessId)."
    }
}

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
if ($clusters -contains "k8s-llm-job") {
    Stop-KServePortForward
    Write-Host "Deleting kind cluster 'k8s-llm-job'..."
    kind delete cluster --name k8s-llm-job
    Write-Host "Cluster deleted."
} else {
    Write-Host "Kind cluster 'k8s-llm-job' does not exist."
}
