#!/usr/bin/env bash
# Cross-platform load-test wrapper for Linux/WSL.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT}"
exec uv run --all-extras python scripts/load_test.py "$@"
