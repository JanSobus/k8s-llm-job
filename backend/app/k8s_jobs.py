from __future__ import annotations

import re
import warnings

from kubernetes_asyncio import client, config  # type: ignore[import-untyped]

from backend.app.config import JobExecutionMode, Settings
from backend.app.jobs import get_job_store
from backend.app.routing import UploadRoute, WorkerType
from backend.app.storage import StorageError, get_storage


def _k8s_ident(name: str) -> str:
    """Subdomain-safe identifier (lowercase, hyphens) max 63 chars for Job names."""
    base = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    if len(base) > 63:
        return base[:63].strip("-")
    return base or "job"


def _v1_env(name: str, value: str) -> client.V1EnvVar:
    return client.V1EnvVar(name=name, value=value)


def build_worker_job(job_id: str, route: UploadRoute, app_settings: Settings) -> client.V1Job:
    image = (
        app_settings.worker_image_tabular
        if route.worker_type is WorkerType.TABULAR
        else app_settings.worker_image_pdf
    )
    command = "python"
    args = [
        "-m",
        "workers.tabular.main" if route.worker_type is WorkerType.TABULAR else "workers.pdf.main",
    ]
    name = _k8s_ident(f"{app_settings.job_name_prefix}{job_id}")
    env = _app_env_list(app_settings) + [client.V1EnvVar(name="JOB_ID", value=job_id)]
    resources = client.V1ResourceRequirements(
        requests={
            "cpu": app_settings.worker_cpu_request,
            "memory": app_settings.worker_memory_request,
        },
        limits={
            "cpu": app_settings.worker_cpu_limit,
            "memory": app_settings.worker_memory_limit,
        },
    )
    container = client.V1Container(
        name="worker",
        image=image,
        image_pull_policy="IfNotPresent",
        command=[command],
        args=args,
        env=env,
        resources=resources,
    )
    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(
            labels={
                "app": "cern-ml-demo",
                "job-template": route.job_template_name,
                "job-id": job_id,
            },
        ),
        spec=client.V1PodSpec(
            restart_policy="Never",
            containers=[container],
        ),
    )
    return client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(
            name=name,
            labels={
                "app": "cern-ml-demo",
                "job-template": route.job_template_name,
                "job-id": job_id,
            },
        ),
        spec=client.V1JobSpec(
            ttl_seconds_after_finished=app_settings.job_ttl_seconds_after_finished,
            backoff_limit=0,
            template=template,
        ),
    )


def _app_env_list(app_settings: Settings) -> list[client.V1EnvVar]:
    """Mirror critical APP_ settings the worker process needs in-cluster."""
    items: list[client.V1EnvVar] = [
        _v1_env("APP_LLM_PROVIDER", app_settings.llm_provider.value),
        _v1_env("APP_LLM_FAKE_MODE", str(app_settings.llm_fake_mode).lower()),
        _v1_env("APP_OPENAI_BASE_URL", app_settings.openai_base_url),
        _v1_env("APP_OPENAI_MODEL", app_settings.openai_model),
        _v1_env("APP_OLLAMA_BASE_URL", app_settings.ollama_base_url),
        _v1_env("APP_OLLAMA_MODEL", app_settings.ollama_model),
        _v1_env("APP_KSERVE_BASE_URL", app_settings.kserve_base_url),
        _v1_env("APP_KSERVE_MODEL", app_settings.kserve_model),
        _v1_env("APP_MINIO_ENDPOINT", app_settings.minio_endpoint),
        _v1_env("APP_MINIO_CONSOLE_URL", app_settings.minio_console_url),
        _v1_env("APP_MINIO_ACCESS_KEY", app_settings.minio_access_key.get_secret_value()),
        _v1_env("APP_MINIO_SECRET_KEY", app_settings.minio_secret_key.get_secret_value()),
        _v1_env("APP_MINIO_BUCKET", app_settings.minio_bucket),
        _v1_env("APP_MINIO_SECURE", str(app_settings.minio_secure).lower()),
        _v1_env("APP_JOB_EXECUTION_MODE", JobExecutionMode.LOCAL.value),
    ]
    if app_settings.openai_api_key is not None:
        items.append(
            _v1_env("APP_OPENAI_API_KEY", app_settings.openai_api_key.get_secret_value())
        )
    return items


async def create_kubernetes_worker_job(
    job_id: str,
    route: UploadRoute,
    app_settings: Settings,
) -> client.V1Job:
    if app_settings.job_execution_mode is not JobExecutionMode.KUBERNETES:
        msg = "create_kubernetes_worker_job only applies when job_execution_mode=kubernetes"
        raise ValueError(msg)
    job_body = build_worker_job(job_id, route, app_settings)
    if app_settings.backend_kubernetes_in_cluster:
        config.load_incluster_config()  # type: ignore[no-untyped-call]
    else:
        if app_settings.kubeconfig_path:
            with warnings.catch_warnings():
                await config.load_kube_config(  # type: ignore[no-untyped-call, misc]
                    config_file=app_settings.kubeconfig_path,
                )
        else:
            with warnings.catch_warnings():
                await config.load_kube_config()  # type: ignore[no-untyped-call, misc]

    batch = client.BatchV1Api()
    out = await batch.create_namespaced_job(
        namespace=app_settings.kubernetes_namespace,
        body=job_body,
    )
    return out


def on_k8s_submission_error(job_id: str, exc: BaseException) -> None:
    try:
        storage = get_storage()
        store = get_job_store(storage)
        store.mark_failed(job_id, message=f"Kubernetes job submission failed: {exc}")
    except StorageError:
        return
