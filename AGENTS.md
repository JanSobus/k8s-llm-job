# Agent Guidance

This project is a portfolio demo for the CERN IT-CD-PI-2026-63-LD Machine Learning Engineer role. Keep work aligned with `plan.md`: a reliable local FastAPI demo first, then Kubernetes Jobs, MinIO, KServe/vLLM, observability, and documentation.

## Tooling

- Use Python 3.12.
- Use `uv` for all Python dependency management, locking, local execution, Docker installs, tests, and CI.
- Use the latest installed `ruff`, `pyright`, and `pytest` through `uv` or `uvx`.
- Do not introduce Poetry, pip-tools, Black, mypy, npm frontend tooling, or alternate test runners without explicit approval.
- Use `gh` for GitHub repository, issue, pull request, and workflow operations.

## Architecture Guardrails

- Preserve the provider split:
  - `openai`: external managed provider for fast iteration and fallback.
  - `ollama`: lightweight local developer provider.
  - `kserve`: owned/scaled inference expansion path.
- Do not wrap OpenAI in KServe as the core architecture. KServe is for self-hosted, platform-operated inference.
- Keep the demo profiles clear: `local-fast`, `kserve-cpu`, and `gpu-notes`.
- MinIO is a local S3-compatible service for upload/result storage. It does not require an external S3 account.
- Backend and worker pods should share one OpenAI-compatible LLM client contract.

## Implementation Style

- Keep the first working path simple and reliable before adding infrastructure.
- Prefer HTMX + Jinja served by FastAPI; do not add a frontend build system.
- Keep one root `pyproject.toml` initially, with dependency groups/extras as needed.
- Use stable local image names when container work starts:
  - `cern-ml-demo-backend:local`
  - `cern-ml-demo-worker-pdf:local`
  - `cern-ml-demo-worker-tabular:local`
- Windows PowerShell scripts in `scripts/*.ps1` are first-class demo entrypoints.

## Quality Bar

- Run `uv run ruff check .`, `uv run pyright`, and `uv run pytest` after substantive Python edits.
- Keep tests focused on provider selection, configuration, route smoke checks, and worker behavior as features are added.
- Do not spend time on production auth, a polished frontend, a third worker, RAG, or a Helm chart unless explicitly requested.
