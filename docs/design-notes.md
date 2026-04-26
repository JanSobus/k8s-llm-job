# Design Notes

Architecture and decision rationale for K8s LLM Job.

---

## Why KServe, and what role it plays here

The demo uses KServe in **standard (raw-deployment) mode** as the primary owned-inference path.
The provider model has three tiers:

| Provider | Role | When to use |
|----------|------|-------------|
| `openai` | External managed API | Fast iteration, reliable reviewer fallback |
| `ollama` | Local developer runtime | Offline development, no k8s needed |
| `kserve` | Platform-owned, autoscaled serving | Production-equivalent demo path |

KServe is **not** used here as a proxy to OpenAI or as a caching layer. Its value in this demo is identical to its value at CERN: providing a **Kubernetes-native lifecycle** for self-hosted models — versioned InferenceServices, rollout/rollback via `kubectl`, HPA-backed scaling, and a single `/v1/chat/completions`-compatible endpoint the rest of the stack doesn't need to know about.

---

## KServe standard mode vs Knative vs LLMInferenceService

**Standard (raw-deployment) mode** was chosen deliberately:

- Knative Serving adds scale-to-zero and traffic splitting but requires cert-manager, net-istio or kourier, and careful DNS configuration. On a kind cluster that's 3–4 extra moving parts with no functional benefit for the demo, and a known source of instability on CPU-only local clusters.
- `LLMInferenceService` (the newer KServe API for LLM-specific features like prefix caching and disaggregated prefill/decode) is in alpha as of KServe 0.13. It targets GPU multi-node deployments and adds complexity not justified by the model size used here.
- Raw-deployment mode is what most CERN workloads would use in practice for persistent, always-on inference services — it maps directly to a standard Deployment + HPA, which any platform operator can reason about without KServe-specific expertise.

For production CERN use, the path to Knative would be:
1. Install KNative with a supported ingress (Kourier or Istio).
2. Remove `serving.kserve.io/deploymentMode: RawDeployment` annotation from the InferenceService.
3. Configure domain suffix and DNS — CERN uses `*.cern.ch` internal routing.
4. Gain scale-to-zero for idle models and traffic-split rollouts (canary, blue-green).

---

## KServe vs Triton for this demo

Triton Inference Server is NVIDIA's production inference runtime — excellent for ensemble pipelines, multi-backend model serving (TensorRT, ONNX, TF, PyTorch), and GPU batching. It's the right choice when:
- You own the model format pipeline (TensorRT plans, ONNX export).
- You need dynamic batching across multiple model backends in one server.
- Your models are deployed on dedicated GPU nodes with tight latency SLAs.

KServe is the right choice here because:
- The demo serves a **chat-completion contract** (`/v1/chat/completions`). vLLM implements this natively; Triton requires a separate HTTP frontend (triton-vllm-backend or custom Python model).
- KServe's **model lifecycle API** (InferenceService CRD) is richer than Triton's model repository for versioning, rollout, and HPA integration.
- The CERN JD asks for platform lifecycle thinking, not GPU kernel optimisation. KServe's Kubernetes-native approach better demonstrates that.

For CERN's actual GPU inference workloads, the two are complementary: KServe as the lifecycle/serving layer, Triton (or vLLM) as the runtime backend.

---

## Model lifecycle: versioning, rollout/rollback, promotion

The KServe InferenceService supports versioned rollout without cluster downtime:

```yaml
# promote a new model version with traffic split (Knative mode)
spec:
  predictor:
    canaryTrafficPercent: 10
    model:
      storageUri: "hf://Qwen/Qwen2.5-3B-Instruct"  # new version
```

In raw-deployment mode, versioning is done via InferenceService name or namespace — a blue/green swap by updating the storageUri and watching `kubectl rollout status`.

**Promotion criteria** used in this demo:
1. p95 chat latency < 5 s under 10 concurrent requests (captured in `docs/benchmark.md`).
2. Zero error rate from `/metrics` over a 5-minute soak window.
3. Model outputs validated against a fixed prompt set in `examples/`.

**Rollback**: `kubectl rollout undo deployment/<predictor-name>` in raw-deployment mode, or revert the InferenceService manifest and `kubectl apply`.

---

## Secure multi-tenant platform design

The demo implements the first layer of multi-tenancy. A production CERN deployment would extend each layer:

### What the demo does

| Control | Implementation |
|---------|---------------|
| Service accounts | `k8s-llm-job-backend` SA, `k8s-llm-job-backend-jobs` Role (batch/jobs, pods/log only) |
| Least-privilege RBAC | Role scoped to `default` namespace; no cluster-wide permissions |
| Resource limits | CPU/memory requests and limits on backend, workers, MinIO, Prometheus |
| Secrets | MinIO credentials in a Kubernetes Secret, not in ConfigMap or env literals |
| Job TTL | `ttlSecondsAfterFinished: 600` cleans up worker pods automatically |
| MIME allowlist | Upload endpoint rejects anything outside `application/pdf`, `text/csv` |
| Object key sanitisation | `safe_filename()` strips path traversal and non-printable characters |

### Production CERN extensions

**Namespace isolation**: one namespace per team or experiment. Each InferenceService, job quota, and network policy is scoped to that namespace. An `InferenceServiceNamespaceQuota` (KServe 0.14+) or a Kueue `ClusterQueue` caps GPU/CPU allocation per team.

**Network policy**: restrict backend→MinIO, worker→MinIO, backend→KServe predictor. Block all other pod-to-pod traffic by default. CERN's SDN (OpenStack Neutron) enforces this at the hypervisor level on bare-metal k8s.

**Secrets management**: replace Kubernetes Secret literals with Vault sidecar injection (Vault Agent Injector) or External Secrets Operator syncing from CERN's HashiCorp Vault. Avoids storing model API keys or S3 credentials in etcd.

**Fair-share scheduling with HTCondor integration**: CERN uses HTCondor for HEP batch alongside Kubernetes. A bridge (e.g., `condor-k8s-broker` or CERN's custom pilot framework) submits k8s Jobs to a shared pool with fair-share priority. The worker Job contract in this demo (read input from MinIO, write result to MinIO, exit 0) is already compatible with this pattern — no changes to worker code needed.

---

## Future RAG path (without implementing a vector store)

The current architecture already anticipates RAG without a vector store component:

```
Upload PDF → worker-pdf extracts text + metadata → stores in MinIO
Chat agent → queries MinIO for recent extractions → passes context to LLM
```

To add a proper RAG path:
1. Add a `worker-embed` type that calls an embedding model (e.g., `bge-m3` on KServe) and writes vectors to a pgvector or Qdrant store in the cluster.
2. Add a retrieval tool to the chat agent: `retrieve_relevant_chunks(query, top_k=5)`.
3. The LLM provider contract is unchanged — retrieved chunks go into the system prompt or a user message before the question.

The single-contract LLM client (`/v1/chat/completions`) means the embedding and generation models can both run on KServe, sharing the same autoscaling and lifecycle machinery.

---

## GPU efficiency path

The demo runs CPU-only (Qwen2.5-0.5B-Instruct, `--dtype float32`, `--device cpu`). The path to GPU production is:

**Single GPU (A100 40 GB)**
- Remove `--dtype float32` and `--device cpu` from `vllm-runtime.yaml`.
- Add `nvidia.com/gpu: "1"` to resource limits.
- Switch model to `Qwen/Qwen2.5-7B-Instruct` or `meta-llama/Llama-3.1-8B-Instruct`.
- Expected throughput: ~2000 tokens/s output, p50 latency ~200 ms first token.

**Multi-GPU tensor parallelism**
- Add `--tensor-parallel-size 2` (or 4/8) to vLLM args.
- Request matching GPU count in resource limits.
- KServe propagates resource requests to the underlying Deployment.

**Continuous batching and KV cache**
- vLLM's PagedAttention is on by default. `--max-num-seqs` controls batch size.
- `--gpu-memory-utilization 0.90` (default) reserves 10% for KV cache fragmentation.
- For very long contexts, `--enable-chunked-prefill` reduces first-token latency variability.

**Token throughput metric**
- vLLM exposes `/metrics` on the same port — Prometheus can scrape `vllm:generation_tokens_total` directly.
- Add a scrape target in `prometheus.yaml` pointing at the KServe predictor service.

**Data parallelism (multiple replicas)**
- Handled by KServe HPA (`minReplicas`/`maxReplicas`/`scaleTarget`).
- Each replica is an independent vLLM process. For shared KV cache across replicas, vLLM's `--enable-prefix-caching` + `--prefix-caching-backend redis` can be used with a shared Redis sidecar (experimental as of vLLM 0.6).
