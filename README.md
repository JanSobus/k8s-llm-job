# CERN ML Demo

Portfolio demo for the CERN Machine Learning Engineer role. The project will show a small user-facing FastAPI app backed by OpenAI-compatible LLM providers, Kubernetes Jobs for batch uploads, local MinIO storage, and a KServe/vLLM expansion path for owned scaled inference.

## Current Status

- uv-managed Python 3.12, FastAPI + HTMX UI, OpenAI-compatible LLM providers, local MinIO.
- **Workers**: after upload, PDF and CSV jobs run in **local** mode (background thread) or, when configured, as **Kubernetes Batch Jobs** that use the same MinIO contract.
- `GET /jobs/{id}` and `GET /jobs/{id}/fragment` expose status; results are written to `jobs/{id}/result.json`.

## Run Locally

Start local MinIO first:

```powershell
.\scripts\up.ps1
```

Then start the FastAPI app:

```powershell
.\scripts\demo.ps1
```

Then open `http://localhost:8000`.

## Provider Model

- `openai`: managed provider for fast iteration and reliable fallback.
- `ollama`: lightweight local developer provider.
- `kserve`: future owned/scaled inference path using self-hosted vLLM.

KServe is not used to proxy OpenAI in the core architecture. MinIO is planned as a local S3-compatible service for upload and result storage; it does not require an external S3 account.

## Upload Flow

- MinIO runs locally through Docker on `http://localhost:9000`.
- The MinIO console is available at `http://localhost:9001`.
- Demo credentials are `minioadmin` / `minioadmin`.
- The app creates the `cern-ml-demo` bucket on first storage use.
- Uploads are stored under `jobs/{job_id}/input/{filename}`.
- Job metadata is stored under `jobs/{job_id}/metadata.json`.
- Worker output is stored under `jobs/{job_id}/result.json` (JSON summary + optional LLM text).

Set `APP_JOB_EXECUTION_MODE=local` (default) to run workers in a thread after each upload, or `kubernetes` to let the API create a Batch Job (requires cluster access; see [deploy/app/backend-rbac.yaml](deploy/app/backend-rbac.yaml) and the `workers/*/Dockerfile` image tags in [AGENTS.md](AGENTS.md) — use `cern-ml-demo-worker-pdf:local` and `cern-ml-demo-worker-tabular:local`).

### Build worker images (for Kubernetes)

From the repository root:

```powershell
docker build -f workers/pdf/Dockerfile -t cern-ml-demo-worker-pdf:local .
docker build -f workers/tabular/Dockerfile -t cern-ml-demo-worker-tabular:local .
```
