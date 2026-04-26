#!/usr/bin/env bash
# Run or describe demo profiles on Linux/WSL.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PROFILE="local-fast"
PORT="8000"

usage() {
  cat <<'EOF'
Usage: bash scripts/demo.sh [local-fast|kserve-cpu] [--port PORT]

Profiles:
  local-fast   Start local MinIO if needed, then run FastAPI with hot reload
  kserve-cpu   Print URLs for the kind-backed KServe profile
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    local-fast | kserve-cpu)
      PROFILE="$1"
      shift
      ;;
    --port)
      PORT="${2:-}"
      shift 2
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

if [[ -z "${PORT}" || ! "${PORT}" =~ ^[0-9]+$ ]]; then
  echo "--port must be a numeric TCP port." >&2
  exit 2
fi

echo "K8s LLM Job - profile: ${PROFILE}"
echo

if [[ "${PROFILE}" == "local-fast" ]]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required for local MinIO." >&2
    exit 1
  fi
  if ! command -v uv >/dev/null 2>&1; then
    echo "'uv' not found. Install uv before starting the backend." >&2
    exit 1
  fi

  echo "Checking MinIO..."
  running="$(docker ps --filter "name=^/k8s-llm-job-minio$" --filter "status=running" --format '{{.Names}}' 2>/dev/null || true)"
  if [[ "${running}" != "k8s-llm-job-minio" ]]; then
    echo "MinIO not running. Starting via up.sh..."
    bash "${SCRIPT_DIR}/up.sh" --mode local
  fi

  echo
  echo "Starting backend on http://localhost:${PORT}"
  echo "Provider comes from .env (set APP_LLM_PROVIDER to switch)."
  echo ".env.example starts with APP_LLM_FAKE_MODE=true; set it to false for real provider responses."
  echo "Stop with Ctrl+C."
  echo
  cd "${ROOT}"
  exec uv run --all-extras uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT}" --reload
fi

echo "kserve-cpu profile: kind-backed demo URLs."
echo "Run 'bash scripts/up.sh --mode kind --with-kserve' first to install KServe and wire the backend to vLLM."
echo
echo "  Backend:  http://localhost:8000"
echo "  vLLM:     http://localhost:8080/v1"
echo "  MinIO:    http://localhost:9001"
echo "  Grafana:  http://localhost:3000  (after observability is deployed)"
