#!/usr/bin/env bash
# Install KServe (standard mode, no Knative) into the active kubectl context.
# Tested against kind cluster created by deploy/kind/cluster.yaml.
# Safe to run from any cwd; resolves manifest paths relative to itself.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

KSERVE_VERSION="${KSERVE_VERSION:-0.13.1}"
CERT_MANAGER_VERSION="${CERT_MANAGER_VERSION:-1.16.2}"
KUBE_RBAC_PROXY_IMAGE="${KUBE_RBAC_PROXY_IMAGE:-registry.k8s.io/kubebuilder/kube-rbac-proxy:v0.15.0}"

echo "==> Installing cert-manager ${CERT_MANAGER_VERSION}..."
kubectl apply -f \
  "https://github.com/cert-manager/cert-manager/releases/download/v${CERT_MANAGER_VERSION}/cert-manager.yaml"
kubectl rollout status deployment/cert-manager         -n cert-manager --timeout=120s
kubectl rollout status deployment/cert-manager-webhook -n cert-manager --timeout=120s

echo "==> Installing KServe ${KSERVE_VERSION} (standard / raw-deployment mode)..."
# Standard mode uses raw Deployments instead of Knative Serving — simpler and
# CPU-friendly for the local demo. External predictor access is handled by a
# `kubectl port-forward` step in `scripts/up.ps1`, not by a NodePort service.
if command -v helm >/dev/null 2>&1; then
  helm repo add kserve https://kserve.github.io/helm-charts/ 2>/dev/null || true
  helm repo update kserve

  helm upgrade --install kserve-crd kserve/kserve-crd \
    --namespace kserve \
    --create-namespace \
    --version "${KSERVE_VERSION}" \
    --timeout 5m \
    --wait

  kubectl wait --for=condition=Established \
    crd/servingruntimes.serving.kserve.io \
    crd/inferenceservices.serving.kserve.io \
    --timeout=120s

  helm upgrade --install kserve kserve/kserve \
    --namespace kserve \
    --create-namespace \
    --version "${KSERVE_VERSION}" \
    --set kserve.controller.image.tag="${KSERVE_VERSION}" \
    --set kserve.servingruntime.defaultRuntime="vllm-runtime" \
    --set kserve.ingress.ingressClassName="none" \
    --timeout 5m \
    --wait
else
  echo "==> Helm not found; installing KServe release manifests directly..."
  kubectl apply -f "https://github.com/kserve/kserve/releases/download/v${KSERVE_VERSION}/kserve.yaml"
  kubectl wait --for=condition=Established \
    crd/servingruntimes.serving.kserve.io \
    crd/inferenceservices.serving.kserve.io \
    --timeout=120s
fi

# KServe v0.13.x manifests reference the removed gcr.io kubebuilder proxy image.
# Swap to the Kubernetes mirror so fresh local clusters can still start.
kubectl set image deployment/kserve-controller-manager \
  -n kserve \
  "kube-rbac-proxy=${KUBE_RBAC_PROXY_IMAGE}" || true
kubectl rollout status deployment/kserve-controller-manager -n kserve --timeout=300s

echo "==> Installing built-in KServe cluster resources..."
kubectl apply -f "https://github.com/kserve/kserve/releases/download/v${KSERVE_VERSION}/kserve-cluster-resources.yaml"

echo "==> KServe installed. Applying vLLM ServingRuntime..."
kubectl apply -f "${SCRIPT_DIR}/vllm-runtime.yaml"

echo "==> Done."
echo "    Deploy an InferenceService with:"
echo "    kubectl apply -f ${SCRIPT_DIR}/inferenceservice.yaml"
