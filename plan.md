# CERN ML Demo — Implementation Plan

## Context

Portfolio project supporting an application to [**CERN IT-CD-PI-2026-63-LD (Machine Learning Engineer, Grade 6)**](https://careers.cern/jobs/it-cd-pi-2026-63-ld/). Deadline: **April 29, 2026**. The repo is the primary technical artefact backing the CV — it must demonstrate, in a single coherent narrative, the JD's main capability areas:

1. **Scalable model serving** (long-running, autoscalable) — KServe + vLLM
2. **Dynamic per-workload pod orchestration** (k8s Jobs) — for batch workloads
3. **Model lifecycle and platform operations** — versioning, rollout/rollback notes, benchmarks, observability
4. **Secure multi-tenant platform thinking** — RBAC, service accounts, resource limits, namespace/label strategy
5. **Reference architecture judgement** — explicit tradeoffs for KServe, vLLM, external providers, and future RAG/agent paths

A user-facing app (chat + file upload) sits on top, giving the infrastructure something concrete to do. The demo must run end-to-end on Windows with `scripts/demo.ps1`; `make demo` remains a convenience wrapper for environments with Make installed.

## Architecture

```
┌───────────────────────────────────────────────┐
│ Browser (HTMX + Jinja, SSE for streaming)     │
└──────────────────┬────────────────────────────┘
                   │
┌──────────────────▼────────────────────────────┐
│ FastAPI backend                               │
│  /               chat UI (Jinja)              │
│  /chat           SSE stream (PydanticAI)      │
│  /upload         validates + stores upload    │
│  /jobs/{id}      status + result polling      │
│  /metrics        Prometheus exposition        │
└──────┬───────────────────────┬────────────────┘
       │ OpenAI-compatible     │ K8s API
       │ LLM client            │ creates Jobs
       ▼                       ▼
┌──────────────────┐    ┌──────────────────────┐
│ Provider targets │    │ Worker Job pods      │
│ - KServe + vLLM  │◄───┤  - worker-pdf        │
│ - OpenAI         │    │  - worker-tabular    │
│ - Ollama         │    └────┬─────────────────┘
└──────────────────┘         │
       ▲                     │ reads/writes
       │                     ▼
       │              ┌──────────────┐
       └──────────────┤ MinIO (S3)   │
                      │ uploads +    │
                      │ results      │
                      └──────────────┘

Observability: Prometheus scrapes backend + KServe + kube-state-metrics.
Default Grafana dashboard: chat latency/errors, active jobs, job duration/status,
serving endpoint health, pod counts, and token throughput when exposed.
GPU utilisation is documented as part of the optional GPU expansion profile.
```

**Key design choices**

- **Single client contract** — OpenAI-compatible (`/v1/chat/completions`). vLLM, Ollama, and OpenAI all expose this. PydanticAI's `OpenAIModel` with configurable `base_url` is the only abstraction needed.
- **KServe is the owned inference expansion path** — KServe should demonstrate how the platform would operate self-hosted, autoscaled vLLM models. OpenAI and Ollama are provider adapters for iteration/fallback, not things to wrap in KServe for the core demo.
- **Provider-pluggable, KServe-ready** — `LLM_PROVIDER` selects between `kserve` (production-style self-hosted path), `openai` (fast iteration), and `ollama` (local without k8s).
- **Workers are clients of the serving layer**, not separate model loaders. One model-serving contract, two workload patterns. Demonstrates layered architecture and realistic load (many jobs → autoscale).
- **Routing in backend**, not in the cluster — keeps infra simple. Backend picks worker image + Job template by MIME type.
- **uv for all Python services** — backend and worker pods use the same uv-managed project/workspace conventions for dependency locking, Docker builds, local execution, tests, and CI.
- **Latest built-in Python tooling** — use the installed latest `uv`, `ruff`, `pyright`, and `pytest` consistently across backend and workers. Capture this explicitly in `AGENTS.md` so future agents do not introduce alternate package/test/lint tooling.
- **Python 3.12 baseline** — use Python 3.12 locally, in Docker images, and in CI unless a dependency forces a documented change.
- **Single root uv project first** — start with one root `pyproject.toml` and dependency groups/extras for backend, workers, dev, and optional kserve tooling. Only split into a uv workspace if package boundaries become genuinely useful.
- **gh for repo management** — use the GitHub CLI for repository creation, remote setup, issue/PR checks, and any GitHub workflow interactions instead of managing those steps manually in the browser.
- **Project guidance from day one** — scaffold `AGENTS.md` at the start from this plan so future agent sessions preserve the project goals, uv conventions, provider strategy, demo profiles, and scope guardrails.
- **Stable local image names** — scripts and manifests should use fixed local tags from the start: `cern-ml-demo-backend:local`, `cern-ml-demo-worker-pdf:local`, and `cern-ml-demo-worker-tabular:local`.
- **Deadline guardrail** — local KServe + vLLM is the highest-risk part. Use a CPU-friendly default model and keep a reliable OpenAI/Ollama demo path working at all times.

## Demo profiles

| Profile | Purpose | Provider | Expected to work locally? |
|---------|---------|----------|---------------------------|
| `local-fast` | Fast development and reliable reviewer fallback | OpenAI or Ollama | Yes |
| `kserve-cpu` | Portfolio proof of owned/scaled inference path | KServe standard mode + CPU vLLM | Yes, with small model and sufficient Docker resources |
| `gpu-notes` | CERN-scale expansion documentation | KServe + vLLM on GPU | Documented, not required locally |

Default local KServe model should be CPU-friendly: `Qwen/Qwen2.5-0.5B-Instruct`, `TinyLlama/TinyLlama-1.1B-Chat-v1.0`, or another small OpenAI-compatible vLLM-supported model. `Qwen2.5-3B-Instruct` is an optional stronger profile for machines with enough memory.

## Frontend recommendation: HTMX + Jinja2 (Python-only)

**Recommendation: HTMX + Jinja2 templates served by FastAPI.** Reasoning:

- **Streamlit (Python)**: ships fastest, but reads as "ML researcher who can't ship real systems" — exactly the perception to avoid for a Grade 6 platform role.
- **Next.js / React + TS**: looks professional but burns 1–2 days on frontend that adds no CERN-relevant signal. High risk of not finishing core infra.
- **HTMX + Jinja**: one language, one process, real HTML, SSE streaming for chat is natural with FastAPI. Modern, well-regarded, frames you as "thoughtful minimalist" rather than "data scientist" or "didn't finish."

If HTMX feels unfamiliar mid-build, fall back to Streamlit on day 4 — the backend contract is the same.

## Repository structure

Location: `C:\Users\Jan\projects\cern-ml-demo`

```
cern-ml-demo/
├── README.md                    architecture diagram, one-command demo, design notes
├── AGENTS.md                    persistent agent guidance generated from this plan
├── Makefile                     convenience wrapper around scripts/*.ps1
├── pyproject.toml               uv-managed workspace/project; backend + worker deps
├── uv.lock
├── .env.example                 LLM_PROVIDER, OPENAI_API_KEY, KSERVE_URL, etc.
├── .github/workflows/ci.yml     lint, type-check, unit tests, image builds
├── examples/
│   ├── sample.csv               small tabular upload fixture
│   └── sample.pdf               small PDF upload fixture
├── scripts/
│   ├── demo.ps1                 primary Windows demo entrypoint
│   ├── up.ps1                   create kind cluster + deploy dependencies
│   ├── down.ps1                 teardown
│   └── load-test.ps1            small concurrency smoke/load test
│
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI app, routes, lifespan
│   │   ├── config.py            pydantic-settings (Provider enum, base URLs)
│   │   ├── llm.py               PydanticAI client factory (provider switch)
│   │   ├── chat.py              SSE streaming endpoint + small tool-using agent
│   │   ├── jobs.py              k8s Job submission + status (kubernetes-asyncio)
│   │   ├── routing.py           MIME → worker template resolver
│   │   ├── storage.py           MinIO client (boto3)
│   │   ├── metrics.py           prometheus_client custom metrics
│   │   ├── schemas.py           PydanticAI extraction schemas (PDF, tabular)
│   │   └── templates/           Jinja2: index.html, chat.html, results.html
│   └── tests/                   pytest, fakes for k8s + LLM
│
├── workers/
│   ├── shared/                  uv-managed shared worker helpers / llm client
│   ├── pdf/
│   │   ├── Dockerfile
│   │   └── main.py              PyMuPDF → PydanticAI extraction → MinIO write
│   └── tabular/
│       ├── Dockerfile
│       └── main.py              Polars → column stats → LLM summarisation
│
├── deploy/
│   ├── kind/cluster.yaml        kind config with port mappings
│   ├── kserve/
│   │   ├── install.sh           KServe + dependencies via helm
│   │   └── inferenceservice.yaml  vLLM serving runtime, CPU-friendly small model
│   ├── app/
│   │   ├── backend-deploy.yaml
│   │   ├── backend-rbac.yaml
│   │   ├── minio.yaml
│   │   ├── job-template-pdf.yaml
│   │   └── job-template-tabular.yaml
│   └── observability/
│       ├── prometheus.yaml
│       └── grafana-dashboard.json
│
└── docs/
    ├── architecture.png         exported from README diagram
    ├── design-notes.md          why KServe over Triton, multi-tenancy considerations,
    │                            CERN-scale extensions (HTCondor integration, fair-share),
    │                            lifecycle, provider tradeoffs, future RAG integration
    ├── benchmark.md             local benchmark results + hardware assumptions
    └── demo-script.md           reviewer walkthrough
```

## Configuration model

`backend/app/config.py` using `pydantic-settings`:

```python
class Provider(str, Enum):
    KSERVE = "kserve"
    OPENAI = "openai"
    OLLAMA = "ollama"

class Settings(BaseSettings):
    llm_provider: Provider = Provider.OPENAI
    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2.5:0.5b"
    kserve_base_url: str = "http://vllm-predictor.default.svc.cluster.local/v1"
    kserve_model: str = "Qwen/Qwen2.5-0.5B-Instruct"
    minio_endpoint: str = "http://minio.default.svc.cluster.local:9000"
    max_concurrent_jobs: int = 5
    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_")
```

## Day-by-day plan (4 days, April 25 → April 28)

**Day 1 (Apr 25) — Backend skeleton + provider abstraction**
- `uv init --python 3.12`, project scaffolding, root pyproject + lockfile for backend and worker components
- Configure root dependency groups/extras for backend, workers, dev, and optional kserve tooling before adding code
- Create `AGENTS.md` from this plan: latest `uv`/`ruff`/`pyright`/`pytest` workflow, provider strategy, KServe scope, Windows demo path, security/observability expectations, and tools not to introduce without approval
- `config.py`, `llm.py` (PydanticAI client, three providers), `schemas.py`
- `/chat` SSE endpoint working against OpenAI (fast iteration)
- PydanticAI tool signal: chat agent can check job status or summarise latest upload result
- HTMX index + chat template, basic styling
- Windows script skeletons: `scripts/demo.ps1`, `scripts/up.ps1`, `scripts/down.ps1`
- Add tiny `examples/sample.csv` and `examples/sample.pdf` fixtures for demo validation
- Unit tests: provider switching, schema validation
- Use `gh` for repo setup / GitHub interactions; commit + push to GitHub

**Day 2 (Apr 26) — k8s Jobs + workers**
- `routing.py`, `jobs.py` (kubernetes-asyncio client, Job creation, watch/status)
- `/upload` and `/jobs/{id}` endpoints
- Worker images: `pdf` (PyMuPDF + extraction) and `tabular` (Polars + summarisation), built with uv inside Docker
- MinIO deployment + `storage.py`
- Upload size limits, MIME allowlist, safe object keys, clear error states
- Worker/backend service accounts, least-privilege RBAC, resource requests/limits, Job TTL cleanup
- kind cluster config + Makefile targets (`make up`, `make down`)
- Test end-to-end on kind with OpenAI provider

**Day 3 (Apr 27) — KServe + vLLM**
- Install KServe standard mode via helm/manifests (install helm first)
- Deploy vLLM InferenceService with CPU-friendly small model
- Wire `kserve` provider, validate chat works against in-cluster endpoint
- Workers also use KServe by default
- HPA on the serving deployment/InferenceService where supported
- Midday cutoff: if local KServe is unstable, freeze the reliable OpenAI/Ollama demo path and keep KServe manifests + failure notes + expansion documentation rather than burning the polish day

**Day 4 (Apr 28) — Observability, polish, write-up**
- Prometheus + Grafana via helm
- Backend exposes `/metrics` (chat latency/errors, active jobs, job duration/status, queue depth)
- One Grafana dashboard JSON checked in
- `docs/benchmark.md`: local hardware assumptions, model, concurrency, latency/throughput, limitations
- README: architecture diagram, Windows one-command demo, design notes section explaining provider roles, KServe-vs-Triton, KServe standard-vs-Knative/LLMInferenceService, multi-tenancy, CERN-scale extensions
- CI workflow: lint (ruff), type-check (pyright/mypy), pytest, image build; full kind/KServe validation is optional/manual unless time remains
- Tag v0.1.0, link in CV

## Critical files to create

| Path | Purpose |
|------|---------|
| `AGENTS.md` | persistent agent guidance distilled from this plan |
| `pyproject.toml` | single root uv project on Python 3.12 with dependency groups/extras for backend, workers, dev, and optional kserve tooling |
| `uv.lock` | lockfile committed for reproducible backend, worker, Docker, and CI installs |
| `backend/app/config.py` | pydantic-settings provider switch |
| `backend/app/llm.py` | PydanticAI factory — single OpenAI-compat client across providers |
| `backend/app/jobs.py` | k8s Job creation + status (uses kubernetes-asyncio) |
| `backend/app/routing.py` | MIME-type → worker template selector |
| `scripts/demo.ps1` | primary Windows demo path |
| `scripts/up.ps1` | cluster/dependency setup |
| `scripts/down.ps1` | clean teardown |
| `examples/sample.csv` | tabular upload fixture |
| `examples/sample.pdf` | PDF upload fixture |
| `workers/pdf/main.py` | PDF extraction worker entrypoint |
| `workers/tabular/main.py` | Tabular analysis worker entrypoint |
| `deploy/app/backend-rbac.yaml` | service accounts + least-privilege RBAC |
| `deploy/kserve/inferenceservice.yaml` | KServe + vLLM owned-inference path |
| `deploy/observability/grafana-dashboard.json` | the screenshot in the README |
| `Makefile` | `demo`, `up`, `down`, `load-test`, `lint`, `test` |
| `docs/benchmark.md` | local benchmark results and limitations |
| `README.md` | architecture diagram, Windows one-command demo, design notes |

## Verification (end-to-end)

1. `scripts/demo.ps1` — primary Windows path; installs/deploys enough to run the selected profile and prints URLs
2. `make demo` — convenience equivalent for environments with Make installed
3. Open `http://localhost:8000` — chat interface loads
4. Send chat message — streams response through configured provider (`openai`, `ollama`, or `kserve`)
5. Upload a PDF — `/jobs/{id}` shows pod creation, status transitions, result URL
6. Upload a CSV — different worker pod spins up, returns column-level summary
7. Open `http://localhost:3000` (Grafana) — dashboard shows live backend/job metrics
8. `scripts/load-test.ps1` or `make load-test` — fires N concurrent requests; if KServe is active, observe serving replica/latency impact
9. `scripts/down.ps1` or `make down` — clean teardown

CI must pass on push using the latest installed `uv`, `ruff`, `pyright`, and `pytest` toolchain (lint, type-check, unit tests, image builds). Full kind/KServe validation is documented as a manual smoke test unless there is time to add a separate optional workflow.

## Documentation requirements

- README must explain the provider model clearly:
  - `openai`: external managed provider for fast iteration and reliable fallback
  - `ollama`: lightweight local developer provider
  - `kserve`: future expansion path for platform-owned, scaled inference providers
- README must explain that MinIO is a local S3-compatible service in the demo and does not require an external S3 account.
- `docs/design-notes.md` must cover:
  - why KServe is not used merely to proxy OpenAI
  - KServe standard mode vs Knative vs `LLMInferenceService`
  - KServe vs Triton for this demo
  - model lifecycle: versioning, rollout/rollback, benchmark capture, promotion criteria
  - secure multi-tenant path: namespaces, RBAC, quotas, secrets, service accounts, network policy
  - future RAG path without implementing a vector store
  - accelerator efficiency path: GPU scheduling, batching, KV cache, tensor/data parallelism, token throughput metrics
- `docs/benchmark.md` must capture actual local results and limitations, even if the local KServe path is constrained by CPU/RAM.
- `AGENTS.md` must explicitly say:
  - use latest installed `uv`, `ruff`, `pyright`, and `pytest`
  - keep Python at 3.12 unless a documented dependency constraint requires otherwise
  - do not introduce Poetry, pip-tools, Black, mypy, npm frontend tooling, or alternate test runners without explicit approval
  - use `gh` for GitHub operations
  - preserve the `local-fast`, `kserve-cpu`, and `gpu-notes` scope split
  - keep KServe focused on owned/scaled inference rather than proxying OpenAI

## Optional task breakdown

After `AGENTS.md` is created, it is reasonable to use a context-engineering/task-breakdown framework such as GSD to split this plan into implementation slices. Keep it lightweight and deadline-oriented:

- Generate tasks around deliverable increments, not technology categories: backend chat, provider abstraction, upload/jobs, workers, local scripts, KServe path, observability/docs.
- Each task should have acceptance criteria and the files it is allowed to touch.
- Prefer GitHub issues managed with `gh` if the framework creates durable task artifacts.
- Do not let the framework expand scope; it should preserve this plan's cuts and Day 3 KServe cutoff.

## Out of scope (deliberate)

- RAG / vector store (deferred unless day 4 finishes early)
- Production authentication / full multi-tenancy (secure platform posture is shown via RBAC, service accounts, resource controls, and design notes)
- GPU-backed serving on kind (document the GPU path; demo runs CPU-only)
- Production-grade frontend polish
- A third worker type
- Helm chart for the app itself (raw YAML is fine for a demo)
- Wrapping OpenAI inside KServe as the core architecture (low value for this portfolio; document only as an optional gateway pattern)

## Pre-flight (before Day 1)

- Install Helm: `winget install Helm.Helm`
- Install kind and kubectl if missing
- Install and authenticate GitHub CLI: `winget install GitHub.cli`, then `gh auth login`
- Confirm Python 3.12 and latest `uv`, `ruff`, `pyright`, `pytest` are on PATH or available through `uvx`
- Confirm Docker Desktop has enough resources (8GB RAM, 4 CPU minimum for the cluster)
- Prefer 12-16GB Docker memory for `kserve-cpu`; otherwise use `local-fast`
- Create/manage GitHub repo `cern-ml-demo` with `gh` (public)

---

## Implementation progress (updated 2026-04-25)

Legend: ✅ done · ⚠️ partial/deviation · ❌ not yet started

### Day 1 — Backend skeleton + provider abstraction

- [x] `uv init --python 3.12`, root `pyproject.toml` with dependency groups (backend, workers, dev)
- [x] `uv.lock` committed
- [x] `AGENTS.md` created from plan
- [x] `backend/app/config.py` — pydantic-settings, `Provider` enum, all three providers
- [x] `backend/app/llm.py` — provider factory switching across openai / ollama / kserve ⚠️ uses `httpx` directly rather than PydanticAI `OpenAIModel`
- [x] `backend/app/schemas.py` — `ChatRequest`, `ChatResponse`, extraction schemas
- [x] `/chat` POST endpoint returning HTMX HTML fragment ⚠️ plain POST/response, **not SSE streaming**
- [x] `backend/app/templates/index.html` — HTMX UI with basic styling ⚠️ `chat.html` and `results.html` not separated out
- [x] `scripts/demo.ps1`, `scripts/up.ps1`, `scripts/down.ps1`, `scripts/load-test.ps1` (updated with `-Mode` / `-Profile` params)
- [x] `examples/sample.csv` and `examples/sample.pdf` fixtures
- [x] Unit tests: `test_config.py`, `test_llm.py`, `test_routing.py`, `test_storage.py`, `test_jobs.py`, `test_upload.py`
- [x] GitHub repo created with `gh` and code pushed → https://github.com/JanSobus/cern-ml-demo
- [ ] SSE streaming on `/chat` (`text/event-stream`, token-by-token) — deferred (low JD signal)
- [ ] PydanticAI agent with tool use (job-status check, summarise-latest-upload) — deferred (low JD signal)

### Day 2 — k8s Jobs + workers

- [x] `backend/app/routing.py` — MIME → `UploadRoute` / worker-template selector
- [x] `backend/app/jobs.py` — `JobStore` protocol + `MinioJobStore` implementation
- [x] `backend/app/k8s_jobs.py` — `kubernetes-asyncio` Job creation and submission
- [x] `backend/app/local_jobs.py` — background-thread fallback for local dev
- [x] `backend/app/uploads.py` — `/upload`, `/jobs/{id}`, `/jobs/{id}/fragment`, `/jobs/{id}/result` endpoints
- [x] `backend/app/storage.py` — MinIO / S3-compatible object storage client
- [x] `workers/pdf/main.py` + `Dockerfile` — PyMuPDF extraction worker
- [x] `workers/tabular/main.py` + `Dockerfile` — Polars + LLM summarisation worker
- [x] `workers/shared/` — shared LLM client + storage helpers
- [x] `deploy/app/backend-rbac.yaml` — service accounts + least-privilege RBAC
- [x] `deploy/app/job-template-pdf.yaml` and `job-template-tabular.yaml`
- [x] `deploy/app/minio.yaml`
- [x] Upload size limits, MIME allowlist, safe object keys, clear error states
- [x] `backend/Dockerfile` — uv-based backend image (`cern-ml-demo-backend:local`)
- [x] `deploy/app/backend-deploy.yaml` — Deployment + NodePort Service + ConfigMap/Secret
- [x] `deploy/kind/cluster.yaml` — kind cluster config with NodePort mappings (8000/9000/9001/9090/3000/8080)
- [x] `Makefile` updated: `build-backend`, `build-images`, `kind-up`, `kind-down`
- [ ] End-to-end smoke test on kind with OpenAI provider

### Day 3 — KServe + vLLM

- [x] `deploy/kserve/install.sh` — installs cert-manager + KServe via Helm (standard/raw-deployment mode)
- [x] `deploy/kserve/vllm-runtime.yaml` — custom `ServingRuntime` with explicit CPU/GPU vLLM flags
- [x] `deploy/kserve/inferenceservice.yaml` — `InferenceService` for `Qwen2.5-0.5B-Instruct`; concurrency-based HPA (minReplicas=1, maxReplicas=3); GPU expansion documented in comments
- [x] `scripts/up.ps1 -WithKServe` — runs install.sh, deploys InferenceService, waits for Ready
- [ ] Validate `/chat` end-to-end against in-cluster KServe endpoint
- [ ] Workers: document/configure KServe as default provider in cluster env vars

### Day 4 — Observability, polish, write-up

- [x] `backend/app/metrics.py` — `CHAT_REQUESTS`, `CHAT_LATENCY`, `ACTIVE_JOBS`, `JOB_COMPLETIONS`, `JOB_DURATION`
- [x] `GET /metrics` Prometheus exposition endpoint in `main.py`
- [x] `backend/app/chat.py` — instrumented with chat latency + success/error counts
- [x] `pyproject.toml` — `venvPath`/`venv` added to `[tool.pyright]`; pyright reports 0 errors
- [ ] `backend/app/uploads.py` — instrument job lifecycle metrics (`ACTIVE_JOBS`, `JOB_COMPLETIONS`, `JOB_DURATION`)
- [ ] `deploy/observability/prometheus.yaml`
- [ ] `deploy/observability/grafana-dashboard.json`
- [ ] `docs/design-notes.md` (KServe rationale, multi-tenancy, RAG path, GPU path)
- [ ] `docs/benchmark.md` (local results + limitations)
- [ ] `docs/demo-script.md` (reviewer walkthrough)
- [ ] `docs/architecture.png`
- [ ] `.github/workflows/ci.yml` (ruff lint, pyright, pytest, image builds)
- [ ] `README.md` complete — architecture diagram, one-command demo, design notes
- [ ] `v0.1.0` git tag
