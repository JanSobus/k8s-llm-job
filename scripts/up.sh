#!/usr/bin/env bash
# Start local demo services or the kind-backed Kubernetes demo on Linux/WSL.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

MODE="local"
CONTAINER_NAME="k8s-llm-job-minio"
VOLUME_NAME="k8s-llm-job-minio-data"
ACCESS_KEY="minioadmin"
SECRET_KEY="minioadmin"
SKIP_BUILD="false"
WITH_KSERVE="false"
KSERVE_READY_TIMEOUT_SECONDS="${KSERVE_READY_TIMEOUT_SECONDS:-900}"
PORT_FORWARD_PID_FILE="${TMPDIR:-/tmp}/k8s-llm-job-vllm-port-forward.pid"
PORT_FORWARD_LOG_FILE="${TMPDIR:-/tmp}/k8s-llm-job-vllm-port-forward.log"

usage() {
  cat <<'EOF'
Usage: bash scripts/up.sh [options]

Options:
  --mode local|kind            Start local MinIO or the kind profile (default: local)
  --container-name NAME        Local MinIO container name (default: k8s-llm-job-minio)
  --volume-name NAME           Local MinIO Docker volume name (default: k8s-llm-job-minio-data)
  --access-key VALUE           Local MinIO access key (default: minioadmin)
  --secret-key VALUE           Local MinIO secret key (default: minioadmin)
  --skip-build                 Reuse existing local Docker images for kind
  --with-kserve                Install KServe and deploy the vLLM InferenceService
  -h, --help                   Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:-}"
      shift 2
      ;;
    --container-name)
      CONTAINER_NAME="${2:-}"
      shift 2
      ;;
    --volume-name)
      VOLUME_NAME="${2:-}"
      shift 2
      ;;
    --access-key)
      ACCESS_KEY="${2:-}"
      shift 2
      ;;
    --secret-key)
      SECRET_KEY="${2:-}"
      shift 2
      ;;
    --skip-build)
      SKIP_BUILD="true"
      shift
      ;;
    --with-kserve)
      WITH_KSERVE="true"
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "${MODE}" != "local" && "${MODE}" != "kind" ]]; then
  echo "--mode must be 'local' or 'kind'." >&2
  exit 2
fi

assert_command() {
  local name="$1"
  local install_hint="$2"
  if ! command -v "${name}" >/dev/null 2>&1; then
    echo "'${name}' not found. ${install_hint}" >&2
    exit 1
  fi
}

assert_docker() {
  assert_command docker "Install Docker and ensure it is available in this shell."
  if ! docker info >/dev/null 2>&1; then
    echo "Docker daemon is not reachable. Start Docker Desktop/WSL integration or native Docker and retry." >&2
    exit 1
  fi
}

docker_container_exists() {
  docker ps -a --filter "name=^/${1}$" --format '{{.Names}}' | grep -Fxq "$1"
}

docker_container_running() {
  docker ps --filter "name=^/${1}$" --filter "status=running" --format '{{.Names}}' | grep -Fxq "$1"
}

docker_port_owners() {
  local port="$1"
  docker ps --format '{{.Names}}|{{.Ports}}' 2>/dev/null |
    while IFS='|' read -r name ports; do
      if [[ "${ports}" == *":${port}->"* ]]; then
        printf '%s\n' "${name}"
      fi
    done
}

array_contains() {
  local needle="$1"
  shift
  local item
  for item in "$@"; do
    [[ "${item}" == "${needle}" ]] && return 0
  done
  return 1
}

host_port_listening() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "(:|\\])${port}$" && return 0
  elif command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1 && return 0
  fi
  return 1
}

assert_port_available() {
  local port="$1"
  shift
  local allowed=("$@")
  local owners=()
  mapfile -t owners < <(docker_port_owners "${port}")

  if [[ "${#owners[@]}" -gt 0 ]]; then
    local blocked=()
    local owner
    for owner in "${owners[@]}"; do
      if ! array_contains "${owner}" "${allowed[@]}"; then
        blocked+=("${owner}")
      fi
    done
    if [[ "${#blocked[@]}" -gt 0 ]]; then
      echo "Port ${port} is already published by Docker container(s): ${blocked[*]}. Stop them and retry." >&2
      exit 1
    fi
    return 0
  fi

  if host_port_listening "${port}"; then
    echo "Port ${port} appears to be in use in this Linux/WSL environment. Stop the listener and retry." >&2
    exit 1
  fi
}

assert_local_image() {
  local image_name="$1"
  if ! docker image inspect "${image_name}" >/dev/null 2>&1; then
    echo "Docker image '${image_name}' not found. Run 'bash scripts/up.sh --mode kind' without --skip-build first." >&2
    exit 1
  fi
}

kind_cluster_exists() {
  kind get clusters 2>/dev/null | grep -Fxq "k8s-llm-job"
}

kserve_port_forward_healthy() {
  command -v curl >/dev/null 2>&1 &&
    curl -fsS --max-time 5 "http://localhost:8080/health" >/dev/null 2>&1
}

stop_stale_kserve_port_forward() {
  if [[ ! -f "${PORT_FORWARD_PID_FILE}" ]]; then
    return 0
  fi

  local pid
  pid="$(<"${PORT_FORWARD_PID_FILE}")"
  if [[ -n "${pid}" && "${pid}" =~ ^[0-9]+$ ]] && kill -0 "${pid}" >/dev/null 2>&1; then
    if kserve_port_forward_healthy; then
      return 0
    fi
    kill "${pid}" >/dev/null 2>&1 || true
    sleep 1
  fi
  rm -f "${PORT_FORWARD_PID_FILE}"
}

set_backend_provider_config() {
  local provider="$1"
  local fake_mode="$2"
  kubectl set env deployment/k8s-llm-job-backend -n default \
    "APP_LLM_PROVIDER=${provider}" \
    "APP_LLM_FAKE_MODE=${fake_mode}" >/dev/null
  kubectl rollout status deployment/k8s-llm-job-backend --timeout=120s
}

start_kserve_port_forward() {
  stop_stale_kserve_port_forward
  if [[ -f "${PORT_FORWARD_PID_FILE}" ]] && kserve_port_forward_healthy; then
    echo "KServe port-forward already running on http://localhost:8080."
    return 0
  fi

  if host_port_listening 8080; then
    echo "Port 8080 is already in use. Stop that process or set up a different port-forward manually." >&2
    exit 1
  fi

  nohup kubectl port-forward -n default service/vllm-predictor 8080:80 \
    >"${PORT_FORWARD_LOG_FILE}" 2>&1 &
  local pid="$!"
  printf '%s\n' "${pid}" >"${PORT_FORWARD_PID_FILE}"

  for _ in $(seq 1 20); do
    if ! kill -0 "${pid}" >/dev/null 2>&1; then
      echo "KServe port-forward exited early. Log: ${PORT_FORWARD_LOG_FILE}" >&2
      rm -f "${PORT_FORWARD_PID_FILE}"
      exit 1
    fi
    if kserve_port_forward_healthy; then
      echo "Started KServe port-forward on http://localhost:8080."
      return 0
    fi
    sleep 1
  done

  echo "KServe predictor port-forward started, but /health is not ready yet. Log: ${PORT_FORWARD_LOG_FILE}" >&2
}

if [[ "${MODE}" == "local" ]]; then
  assert_docker
  allowed_local_containers=()
  if docker_container_running "${CONTAINER_NAME}"; then
    allowed_local_containers+=("${CONTAINER_NAME}")
  fi

  assert_port_available 9000 "${allowed_local_containers[@]}"
  assert_port_available 9001 "${allowed_local_containers[@]}"

  if docker_container_exists "${CONTAINER_NAME}"; then
    if ! docker_container_running "${CONTAINER_NAME}"; then
      docker start "${CONTAINER_NAME}" >/dev/null
    fi
  else
    docker volume create "${VOLUME_NAME}" >/dev/null
    docker run \
      --detach \
      --name "${CONTAINER_NAME}" \
      --publish 9000:9000 \
      --publish 9001:9001 \
      --env "MINIO_ROOT_USER=${ACCESS_KEY}" \
      --env "MINIO_ROOT_PASSWORD=${SECRET_KEY}" \
      --volume "${VOLUME_NAME}:/data" \
      quay.io/minio/minio:RELEASE.2024-10-13T13-34-11Z server /data --console-address ":9001" >/dev/null
  fi

  echo "MinIO is running (local mode)."
  echo "  API:     http://localhost:9000"
  echo "  Console: http://localhost:9001"
  echo "  Bucket:  k8s-llm-job (created by the app on first use)"
  echo
  echo "Start the backend:"
  echo "  uv run --all-extras uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload"
  exit 0
fi

assert_command kind "Install kind and ensure it is available in this shell."
assert_command kubectl "Install kubectl and ensure it is available in this shell."
assert_docker

allowed_kind_containers=()
if kind_cluster_exists; then
  allowed_kind_containers+=("k8s-llm-job-control-plane")
fi
for port in 8000 9000 9001 9090 3000; do
  assert_port_available "${port}" "${allowed_kind_containers[@]}"
done

if ! kind_cluster_exists; then
  echo "Creating kind cluster 'k8s-llm-job'..."
  kind create cluster --config "${ROOT}/deploy/kind/cluster.yaml"
else
  echo "Kind cluster 'k8s-llm-job' already exists."
fi

kubectl config use-context kind-k8s-llm-job >/dev/null

if [[ "${SKIP_BUILD}" == "true" ]]; then
  assert_local_image "k8s-llm-job-backend:local"
  assert_local_image "k8s-llm-job-worker-pdf:local"
  assert_local_image "k8s-llm-job-worker-tabular:local"
else
  echo "Building Docker images..."
  docker build -f "${ROOT}/backend/Dockerfile" -t k8s-llm-job-backend:local "${ROOT}"
  docker build -f "${ROOT}/workers/pdf/Dockerfile" -t k8s-llm-job-worker-pdf:local "${ROOT}"
  docker build -f "${ROOT}/workers/tabular/Dockerfile" -t k8s-llm-job-worker-tabular:local "${ROOT}"
fi

echo "Loading images into kind cluster..."
kind load docker-image k8s-llm-job-backend:local --name k8s-llm-job
kind load docker-image k8s-llm-job-worker-pdf:local --name k8s-llm-job
kind load docker-image k8s-llm-job-worker-tabular:local --name k8s-llm-job

echo "Applying manifests..."
kubectl apply -f "${ROOT}/deploy/app/backend-rbac.yaml"
kubectl apply -f "${ROOT}/deploy/app/minio.yaml"
kubectl apply -f "${ROOT}/deploy/app/backend-deploy.yaml"

echo "Deploying Prometheus + Grafana..."
kubectl create configmap grafana-dashboard-json \
  --from-file="k8s-llm-job.json=${ROOT}/deploy/observability/grafana-dashboard.json" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "${ROOT}/deploy/observability/prometheus.yaml"

echo "Waiting for MinIO..."
kubectl rollout status deployment/minio --timeout=120s
echo "Waiting for backend..."
kubectl rollout status deployment/k8s-llm-job-backend --timeout=120s
echo "Waiting for kube-state-metrics..."
kubectl rollout status deployment/kube-state-metrics --timeout=120s
echo "Waiting for Prometheus..."
kubectl rollout status deployment/prometheus --timeout=120s
echo "Waiting for Grafana..."
kubectl rollout status deployment/grafana --timeout=120s

if [[ "${WITH_KSERVE}" == "true" ]]; then
  assert_command curl "Install curl so the script can health-check the KServe port-forward."
  echo "Installing KServe (this takes several minutes)..."
  bash "${ROOT}/deploy/kserve/install.sh"
  echo "Deploying InferenceService (vllm)..."
  kubectl apply -f "${ROOT}/deploy/kserve/inferenceservice.yaml"
  echo "Waiting for InferenceService to become ready (timeout: ${KSERVE_READY_TIMEOUT_SECONDS}s)..."
  kubectl wait inferenceservice/vllm --for=condition=Ready --timeout="${KSERVE_READY_TIMEOUT_SECONDS}s" -n default
  echo "Switching backend provider to KServe..."
  set_backend_provider_config "kserve" "false"
  echo "Starting predictor port-forward..."
  start_kserve_port_forward
fi

echo
echo "Cluster is ready."
echo "  Backend:         http://localhost:8000"
echo "  MinIO API:       http://localhost:9000"
echo "  MinIO console:   http://localhost:9001"
echo "  Prometheus:      http://localhost:9090"
echo "  Grafana:         http://localhost:3000  (admin/admin)"
if [[ "${WITH_KSERVE}" == "true" ]]; then
  echo "  KServe/vLLM:     http://localhost:8080/v1  (kubectl port-forward)"
fi
echo
echo "Profiles:"
echo "  local-fast:  bash scripts/demo.sh local-fast"
echo "  kserve-cpu:  bash scripts/demo.sh kserve-cpu  (requires --with-kserve)"
