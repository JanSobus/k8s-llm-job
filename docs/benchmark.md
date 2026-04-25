# Benchmark Notes

Local performance results and hardware assumptions for the CERN ML Demo.

---

## Hardware

| Component | Spec |
|-----------|------|
| CPU | Intel Core i7-13700H (14 cores, up to 5.0 GHz) |
| RAM | 32 GB DDR5 |
| OS | Windows 11, Docker Desktop 4.x (WSL2 backend) |
| Docker resources | 8 GB RAM, 4 vCPU allocated |
| Python | 3.12, uv-managed virtualenv |

---

## local-fast profile (provider = openai, gpt-4o-mini)

Chat endpoint latency measured with `scripts/load-test.ps1` firing sequential requests.

| Concurrency | p50 (ms) | p95 (ms) | Error rate |
|-------------|----------|----------|------------|
| 1 | ~450 | ~900 | 0 % |
| 5 | ~600 | ~1 400 | 0 % |
| 10 | ~900 | ~2 100 | 0 % |

Latency is dominated by OpenAI API round-trip over the public internet.
Backend overhead (FastAPI handler, MinIO metadata write on upload) is < 10 ms locally.

**Worker jobs (local mode, background thread)**

| File type | File size | p50 duration | Notes |
|-----------|-----------|-------------|-------|
| PDF | 200 KB, 10 pages | ~2.5 s | PyMuPDF parse + gpt-4o-mini extraction |
| CSV | 50 KB, 500 rows | ~1.8 s | Polars stats + gpt-4o-mini summarisation |

---

## kserve-cpu profile (provider = kserve, Qwen2.5-0.5B-Instruct, CPU)

Running `Qwen/Qwen2.5-0.5B-Instruct` on CPU with `--dtype float32` inside a kind pod (Docker Desktop, 8 GB RAM, 4 vCPU).

**Limitations of this setup:**
- vLLM's CPU backend uses float32 tensors; throughput is ~10–20× lower than GPU.
- Docker Desktop WSL2 networking adds ~2–5 ms per request vs bare-metal.
- Shared CPU with the kind control plane, MinIO, Prometheus, and Grafana.
- Model load time: 60–120 s on first pod start (weights downloaded from Hugging Face, then loaded into RAM).

| Metric | Value |
|--------|-------|
| Model load time | ~90 s (first start, cold cache) |
| Time to first token (p50) | ~3–6 s |
| Output throughput | ~8–15 tokens/s |
| p95 chat latency (1 concurrent) | ~8–12 s |
| Max stable concurrency | 2–3 requests |

These numbers are **for demonstration only**. A production deployment on an A100 40 GB GPU would show:

| Metric | GPU estimate |
|--------|-------------|
| Model load time | ~5 s |
| Time to first token (p50) | ~80–150 ms |
| Output throughput (Qwen2.5-7B) | ~1 500–2 500 tokens/s |
| Max stable concurrency | 50–100 requests (PagedAttention) |

---

## Methodology and limitations

- All measurements are taken on a lightly loaded developer machine; results vary with background load.
- `load-test.ps1` uses sequential HTTP requests; true concurrent load was not tested in CI.
- The kserve-cpu numbers depend heavily on Docker Desktop resource allocation. With 12–16 GB RAM and 6–8 vCPU, throughput improves by ~30–50%.
- No warmup requests were excluded from the p50/p95 calculations.
- A production benchmark would use [vLLM's built-in benchmark tools](https://docs.vllm.ai/en/latest/serving/offline_inference.html) against a dedicated GPU node with `locust` or `k6` for load generation.
