#!/usr/bin/env bash
# Install KServe (standard mode, no Knative) into the active kubectl context.
# Tested against kind cluster created by deploy/kind/cluster.yaml.
# Safe to run from any cwd; resolves manifest paths relative to itself.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

KSERVE_VERSION="${KSERVE_VERSION:-0.13.1}"
CERT_MANAGER_VERSION="${CERT_MANAGER_VERSION:-1.16.2}"

echo "==> Installing cert-manager ${CERT_MANAGER_VERSION}..."
kubectl apply -f \
  "https://github.com/cert-manager/cert-manager/releases/download/v${CERT_MANAGER_VERSION}/cert-manager.yaml"
kubectl rollout status deployment/cert-manager         -n cert-manager --timeout=120s
kubectl rollout status deployment/cert-manager-webhook -n cert-manager --timeout=120s

echo "==> Installing KServe ${KSERVE_VERSION} (standard / raw-deployment mode)..."
# Standard mode uses raw Deployments instead of Knative Serving — simpler and
# CPU-friendly for the local demo.  Switch KSERVE_INGRESS_SERVICE_TYPE to
# NodePort so the kind NodePort mapping (31080→8080) works without MetalLB.
helm repo add kserve https://kserve.github.io/helm-charts/ 2>/dev/null || true
helm repo update kserve

helm upgrade --install kserve kserve/kserve \
  --namespace kserve \
  --create-namespace \
  --version "${KSERVE_VERSION}" \
  --set kserve.controller.image.tag="${KSERVE_VERSION}" \
  --set kserve.servingruntime.defaultRuntime="vllm-runtime" \
  --set kserve.ingress.ingressClassName="none" \
  --timeout 5m \
  --wait

echo "==> KServe installed. Applying vLLM ServingRuntime..."
kubectl apply -f "${SCRIPT_DIR}/vllm-runtime.yaml"

echo "==> Done."
echo "    Deploy an InferenceService with:"
echo "    kubectl apply -f ${SCRIPT_DIR}/inferenceservice.yaml"
