# Project Gaps

Audited 2026-04-26. Remediated 2026-04-26.

## Closed Verified Gaps

1. **Coverage tracking** — `pytest-cov` is in dev dependencies, pytest runs with coverage for `backend` and `workers`, and CI enforces the configured threshold.
2. **Security scanning** — CI runs Bandit over application/worker/script code and `pip-audit` over dependencies.
3. **KServe smoke in CI** — `.github/workflows/ci.yml` runs the lightweight kind + KServe smoke predictor path with `scripts/e2e_kserve_smoke.py`.
4. **Worker/shared tests** — `workers/tests/test_shared.py` covers shared LLM fallback behavior and shared storage key exports.
5. **Worker behavior tests** — PDF and tabular worker tests now cover extraction/stat output, LLM summary success, LLM fallback notes, and failure status persistence.
6. **Architecture diagram source** — `docs/architecture.mmd` captures the current backend, worker, storage, provider, and observability flow.
7. **KServe/vLLM observability** — Prometheus scrapes the KServe predictor metrics endpoint, and Grafana includes vLLM request, token, queue, and latency panels.
8. **Pre-commit hooks** — `.pre-commit-config.yaml` provides local ruff, pyright, and pytest coverage hooks through `uv`.

## Reconciled Stale Items

- README already used `uv sync --all-extras`; the kind prerequisites now clarify Docker Desktop CPU/RAM needs.
- Grafana dashboard provisioning was already automated in both deploy scripts.
- KServe env propagation already existed through the backend config and worker Job env mirroring; docs/checklists now reflect that state.
