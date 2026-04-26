# K8s LLM Job

A reference platform demonstrating scalable LLM serving on Kubernetes: FastAPI + HTMX frontend,
Kubernetes Jobs for batch workloads (PDF extraction, tabular analysis), MinIO for object storage,
KServe/vLLM for self-hosted model serving, and Prometheus/Grafana for observability.

---

## Architecture

Diagram source: [docs/architecture.mmd](docs/architecture.mmd).

```
┌───────────────────────────────────────────────┐
│ Browser  (HTMX + Jinja2)                      │
└──────────────────┬────────────────────────────┘
                   │ HTML fragments
┌──────────────────▼────────────────────────────┐
│ FastAPI backend                               │
│  /               two-column UI (Jinja2)       │
│  /upload         validates + stores upload    │
│  /jobs           auto-refresh job list        │
│  /jobs/{id}      job metadata (JSON)          │
│  /chat           multi-turn LLM response      │
│  /chat/attach    inject job context           │
│  /chat/detach    remove job context           │
│  /chat/clear     wipe conversation            │
│  /metrics        Prometheus exposition        │
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
- **KServe is the owned-inference path** — not a proxy to OpenAI. It demonstrates versioned InferenceService lifecycle, HPA-backed scaling, and a self-hosted vLLM runtime. See [docs/design-notes.md](docs/design-notes.md) for the KServe vs Triton rationale and standard mode vs Knative trade-offs.
- **Workers are clients of the serving layer** — PDF and tabular workers call the same LLM endpoint as the chat handler. One serving contract, two workload patterns.
- **MinIO is a local S3-compatible service** — no external S3 account required. The backend creates the `k8s-llm-job` bucket on first use.
- **Stateless chat** — conversation history travels as a JSON-encoded hidden form field; no server-side sessions. Each chat POST receives the full prior transcript and returns the updated one embedded in the response fragment.

---

## Demo profiles

| Profile | Windows | Linux/WSL | Provider | Requires |
|---------|---------|-----------|----------|---------|
| `local-fast` | `.\scripts\demo.ps1` | `bash scripts/demo.sh` | OpenAI or Ollama | Docker (MinIO) |
| `kserve-smoke` | `.\scripts\up.ps1 -Mode kind` + smoke manifest | `bash scripts/up.sh --mode kind` + smoke manifest | KServe smoke predictor | kind, kubectl, bash |
| `kserve-cpu` | `.\scripts\up.ps1 -Mode kind -WithKServe` | `bash scripts/up.sh --mode kind --with-kserve` | KServe + vLLM | kind, kubectl, bash, ~12-16 GB RAM |

---

## Quick start — local-fast

**Windows prerequisites:** Docker Desktop running, Python 3.12, `uv`.

**Linux/WSL prerequisites:** Python 3.12, `uv`, and a working Docker CLI from the same shell (`docker info`). For WSL, enable Docker Desktop WSL integration or run native Docker inside WSL.

Run one demo from one environment. Avoid mixing Windows PowerShell commands with WSL/Linux commands in the same run because `.venv`, kubeconfig paths, and localhost routing can differ.

```powershell
# 1. Install the backend + worker dependencies used by the demo
uv sync --all-extras

# 2. Copy and edit env
cp .env.example .env
# Set APP_LLM_FAKE_MODE=false to use a real provider response.
# Then either set APP_OPENAI_API_KEY=... or switch APP_LLM_PROVIDER=ollama.

# 3. Start MinIO
.\scripts\up.ps1

# 4. Start the backend (hot-reload)
.\scripts\demo.ps1
```

Linux/WSL:

```bash
# 1. Install the backend + worker dependencies used by the demo
uv sync --all-extras

# 2. Copy and edit env
cp .env.example .env
# Set APP_LLM_FAKE_MODE=false to use a real provider response.
# Then either set APP_OPENAI_API_KEY=... or switch APP_LLM_PROVIDER=ollama.

# 3. Start MinIO
bash scripts/up.sh

# 4. Start the backend (hot-reload)
bash scripts/demo.sh
```

Open `http://localhost:8000`.
If the header shows `fake mode`, replies are synthetic until `APP_LLM_FAKE_MODE=false`.

Local teardown:

```powershell
.\scripts\down.ps1
```

```bash
bash scripts/down.sh
```

To switch provider, set `APP_LLM_PROVIDER` in `.env`:

```
APP_LLM_PROVIDER=ollama     # local, no API key needed
APP_LLM_PROVIDER=openai     # default; requires APP_OPENAI_API_KEY
APP_LLM_PROVIDER=kserve     # in-cluster; use with kserve-cpu profile
```

For real provider-backed replies, also set `APP_LLM_FAKE_MODE=false`.
For Ollama, start the local server and pull the model first:

```bash
ollama serve
ollama pull qwen2.5:0.5b
```

If Ollama runs on Windows while the backend runs in WSL, `localhost:11434` may not point to the Windows service from the Linux process. In that case, override `APP_OLLAMA_BASE_URL` with the reachable Windows host address.

---

## Quick start — KServe on kind

**Prerequisites:** Docker available from the active shell, Python 3.12, `uv`, `kind`, `kubectl`, and `bash`. Helm is optional; the KServe installer falls back to release manifests when Helm is not installed. For the kind smoke profile, allocate at least 4 CPUs and 8 GB RAM to Docker Desktop. For the full vLLM profile, allocate 12-16 GB RAM.

### Fast KServe smoke

Windows:

```powershell
# Install local dependencies used by tests, scripts, and local debugging
uv sync --all-extras

# Build images, create the kind cluster, deploy backend + observability
.\scripts\up.ps1 -Mode kind

# Install KServe CRDs/controller into the active kind context
bash ./deploy/kserve/install.sh

# Deploy a lightweight OpenAI-compatible predictor behind KServe
kubectl apply -f .\deploy\kserve\smoke-inferenceservice.yaml

# Switch the backend to call KServe, then run the e2e smoke test
kubectl wait inferenceservice/vllm --for=condition=Ready --timeout=300s -n default
kubectl set env deployment/k8s-llm-job-backend APP_LLM_PROVIDER=kserve APP_LLM_FAKE_MODE=false
kubectl rollout status deployment/k8s-llm-job-backend --timeout=120s
uv run --all-extras python .\scripts\e2e_kserve_smoke.py
```

Linux/WSL:

```bash
# Install local dependencies used by tests, scripts, and local debugging
uv sync --all-extras

# Build images, create the kind cluster, deploy backend + observability
bash scripts/up.sh --mode kind

# Install KServe CRDs/controller into the active kind context
bash ./deploy/kserve/install.sh

# Deploy a lightweight OpenAI-compatible predictor behind KServe
kubectl apply -f deploy/kserve/smoke-inferenceservice.yaml

# Switch the backend to call KServe, then run the e2e smoke test
kubectl wait inferenceservice/vllm --for=condition=Ready --timeout=300s -n default
kubectl set env deployment/k8s-llm-job-backend APP_LLM_PROVIDER=kserve APP_LLM_FAKE_MODE=false
kubectl rollout status deployment/k8s-llm-job-backend --timeout=120s
uv run --all-extras python scripts/e2e_kserve_smoke.py
```

The smoke predictor validates the same OpenAI-compatible contract used by chat and workers without pulling the multi-GB vLLM image. It exercises the backend, KServe routing, upload handling, Kubernetes worker Jobs, MinIO result storage, and chat context attachment.

### Full vLLM CPU profile

Windows:

```powershell
# Build images, create/reuse the kind cluster, install KServe,
# deploy vLLM, switch the backend to kserve, and start port-forwarding.
.\scripts\up.ps1 -Mode kind -WithKServe
```

Linux/WSL:

```bash
# Build images, create/reuse the kind cluster, install KServe,
# deploy vLLM, switch the backend to kserve, and start port-forwarding.
bash scripts/up.sh --mode kind --with-kserve
```

The first full vLLM run downloads a large serving image and model weights. On a clean machine this can take well over 10 minutes, and Docker Desktop should have 12-16 GB RAM allocated.

URLs after the kind profile is ready:

| Service | URL |
|---------|-----|
| Backend | http://localhost:8000 |
| MinIO console | http://localhost:9001 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 (admin/admin) |
| KServe/vLLM | http://localhost:8080/v1 (full `-WithKServe` profile only) |

`8080` is created by `kubectl port-forward`, not by the kind cluster host port mappings.

Tear down:

```powershell
.\scripts\down.ps1 -Mode kind
```

```bash
bash scripts/down.sh --mode kind
```

---

## Make targets

```
make demo           # local-fast: start backend (starts MinIO if needed)
make up             # local MinIO only
make kind-up        # full kind cluster
make kind-up-kserve # kind cluster + full KServe/vLLM profile
make kind-down      # delete kind cluster
make build-images   # build backend + both worker images
make lint           # ruff check
make typecheck      # pyright (strict)
make test           # pytest
make load-test      # send concurrent POSTs to /chat
```

On Windows, the default targets call PowerShell scripts. On Linux/WSL, they call Bash scripts. Explicit `*-ps` and `*-sh` targets are also available, for example `make up-ps` or `make up-sh`.

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
| `APP_LLM_FAKE_MODE` | `true` | `.env.example` defaults to fake replies for safety; set `false` to exercise the real provider |
| `APP_LLM_TIMEOUT_SECONDS` | `60` | Chat/summary provider timeout; increase for first local model warmup if needed |
| `APP_MINIO_CONNECT_TIMEOUT_SECONDS` / `APP_MINIO_READ_TIMEOUT_SECONDS` | `3` / `10` | Storage client timeouts for quick local failure feedback |
| `APP_GRAFANA_URL` | — | When set, a Grafana link appears in the UI header |

All settings use the `APP_` prefix and can be set in `.env` or as environment variables.

---

## Upload and job list flow

1. `POST /upload` — validates MIME type (PDF or CSV), enforces 10 MB limit, stores input in MinIO under `jobs/{id}/input/{filename}`.
2. Backend creates a job record in MinIO (`jobs/{id}/metadata.json`).
3. Depending on `APP_JOB_EXECUTION_MODE`:
   - **`local`** (default): worker logic runs in a background thread.
   - **`kubernetes`**: backend submits a `batch/v1 Job` using the `k8s-llm-job-backend` service account.
4. Worker reads input from MinIO, calls the LLM, writes `jobs/{id}/result.json`.
5. `GET /jobs` returns an HTML fragment of the 20 most recent jobs sorted by creation time. The UI polls this endpoint every 3 s and replaces the job list panel automatically.
6. Once a job shows `succeeded`, a "Discuss" button appears in its row. Clicking it calls `POST /chat/attach/{id}`, which injects a compact system message (filename, row/column counts or page count, LLM summary) into the conversation. A context chip above the chat input shows the active file; click × to detach.

## Chat

The chat panel supports multi-turn conversations. Full conversation history is stored as a JSON-encoded hidden form field in the browser; each POST carries it to the server, the server appends the new exchange, and the updated history is embedded in the returned HTML fragment. No server-side session state.

| Route | Action |
|-------|--------|
| `POST /chat` | Append user turn, call LLM, return updated panel |
| `POST /chat/attach/{job_id}` | Insert job context as system message, show filename chip |
| `POST /chat/detach` | Drop system message, remove chip |
| `POST /chat/clear` | Wipe conversation entirely |

Worker images use stable local tags: `k8s-llm-job-worker-pdf:local`, `k8s-llm-job-worker-tabular:local`.

---

## Observability

The backend exposes Prometheus metrics at `/metrics`:

| Metric | Type | Labels |
|--------|------|--------|
| `k8s_llm_chat_requests_total` | Counter | `provider`, `status` |
| `k8s_llm_chat_latency_seconds` | Histogram | `provider` |
| `k8s_llm_active_jobs` | Gauge | `worker_type` |
| `k8s_llm_job_completions_total` | Counter | `worker_type`, `status` |
| `k8s_llm_job_duration_seconds` | Histogram | `worker_type` |

The Grafana dashboard (`deploy/observability/grafana-dashboard.json`) visualises backend metrics, job metrics, container resource usage, and vLLM serving metrics such as request rate, token throughput, queue depth, and latency. Backend metrics are always present; vLLM panels show data when the full KServe/vLLM profile is running. The dashboard is provisioned automatically by `up.ps1 -Mode kind` and `scripts/up.sh --mode kind`.

---

## Security posture

- `k8s-llm-job-backend` ServiceAccount with a least-privilege Role: `batch/jobs` and `batch/jobs/status` (get/list/watch/create/delete as needed for submission and reconciliation), `pods` and `pods/log` (get/list/watch) — no cluster-wide permissions.
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
scripts/            PowerShell and Bash demo/up/down/load-test entry points
examples/           sample.pdf and sample.csv for demo validation
```

---

## Further reading

- [docs/design-notes.md](docs/design-notes.md) — KServe vs Triton, standard vs Knative, model lifecycle, multi-tenancy, GPU efficiency, RAG path
- [docs/benchmark.md](docs/benchmark.md) — local latency/throughput results
- [AGENTS.md](AGENTS.md) — toolchain conventions for future agent sessions
