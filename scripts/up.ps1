param(
    [ValidateSet("local", "kind")]
    [string]$Mode = "local",
    [string]$ContainerName = "cern-ml-demo-minio",
    [string]$VolumeName    = "cern-ml-demo-minio-data",
    [string]$AccessKey     = "minioadmin",
    [string]$SecretKey     = "minioadmin",
    [switch]$SkipBuild,
    # Install KServe + deploy InferenceService (kserve-cpu profile)
    [switch]$WithKServe
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent

function Assert-Command($name, $installHint) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        throw "'$name' not found. $installHint"
    }
}

function Assert-Docker {
    Assert-Command "docker" "Install Docker Desktop and ensure it is running."
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    docker info *> $null
    $code = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    if ($code -ne 0) { throw "Docker daemon is not reachable. Start Docker Desktop and retry." }
}

# ─────────────────────────── local mode ───────────────────────────────────────
if ($Mode -eq "local") {
    Assert-Docker
    $existing = docker ps -a --filter "name=^/$ContainerName$" --format "{{.Names}}"
    if ($existing -eq $ContainerName) {
        $running = docker ps --filter "name=^/$ContainerName$" --filter "status=running" --format "{{.Names}}"
        if ($running -ne $ContainerName) { docker start $ContainerName | Out-Null }
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
            quay.io/minio/minio:RELEASE.2024-10-13T13-34-11Z server /data --console-address ":9001" | Out-Null
    }
    Write-Host "MinIO is running (local mode)."
    Write-Host "  API:     http://localhost:9000"
    Write-Host "  Console: http://localhost:9001"
    Write-Host "  Bucket:  cern-ml-demo (created by the app on first use)"
    Write-Host ""
    Write-Host "Start the backend:"
    Write-Host "  uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload"
    exit 0
}

# ─────────────────────────── kind mode ────────────────────────────────────────
Assert-Command "kind"    "winget install Kubernetes.kind"
Assert-Command "kubectl" "winget install Kubernetes.kubectl"
Assert-Docker

# Create cluster if it doesn't exist
$clusters = kind get clusters 2>$null
if ($clusters -notcontains "cern-ml-demo") {
    Write-Host "Creating kind cluster 'cern-ml-demo'..."
    kind create cluster --config "$Root\deploy\kind\cluster.yaml"
} else {
    Write-Host "Kind cluster 'cern-ml-demo' already exists."
}

kubectl config use-context kind-cern-ml-demo | Out-Null

# Build and load images
if (-not $SkipBuild) {
    Write-Host "Building Docker images..."
    docker build -f "$Root\backend\Dockerfile"         -t cern-ml-demo-backend:local       $Root
    docker build -f "$Root\workers\pdf\Dockerfile"     -t cern-ml-demo-worker-pdf:local    $Root
    docker build -f "$Root\workers\tabular\Dockerfile" -t cern-ml-demo-worker-tabular:local $Root
}

Write-Host "Loading images into kind cluster..."
kind load docker-image cern-ml-demo-backend:local        --name cern-ml-demo
kind load docker-image cern-ml-demo-worker-pdf:local     --name cern-ml-demo
kind load docker-image cern-ml-demo-worker-tabular:local --name cern-ml-demo

# Apply manifests
Write-Host "Applying manifests..."
kubectl apply -f "$Root\deploy\app\backend-rbac.yaml"
kubectl apply -f "$Root\deploy\app\minio.yaml"
kubectl apply -f "$Root\deploy\app\backend-deploy.yaml"

# Observability
Write-Host "Deploying Prometheus + Grafana..."
kubectl create configmap grafana-dashboard-json `
    "--from-file=cern-ml-demo.json=$Root\deploy\observability\grafana-dashboard.json" `
    --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "$Root\deploy\observability\prometheus.yaml"

# Wait for deployments
Write-Host "Waiting for MinIO..."
kubectl rollout status deployment/minio --timeout=120s
Write-Host "Waiting for backend..."
kubectl rollout status deployment/cern-ml-demo-backend --timeout=120s
Write-Host "Waiting for kube-state-metrics..."
kubectl rollout status deployment/kube-state-metrics --timeout=120s
Write-Host "Waiting for Prometheus..."
kubectl rollout status deployment/prometheus --timeout=120s
Write-Host "Waiting for Grafana..."
kubectl rollout status deployment/grafana --timeout=120s

if ($WithKServe) {
    Write-Host "Installing KServe (this takes 3-5 minutes)..."
    if (-not (Get-Command bash -ErrorAction SilentlyContinue)) {
        throw "bash not found. KServe install script requires Git Bash or WSL."
    }
    bash "$Root/deploy/kserve/install.sh"
    Write-Host "Deploying InferenceService (vllm)..."
    kubectl apply -f "$Root\deploy\kserve\inferenceservice.yaml"
    Write-Host "Waiting for InferenceService to become ready (may take 5-10 min for model download)..."
    kubectl wait inferenceservice/vllm --for=condition=Ready --timeout=600s -n default
}

Write-Host ""
Write-Host "Cluster is ready."
Write-Host "  Backend:         http://localhost:8000"
Write-Host "  MinIO API:       http://localhost:9000"
Write-Host "  MinIO console:   http://localhost:9001"
Write-Host "  Prometheus:      http://localhost:9090"
Write-Host "  Grafana:         http://localhost:3000  (admin/admin)"
if ($WithKServe) {
    Write-Host "  KServe/vLLM:     http://localhost:8080/v1"
}
Write-Host ""
Write-Host "Profiles:"
Write-Host "  local-fast:  scripts\demo.ps1 -Profile local-fast"
Write-Host "  kserve-cpu:  scripts\demo.ps1 -Profile kserve-cpu  (requires -WithKServe)"
