param(
    [ValidateSet("local", "kind")]
    [string]$Mode = "local",
    [string]$ContainerName = "k8s-llm-job-minio",
    [string]$VolumeName    = "k8s-llm-job-minio-data",
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

function Get-DockerPortOwners([int]$Port) {
    $owners = @()
    $rows = docker ps --format "{{.Names}}|{{.Ports}}" 2>$null
    foreach ($row in $rows) {
        $parts = $row -split "\|", 2
        if ($parts.Count -eq 2 -and $parts[1] -match "(:|\])$Port->") {
            $owners += $parts[0]
        }
    }
    return $owners
}

function Test-AllowedProcess($ProcessInfo, [string[]]$AllowedProcessCommandLike) {
    if (-not $ProcessInfo) { return $false }
    foreach ($pattern in $AllowedProcessCommandLike) {
        if ($ProcessInfo.CommandLine -like $pattern) { return $true }
    }
    return $false
}

function Assert-PortAvailable {
    param(
        [int]$Port,
        [string[]]$AllowedDockerContainers = @(),
        [string[]]$AllowedProcessCommandLike = @()
    )

    $dockerOwners = @(Get-DockerPortOwners $Port)
    $blockedDocker = @($dockerOwners | Where-Object { $AllowedDockerContainers -notcontains $_ })
    if ($blockedDocker.Count -gt 0) {
        throw "Port $Port is already published by Docker container(s): $($blockedDocker -join ', '). Stop them and retry."
    }
    if ($dockerOwners.Count -gt 0) {
        return
    }

    if (-not (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue)) {
        return
    }

    $connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    $blocked = @()
    foreach ($connection in $connections) {
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($connection.OwningProcess)" -ErrorAction SilentlyContinue
        if (-not (Test-AllowedProcess $processInfo $AllowedProcessCommandLike)) {
            $name = if ($processInfo) { $processInfo.Name } else { "pid $($connection.OwningProcess)" }
            $blocked += "$name ($($connection.OwningProcess))"
        }
    }
    if ($blocked.Count -gt 0) {
        throw "Port $Port is already in use by: $($blocked -join ', '). Stop the process and retry."
    }
}

function Assert-LocalImage([string]$ImageName) {
    docker image inspect $ImageName *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker image '$ImageName' not found. Run scripts\up.ps1 -Mode kind without -SkipBuild first."
    }
}

function Set-BackendProviderConfig([string]$Provider, [string]$FakeMode) {
    kubectl set env deployment/k8s-llm-job-backend -n default `
        "APP_LLM_PROVIDER=$Provider" `
        "APP_LLM_FAKE_MODE=$FakeMode" | Out-Null
    kubectl rollout status deployment/k8s-llm-job-backend --timeout=120s
}

function Start-KServePortForward {
    $existing = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match "^kubectl(.exe)?$" -and
            $_.CommandLine -like "*port-forward*service/vllm-predictor*8080:80*"
        }
    if ($existing) {
        try {
            $null = Invoke-WebRequest "http://localhost:8080/health" -UseBasicParsing -TimeoutSec 5
            Write-Host "KServe port-forward already running on localhost:8080."
            return
        } catch {
            foreach ($proc in $existing) {
                Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Start-Process kubectl -WindowStyle Hidden -ArgumentList @(
        "port-forward",
        "-n", "default",
        "service/vllm-predictor",
        "8080:80"
    ) | Out-Null
    Start-Sleep -Seconds 2

    try {
        $null = Invoke-WebRequest "http://localhost:8080/health" -UseBasicParsing -TimeoutSec 10
        Write-Host "Started KServe port-forward on http://localhost:8080."
    } catch {
        Write-Warning "KServe predictor port-forward did not become healthy on localhost:8080 yet."
    }
}

# ─────────────────────────── local mode ───────────────────────────────────────
if ($Mode -eq "local") {
    Assert-Docker
    $existing = docker ps -a --filter "name=^/$ContainerName$" --format "{{.Names}}"
    $running = docker ps --filter "name=^/$ContainerName$" --filter "status=running" --format "{{.Names}}"
    $allowedLocalContainers = @()
    if ($running -eq $ContainerName) { $allowedLocalContainers += $ContainerName }
    Assert-PortAvailable -Port 9000 -AllowedDockerContainers $allowedLocalContainers
    Assert-PortAvailable -Port 9001 -AllowedDockerContainers $allowedLocalContainers
    if ($existing -eq $ContainerName) {
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
    Write-Host "  Bucket:  k8s-llm-job (created by the app on first use)"
    Write-Host ""
    Write-Host "Start the backend:"
    Write-Host "  uv run --all-extras uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload"
    exit 0
}

# ─────────────────────────── kind mode ────────────────────────────────────────
Assert-Command "kind"    "winget install Kubernetes.kind"
Assert-Command "kubectl" "winget install Kubernetes.kubectl"
Assert-Docker

# Create cluster if it doesn't exist
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$clusters = kind get clusters 2>&1 | Where-Object { $_ -is [string] }
$ErrorActionPreference = $previousPreference
$allowedKindContainers = @()
if ($clusters -contains "k8s-llm-job") {
    $allowedKindContainers += "k8s-llm-job-control-plane"
}
foreach ($port in @(8000, 9000, 9001, 9090, 3000)) {
    Assert-PortAvailable -Port $port -AllowedDockerContainers $allowedKindContainers
}
if ($WithKServe) {
    Assert-PortAvailable `
        -Port 8080 `
        -AllowedProcessCommandLike @("*port-forward*service/vllm-predictor*8080:80*")
}
if ($clusters -notcontains "k8s-llm-job") {
    Write-Host "Creating kind cluster 'k8s-llm-job'..."
    kind create cluster --config "$Root\deploy\kind\cluster.yaml"
} else {
    Write-Host "Kind cluster 'k8s-llm-job' already exists."
}

kubectl config use-context kind-k8s-llm-job | Out-Null

# Build and load images
if (-not $SkipBuild) {
    Write-Host "Building Docker images..."
    docker build -f "$Root\backend\Dockerfile"         -t k8s-llm-job-backend:local       $Root
    docker build -f "$Root\workers\pdf\Dockerfile"     -t k8s-llm-job-worker-pdf:local    $Root
    docker build -f "$Root\workers\tabular\Dockerfile" -t k8s-llm-job-worker-tabular:local $Root
} else {
    Assert-LocalImage "k8s-llm-job-backend:local"
    Assert-LocalImage "k8s-llm-job-worker-pdf:local"
    Assert-LocalImage "k8s-llm-job-worker-tabular:local"
}

Write-Host "Loading images into kind cluster..."
kind load docker-image k8s-llm-job-backend:local        --name k8s-llm-job
kind load docker-image k8s-llm-job-worker-pdf:local     --name k8s-llm-job
kind load docker-image k8s-llm-job-worker-tabular:local --name k8s-llm-job

# Apply manifests
Write-Host "Applying manifests..."
kubectl apply -f "$Root\deploy\app\backend-rbac.yaml"
kubectl apply -f "$Root\deploy\app\minio.yaml"
kubectl apply -f "$Root\deploy\app\backend-deploy.yaml"

# Observability
Write-Host "Deploying Prometheus + Grafana..."
kubectl create configmap grafana-dashboard-json `
    "--from-file=k8s-llm-job.json=$Root\deploy\observability\grafana-dashboard.json" `
    --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "$Root\deploy\observability\prometheus.yaml"

# Wait for deployments
Write-Host "Waiting for MinIO..."
kubectl rollout status deployment/minio --timeout=120s
Write-Host "Waiting for backend..."
kubectl rollout status deployment/k8s-llm-job-backend --timeout=120s
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
    Write-Host "Switching backend provider to KServe..."
    Set-BackendProviderConfig -Provider "kserve" -FakeMode "false"
    Write-Host "Starting predictor port-forward..."
    Start-KServePortForward
}

Write-Host ""
Write-Host "Cluster is ready."
Write-Host "  Backend:         http://localhost:8000"
Write-Host "  MinIO API:       http://localhost:9000"
Write-Host "  MinIO console:   http://localhost:9001"
Write-Host "  Prometheus:      http://localhost:9090"
Write-Host "  Grafana:         http://localhost:3000  (admin/admin)"
if ($WithKServe) {
    Write-Host "  KServe/vLLM:     http://localhost:8080/v1  (kubectl port-forward)"
}
Write-Host ""
Write-Host "Profiles:"
Write-Host "  local-fast:  scripts\demo.ps1 -Profile local-fast"
Write-Host "  kserve-cpu:  scripts\demo.ps1 -Profile kserve-cpu  (requires -WithKServe)"
