# Demo Script — Reviewer Walkthrough

A guided walkthrough of the CERN ML Demo for a technical reviewer.
Estimated time: 10–15 minutes for the local-fast path; 25–30 minutes with the kserve-cpu cluster.

---

## 1. Repository overview (2 min)

```
README.md           one-command start, architecture diagram, provider model
docs/design-notes.md  architecture rationale (KServe, multi-tenancy, GPU path)
backend/app/        FastAPI application — config, llm, chat, uploads, metrics
workers/            PDF and tabular batch workers sharing the LLM contract
deploy/             all Kubernetes manifests, KServe, observability
.github/workflows/  CI: lint + typecheck + pytest + image builds
```

Key thing to notice: **one LLM contract** (`/v1/chat/completions`) used by the interactive chat endpoint *and* the batch workers. Provider switches without touching worker code.

---

## 2. Start local-fast profile (2 min)

```powershell
cp .env.example .env
# Set APP_OPENAI_API_KEY=sk-... in .env  (or use APP_LLM_PROVIDER=ollama)
.\scripts\up.ps1        # starts MinIO container
.\scripts\demo.ps1      # starts FastAPI with hot-reload
```

Open `http://localhost:8000`.

**What to show:**
- The UI loads — provider and model name displayed in the header.
- Send a chat message. Response returns with the provider/model label (e.g. `openai / gpt-4o-mini`).
- Upload `examples/sample.pdf` — the job card appears immediately and polls status every 2 s.
- Upload `examples/sample.csv` — a second card appears, different worker type.
- Once both jobs succeed, the result preview appears inline. Click "View full result" to see the JSON extraction.
- Open `http://localhost:8000/metrics` — Prometheus text format showing `cern_ml_chat_requests_total`, `cern_ml_chat_latency_seconds`, `cern_ml_active_jobs`, etc.

---

## 3. Provider switch (1 min)

In `.env`:

```
APP_LLM_PROVIDER=ollama
APP_OLLAMA_MODEL=qwen2.5:0.5b
```

Restart the backend. Send a chat message — the label in the response changes to `ollama / qwen2.5:0.5b`. No code changes, no worker changes.

---

## 4. kserve-cpu cluster (10 min, optional)

```powershell
.\scripts\up.ps1 -Mode kind -WithKServe
# Takes 5–10 min; downloads Qwen2.5-0.5B-Instruct on first run
```

After the cluster is ready:

```
http://localhost:8000   backend (running in kind)
http://localhost:9001   MinIO console
http://localhost:9090   Prometheus
http://localhost:3000   Grafana (admin/admin)
```

**What to show:**
- Grafana → CERN ML Demo dashboard:
  - Chat request rate and latency percentiles (send a few messages).
  - Active jobs gauge (upload a file and watch it increment then drop).
  - Job duration histogram after the worker completes.
- Prometheus → query `cern_ml_chat_latency_seconds_bucket` directly — shows bucketed histogram data.
- `kubectl get inferenceservice` — shows the KServe InferenceService and its `Ready` condition.
- `kubectl get hpa` — shows the HPA targeting the vLLM predictor deployment.
- Set `APP_LLM_PROVIDER=kserve` in the backend ConfigMap and redeploy — chat now routes through the in-cluster vLLM endpoint.

---

## 5. Security and RBAC (1 min)

```powershell
kubectl get serviceaccount cern-ml-demo-backend -n default
kubectl describe role cern-ml-demo-backend-jobs -n default
```

Show that the backend SA has exactly two permissions: `batch/jobs` and `pods/log` within `default`. It cannot list Secrets, create Deployments, or access other namespaces.

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

```powershell
.\scripts\down.ps1              # stops local MinIO
.\scripts\down.ps1 -Mode kind   # deletes kind cluster
```
