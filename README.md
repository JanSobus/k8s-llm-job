# CERN ML Demo

Portfolio project for the [CERN IT-CD-PI-2026-63-LD Machine Learning Engineer (Grade 6)](https://careers.cern/jobs/it-cd-pi-2026-63-ld/) role.

A user-facing FastAPI + HTMX chat application that demonstrates the JD's core platform engineering capabilities:
scalable model serving (KServe + vLLM), dynamic batch workload orchestration (Kubernetes Jobs),
model lifecycle operations, secure multi-tenant posture, and reference architecture judgement.

---

## Architecture

```
┌───────────────────────────────────────────────┐
│ Browser  (HTMX + Jinja2)                      │
└──────────────────┬────────────────────────────┘
                   │ HTML fragments
┌──────────────────▼────────────────────────────┐
│ FastAPI backend                               │
│  /          chat UI (Jinja2)                  │
│  /chat      LLM response (HTMX fragment)      │
│  /upload    validates + stores upload         │
│  /jobs/{id} status + result polling           │
│  /metrics   Prometheus exposition             │
└──────┬───────────────────────┬────────────────┘
       │ OpenAI-compatible     │ k8s API
       │ /v1/chat/completions  │ creates Jobs
       ▼                       ▼
┌──────────────────┐    ┌──────────────────────┐
│ LLM providers    │    │ Worker Job pods      │
│  kserve + vLLM   │◄───┤  worker-pdf          │
│  openai          │    │  worker-tabular      │
│  ollama          │    └────┬─────────────────┘
└──────────────────┘         │ reads / writes
                             ▼
                      ┌──────────────┐
                      │ MinIO (S3)   │
                      │ uploads +    │
                      │ results      │
                      └──────────────┘

Observability: Prometheus scrapes /metrics.
Grafana dashboard: chat latency/errors, active jobs,
job duration, pod counts.
```

**Key design choices**

- **Single client contract** — all three providers expose `/v1/chat/completions`. The backend picks the provider via `APP_LLM_PROVIDER`; workers and chat share the same factory.
- **KServe is the owned-inference path** — not a proxy to OpenAI. It demonstrates versioned InferenceService lifecycle, concurrency-based HPA, and a self-hosted vLLM runtime. See [docs/design-notes.md](docs/design-notes.md) for the KServe vs Triton rationale and standard mode vs Knative trade-offs.
- **Workers are clients of the serving layer** — PDF and tabular workers call the same LLM endpoint as the chat handler. One serving contract, two workload patterns.
- **MinIO is a local S3-compatible service** — no external S3 account required. The backend creates the `cern-ml-demo` bucket on first use.

---

## Demo profiles

| Profile | Command | Provider | Requires |
|---------|---------|----------|---------|
| `local-fast` | `.\scripts\demo.ps1` | OpenAI or Ollama | Docker (MinIO) |
| `kserve-cpu` | `.\scripts\up.ps1 -Mode kind -WithKServe` | KServe + vLLM | kind, kubectl, Helm, ~8 GB RAM |

---

## Quick start — local-fast (Windows)

**Prerequisites:** Docker Desktop running, Python 3.12, `uv`.

```powershell
# 1. Copy and edit env (set APP_OPENAI_API_KEY or switch to ollama)
cp .env.example .env

# 2. Start MinIO
.\scripts\up.ps1

# 3. Start the backend (hot-reload)
.\scripts\demo.ps1
```

Open `http://localhost:8000`.

To switch provider, set `APP_LLM_PROVIDER` in `.env`:

```
APP_LLM_PROVIDER=ollama     # local, no API key needed
APP_LLM_PROVIDER=openai     # default; requires APP_OPENAI_API_KEY
APP_LLM_PROVIDER=kserve     # in-cluster; use with kserve-cpu profile
```

---

## Quick start — kserve-cpu (kind cluster)

**Prerequisites:** Docker Desktop (≥ 8 GB RAM allocated), kind, kubectl, Helm, Git Bash or WSL (for the install shell script).

```powershell
# Build images, create cluster, deploy all manifests + observability
.\scripts\up.ps1 -Mode kind

# Optional: also install KServe + deploy vLLM InferenceService
.\scripts\up.ps1 -Mode kind -WithKServe
```

URLs after `up.ps1` completes:

| Service | URL |
|---------|-----|
| Backend | http://localhost:8000 |
| MinIO console | http://localhost:9001 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 (admin/admin) |
| KServe/vLLM | http://localhost:8080/v1 (with `-WithKServe`) |

Tear down:

```powershell
.\scripts\down.ps1 -Mode kind
```

---

## Make targets

```
make demo           # local-fast: start backend (requires up.ps1 first)
make up             # local MinIO only
make kind-up        # full kind cluster
make kind-down      # delete kind cluster
make build-images   # build backend + both worker images
make lint           # ruff check
make typecheck      # pyright (strict)
make test           # pytest
make load-test      # fire N concurrent chat requests
```

---

## Provider model

| Setting | Value | Notes |
|---------|-------|-------|
| `APP_LLM_PROVIDER` | `openai` / `ollama` / `kserve` | Selects the active provider |
| `APP_OPENAI_API_KEY` | — | Required when provider=openai |
| `APP_OPENAI_MODEL` | `gpt-4o-mini` | Override as needed |
| `APP_OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama OpenAI-compatible endpoint |
| `APP_OLLAMA_MODEL` | `qwen2.5:0.5b` | Any model pulled in Ollama |
| `APP_KSERVE_BASE_URL` | `http://vllm-predictor.default.svc.cluster.local/v1` | In-cluster KServe endpoint |
| `APP_KSERVE_MODEL` | `Qwen/Qwen2.5-0.5B-Instruct` | Must match InferenceService |
| `APP_LLM_FAKE_MODE` | `true` | Bypass real LLM calls (default for safety) |

All settings use the `APP_` prefix and can be set in `.env` or as environment variables.

---

## Upload flow

1. `POST /upload` — validates MIME type (PDF or CSV), enforces 10 MB limit, stores input in MinIO under `jobs/{id}/input/{filename}`.
2. Backend creates a job record in MinIO (`jobs/{id}/metadata.json`) and returns an HTMX job-status card.
3. Depending on `APP_JOB_EXECUTION_MODE`:
   - **`local`** (default): worker logic runs in a background thread.
   - **`kubernetes`**: backend submits a `batch/v1 Job` using the `cern-ml-demo-backend` service account.
4. Worker reads input from MinIO, calls the LLM, writes `jobs/{id}/result.json`.
5. UI polls `/jobs/{id}/fragment` every 2 s and replaces the card when the job reaches a terminal state.

Worker images use stable local tags: `cern-ml-demo-worker-pdf:local`, `cern-ml-demo-worker-tabular:local`.

---

## Observability

The backend exposes Prometheus metrics at `/metrics`:

| Metric | Type | Labels |
|--------|------|--------|
| `cern_ml_chat_requests_total` | Counter | `provider`, `status` |
| `cern_ml_chat_latency_seconds` | Histogram | `provider` |
| `cern_ml_active_jobs` | Gauge | `worker_type` |
| `cern_ml_job_completions_total` | Counter | `worker_type`, `status` |
| `cern_ml_job_duration_seconds` | Histogram | `worker_type` |

The Grafana dashboard (`deploy/observability/grafana-dashboard.json`) visualises all five metric groups with chat latency percentiles, job completion rate, and container resource usage. It is provisioned automatically by `up.ps1 -Mode kind`.

---

## Security posture

- `cern-ml-demo-backend` ServiceAccount with a least-privilege Role: `batch/jobs` (get/list/watch/create/delete), `pods/log` (get/list/watch) — no cluster-wide permissions.
- Worker pods run with resource requests and limits; `ttlSecondsAfterFinished: 600` cleans up automatically.
- Upload endpoint enforces MIME allowlist and safe filename sanitisation.
- MinIO credentials injected via Kubernetes Secret, not ConfigMap.

See [docs/design-notes.md](docs/design-notes.md) for the multi-tenancy extension path (namespace isolation, network policy, Vault secrets, HTCondor fair-share integration).

---

## Repository layout

```
backend/            FastAPI app (config, llm, chat, upload/jobs, metrics)
workers/pdf/        PyMuPDF extraction worker
workers/tabular/    Polars + LLM summarisation worker
workers/shared/     Shared LLM client + MinIO helpers
deploy/
  app/              Deployment, Service, RBAC, MinIO, job templates
  kind/             kind cluster config (NodePort mappings)
  kserve/           ServingRuntime, InferenceService, install script
  observability/    Prometheus + Grafana manifests + dashboard JSON
docs/
  design-notes.md   Architecture rationale (KServe, multi-tenancy, GPU path)
  benchmark.md      Local performance results and hardware assumptions
  demo-script.md    Reviewer walkthrough
scripts/            PowerShell demo/up/down/load-test
examples/           sample.pdf and sample.csv for demo validation
```

---

## Further reading

- [docs/design-notes.md](docs/design-notes.md) — KServe vs Triton, standard vs Knative, model lifecycle, multi-tenancy, GPU efficiency, RAG path
- [docs/benchmark.md](docs/benchmark.md) — local latency/throughput results
- [AGENTS.md](AGENTS.md) — toolchain conventions for future agent sessions
