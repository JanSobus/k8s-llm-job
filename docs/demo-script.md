# Demo Script — Reviewer Walkthrough

A guided walkthrough of the K8s LLM Job for a technical reviewer.
Estimated time: 10–15 minutes for the local-fast path; 25–30 minutes with the kserve-cpu cluster.

---

## 1. Repository overview (2 min)

```
README.md           one-command start, architecture overview, provider model
docs/architecture.mmd  source architecture diagram
docs/design-notes.md  architecture rationale (KServe, multi-tenancy, GPU path)
backend/app/        FastAPI application — config, llm, chat, uploads, metrics
workers/            PDF and tabular batch workers sharing the LLM contract
deploy/             all Kubernetes manifests, KServe, observability
.github/workflows/  CI: lint + typecheck + pytest + image builds
```

Key thing to notice: **one LLM contract** (`/v1/chat/completions`) used by the interactive chat endpoint *and* the batch workers. Provider switches without touching worker code.

---

## 2. Start local-fast profile (2 min)

Windows:

```powershell
uv sync --all-extras
cp .env.example .env
# Set APP_LLM_FAKE_MODE=false in .env for real provider responses.
# Then set APP_OPENAI_API_KEY=sk-...  (or use APP_LLM_PROVIDER=ollama)
.\scripts\up.ps1        # starts MinIO container
.\scripts\demo.ps1      # starts FastAPI with hot-reload
```

Linux/WSL:

```bash
uv sync --all-extras
cp .env.example .env
# Set APP_LLM_FAKE_MODE=false in .env for real provider responses.
# Then set APP_OPENAI_API_KEY=sk-...  (or use APP_LLM_PROVIDER=ollama)
bash scripts/up.sh        # starts MinIO container
bash scripts/demo.sh      # starts FastAPI with hot-reload
```

For WSL, run all commands from the WSL/Linux shell and make sure `docker info` works there. Avoid mixing Windows and WSL commands during one walkthrough because `.venv`, kubeconfig paths, and localhost routing can differ.

Open `http://localhost:8000`.

**What to show:**
- The UI loads with a two-column layout: **Upload + Jobs** on the left, **Chat** on the right. Provider and model name are in the header.
- If the header still says **fake mode**, flip `APP_LLM_FAKE_MODE=false` before the walkthrough so the replies come from the selected provider.
- Upload `examples/sample.csv` — the job row appears in the Jobs panel immediately. The list auto-refreshes every 3 s; status progresses `queued → running → succeeded`.
- Upload `examples/sample.pdf` — a second row appears, showing a different worker-type badge (`pdf` vs `tabular`).
- Once a job shows ✓ succeeded, click **Discuss** in its row. A yellow context chip appears above the chat input ("Discussing: sample.csv"). The job's column names, row count, and LLM summary are silently injected as a system message.
- Send a question about the data (e.g. "How many rows?", "What columns are numeric?"). The assistant's reply references the injected context.
- Send a follow-up without repeating the file details — the second response continues the conversation, demonstrating multi-turn memory.
- Click the **×** on the chip to detach the context. Click **Clear conversation** to start fresh.
- Open `http://localhost:8000/metrics` — Prometheus text format showing `k8s_llm_chat_requests_total`, `k8s_llm_chat_latency_seconds`, `k8s_llm_active_jobs`, etc.

---

## 3. Provider switch (1 min)

In `.env`:

```
APP_LLM_PROVIDER=ollama
APP_LLM_FAKE_MODE=false
APP_OLLAMA_MODEL=qwen2.5:0.5b
```

Before restarting the backend, make sure Ollama is running and the model is present:

```bash
ollama serve
ollama pull qwen2.5:0.5b
```

If Ollama runs on Windows while the backend runs in WSL, set `APP_OLLAMA_BASE_URL` to a host address reachable from WSL instead of the default `http://localhost:11434/v1`.

Restart the backend. Send a chat message — the label in the response changes to `ollama / qwen2.5:0.5b`. No code changes, no worker changes.

---

## 4. kserve-cpu cluster (10 min, optional)

Windows:

```powershell
.\scripts\up.ps1 -Mode kind -WithKServe
# Takes 5–10 min; downloads Qwen2.5-0.5B-Instruct on first run
```

Linux/WSL:

```bash
bash scripts/up.sh --mode kind --with-kserve
# Takes 5-10+ min; downloads Qwen2.5-0.5B-Instruct on first run
```

Allocate 12-16 GB RAM to Docker Desktop for the full KServe path. The vLLM CPU predictor alone can use up to 8 GiB, before MinIO, backend, Prometheus, Grafana, and Kubernetes overhead.

After the cluster is ready:

```
http://localhost:8000   backend (running in kind)
http://localhost:9001   MinIO console
http://localhost:9090   Prometheus
http://localhost:3000   Grafana (admin/admin)
http://localhost:8080/v1   vLLM predictor (started by port-forward)
```

`8080` is created by `kubectl port-forward`; it is not a kind host port mapping.

**What to show:**
- Click the **Grafana** link in the UI header (top-right) — opens `http://localhost:3000` in a new tab.
- Grafana → K8s LLM Job dashboard:
  - Chat request rate and latency percentiles (send a few messages).
  - Active jobs gauge (upload a file and watch it increment then drop).
  - Job duration histogram after the worker completes.
- Prometheus → query `k8s_llm_chat_latency_seconds_bucket` directly — shows bucketed histogram data.
- `kubectl get inferenceservice` — shows the KServe InferenceService and its `Ready` condition.
- `kubectl get hpa` — shows the HPA targeting the vLLM predictor deployment.
- The backend is already switched to `APP_LLM_PROVIDER=kserve` by `up.ps1 -WithKServe`, so the chat panel should show the `kserve` provider without any manual ConfigMap edits.

---

## 5. Security and RBAC (1 min)

```bash
kubectl get serviceaccount k8s-llm-job-backend -n default
kubectl describe role k8s-llm-job-backend-jobs -n default
```

Show that the backend SA is namespace-scoped and limited to `batch/jobs`, `pods`, and `pods/log` within `default`. It cannot list Secrets, create Deployments, or access other namespaces.

---

## 6. Design discussion points

Likely reviewer questions and where the answers live:

| Question | Pointer |
|----------|---------|
| Why KServe and not Triton? | [docs/design-notes.md — KServe vs Triton](design-notes.md#kserve-vs-triton-for-this-demo) |
| Why standard mode and not Knative? | [docs/design-notes.md — standard vs Knative](design-notes.md#kserve-standard-mode-vs-knative-vs-llminferenceservice) |
| How would this scale at CERN (HTCondor, fair-share)? | [docs/design-notes.md — multi-tenancy](design-notes.md#secure-multi-tenant-platform-design) |
| What's the GPU path? | [docs/design-notes.md — GPU efficiency](design-notes.md#gpu-efficiency-path) |
| How would RAG work? | [docs/design-notes.md — RAG path](design-notes.md#future-rag-path-without-implementing-a-vector-store) |
| Benchmark numbers? | [docs/benchmark.md](benchmark.md) |

---

## 7. Teardown

Windows:

```powershell
.\scripts\down.ps1              # stops local MinIO
.\scripts\down.ps1 -Mode kind   # deletes kind cluster
```

Linux/WSL:

```bash
bash scripts/down.sh              # stops local MinIO
bash scripts/down.sh --mode kind  # deletes kind cluster
```
