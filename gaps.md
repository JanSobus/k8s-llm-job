# Project Gaps

Audited 2026-04-26.

## CI / Quality

1. **No test coverage tracking** — `pytest-cov` not in deps, no coverage thresholds enforced in CI.
2. **No security scanning** — no Bandit, Semgrep, or CVE dependency check in `.github/workflows/ci.yml`.
3. **E2e smoke test not wired to CI** — `scripts/e2e_kserve_smoke.py` and `backend/app/kserve_smoke.py` exist but are not called by CI; `plan.md` marks this as a TODO.

## Test Coverage

4. **`workers/shared/` untested** — `workers/shared/llm.py` and `workers/shared/storage.py` have no test files.
5. **Worker logic minimally tested** — `workers/pdf/worker.py` and `workers/tabular/worker.py` extraction and summarization paths have no meaningful tests.

## Documentation

6. **Architecture diagram missing** — referenced in `plan.md` and `docs/` but the file does not exist.
7. **README quick-start incomplete** — omits Docker Desktop resource requirements for kind and does not make `uv sync --all-extras` explicit.

## Observability

8. **KServe/vLLM has no Prometheus metrics** — serving latency and throughput are invisible to Prometheus/Grafana.
9. **Grafana dashboard provisioning is manual** — `kubectl create configmap` step is not automated in deploy scripts.

## Incomplete Plan Items

10. **KServe end-to-end chat validation missing** — `plan.md` checkbox open: validate `/chat` end-to-end against in-cluster KServe endpoint.
11. **KServe provider not documented in cluster env vars** — workers use hardcoded or default provider selection; no comment on KServe override path.
12. **CI smoke test integration** — `plan.md` promises CI integration of the KServe smoke test; not yet added.

## Tooling

13. **No pre-commit hooks** — no `.pre-commit-config.yaml`; ruff/pyright/tests are only enforced in CI, not locally before push.
