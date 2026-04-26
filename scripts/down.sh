#!/usr/bin/env bash
# Tear down local demo services or the kind-backed Kubernetes demo on Linux/WSL.
set -euo pipefail

MODE="local"
CONTAINER_NAME="k8s-llm-job-minio"
VOLUME_NAME="k8s-llm-job-minio-data"
REMOVE_DATA="false"
PORT_FORWARD_PID_FILE="${TMPDIR:-/tmp}/k8s-llm-job-vllm-port-forward.pid"

usage() {
  cat <<'EOF'
Usage: bash scripts/down.sh [options]

Options:
  --mode local|kind            Tear down local MinIO or the kind profile (default: local)
  --container-name NAME        Local MinIO container name (default: k8s-llm-job-minio)
  --volume-name NAME           Local MinIO Docker volume name (default: k8s-llm-job-minio-data)
  --remove-data                Remove the local MinIO volume as well as the container
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
    --remove-data)
      REMOVE_DATA="true"
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
  local message="$2"
  if ! command -v "${name}" >/dev/null 2>&1; then
    echo "${message}" >&2
    exit 1
  fi
}

assert_docker() {
  assert_command docker "Docker is required."
  if ! docker info >/dev/null 2>&1; then
    echo "Docker daemon is not reachable. Start Docker Desktop/WSL integration or native Docker and retry." >&2
    exit 1
  fi
}

stop_kserve_port_forward() {
  if [[ ! -f "${PORT_FORWARD_PID_FILE}" ]]; then
    return 0
  fi

  local pid
  pid="$(<"${PORT_FORWARD_PID_FILE}")"
  if [[ -n "${pid}" && "${pid}" =~ ^[0-9]+$ ]] && kill -0 "${pid}" >/dev/null 2>&1; then
    kill "${pid}" >/dev/null 2>&1 || true
    echo "Stopped KServe port-forward process ${pid}."
  fi
  rm -f "${PORT_FORWARD_PID_FILE}"
}

if [[ "${MODE}" == "local" ]]; then
  assert_docker
  existing="$(docker ps -a --filter "name=^/${CONTAINER_NAME}$" --format '{{.Names}}')"
  if [[ "${existing}" == "${CONTAINER_NAME}" ]]; then
    docker rm --force "${CONTAINER_NAME}" >/dev/null
    echo "Removed MinIO container ${CONTAINER_NAME}."
  else
    echo "MinIO container ${CONTAINER_NAME} does not exist."
  fi

  if [[ "${REMOVE_DATA}" == "true" ]]; then
    docker volume rm "${VOLUME_NAME}" --force >/dev/null 2>&1 || true
    echo "Removed MinIO volume ${VOLUME_NAME}."
  else
    echo "Preserved MinIO volume ${VOLUME_NAME}. Pass --remove-data to delete it."
  fi
  exit 0
fi

assert_command kind "'kind' not found. Install kind and ensure it is available in this shell."
if kind get clusters 2>/dev/null | grep -Fxq "k8s-llm-job"; then
  stop_kserve_port_forward
  echo "Deleting kind cluster 'k8s-llm-job'..."
  kind delete cluster --name k8s-llm-job
  echo "Cluster deleted."
else
  echo "Kind cluster 'k8s-llm-job' does not exist."
fi
