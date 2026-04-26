from __future__ import annotations

import asyncio
import re
import warnings
from time import monotonic
from typing import Any, cast

from kubernetes_asyncio import client, config  # type: ignore[import-untyped]

from backend.app.config import JobExecutionMode, Settings
from backend.app.jobs import JobStatus, get_job_store
from backend.app.metrics import note_job_terminal
from backend.app.routing import UploadRoute, WorkerType
from backend.app.storage import StorageError, get_storage

_FAILED_POD_REASONS = {
    "CrashLoopBackOff",
    "CreateContainerConfigError",
    "CreateContainerError",
    "ErrImagePull",
    "ImagePullBackOff",
    "InvalidImageName",
    "RunContainerError",
}


def _k8s_ident(name: str) -> str:
    """Subdomain-safe identifier (lowercase, hyphens) max 63 chars for Job names."""
    base = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    if len(base) > 63:
        return base[:63].strip("-")
    return base or "job"


def _v1_env(name: str, value: str) -> client.V1EnvVar:
    return client.V1EnvVar(name=name, value=value)


async def _load_kubernetes_config(app_settings: Settings) -> None:
    if app_settings.backend_kubernetes_in_cluster:
        config.load_incluster_config()  # type: ignore[no-untyped-call]
        return

    with warnings.catch_warnings():
        if app_settings.kubeconfig_path:
            await config.load_kube_config(  # type: ignore[no-untyped-call, misc]
                config_file=app_settings.kubeconfig_path,
            )
        else:
            await config.load_kube_config()  # type: ignore[no-untyped-call, misc]


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
                "app": "k8s-llm-job",
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
                "app": "k8s-llm-job",
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
    await _load_kubernetes_config(app_settings)
    batch = client.BatchV1Api()
    out = await batch.create_namespaced_job(
        namespace=app_settings.kubernetes_namespace,
        body=job_body,
    )
    return out


async def submit_and_reconcile_kubernetes_job(
    job_id: str,
    route: UploadRoute,
    app_settings: Settings,
) -> None:
    created = await create_kubernetes_worker_job(job_id, route, app_settings)
    job_name = _job_name_from_response(created, app_settings, job_id)
    store = get_job_store(get_storage())
    await asyncio.to_thread(
        store.update_job,
        job_id,
        status=JobStatus.QUEUED.value,
        message=f"Kubernetes job {job_name} submitted.",
    )
    await reconcile_kubernetes_job(job_id, job_name, app_settings)


async def reconcile_kubernetes_job(
    job_id: str,
    job_name: str,
    app_settings: Settings,
) -> None:
    await _load_kubernetes_config(app_settings)
    store = get_job_store(get_storage())
    batch = client.BatchV1Api()
    core = client.CoreV1Api()
    deadline = monotonic() + app_settings.worker_poll_timeout_seconds
    success_grace_deadline: float | None = None

    while monotonic() < deadline:
        record = await asyncio.to_thread(store.get_job, job_id)
        if record.status in {JobStatus.SUCCEEDED.value, JobStatus.FAILED.value}:
            note_job_terminal(
                job_id=record.job_id,
                worker_type=record.worker_type.value,
                status=record.status,
                created_at=record.created_at,
            )
            return

        pod_failure, pod_running = await _inspect_job_pods(core, app_settings, job_name)
        if pod_failure is not None:
            failed = await asyncio.to_thread(store.mark_failed, job_id, message=pod_failure)
            note_job_terminal(
                job_id=failed.job_id,
                worker_type=failed.worker_type.value,
                status=failed.status,
                created_at=failed.created_at,
            )
            return

        if pod_running:
            await asyncio.to_thread(
                store.mark_running,
                job_id,
                message=f"Kubernetes job {job_name} is running.",
            )

        job_obj = await batch.read_namespaced_job_status(
            name=job_name,
            namespace=app_settings.kubernetes_namespace,
        )
        status_obj = getattr(job_obj, "status", None)
        if _job_succeeded(status_obj):
            if success_grace_deadline is None:
                success_grace_deadline = monotonic() + 15
            elif monotonic() >= success_grace_deadline:
                latest = await asyncio.to_thread(store.get_job, job_id)
                if latest.status not in {JobStatus.SUCCEEDED.value, JobStatus.FAILED.value}:
                    failed = await asyncio.to_thread(
                        store.mark_failed,
                        job_id,
                        message=(
                            f"Kubernetes job {job_name} completed, but worker metadata "
                            "was not updated."
                        ),
                    )
                    note_job_terminal(
                        job_id=failed.job_id,
                        worker_type=failed.worker_type.value,
                        status=failed.status,
                        created_at=failed.created_at,
                    )
                else:
                    note_job_terminal(
                        job_id=latest.job_id,
                        worker_type=latest.worker_type.value,
                        status=latest.status,
                        created_at=latest.created_at,
                    )
                return
        elif _job_failed(status_obj):
            failure_message = _build_job_failure_message(job_name, status_obj)
            failed = await asyncio.to_thread(store.mark_failed, job_id, message=failure_message)
            note_job_terminal(
                job_id=failed.job_id,
                worker_type=failed.worker_type.value,
                status=failed.status,
                created_at=failed.created_at,
            )
            return
        else:
            success_grace_deadline = None

        await asyncio.sleep(2)

    failed = await asyncio.to_thread(
        store.mark_failed,
        job_id,
        message=(
            f"Kubernetes job {job_name} did not reach a terminal state within "
            f"{app_settings.worker_poll_timeout_seconds} seconds."
        ),
    )
    note_job_terminal(
        job_id=failed.job_id,
        worker_type=failed.worker_type.value,
        status=failed.status,
        created_at=failed.created_at,
    )


def _job_name_from_response(created: client.V1Job, app_settings: Settings, job_id: str) -> str:
    metadata = getattr(created, "metadata", None)
    name = getattr(metadata, "name", None)
    if isinstance(name, str) and name:
        return name
    return _k8s_ident(f"{app_settings.job_name_prefix}{job_id}")


def _job_succeeded(status_obj: object) -> bool:
    succeeded = getattr(status_obj, "succeeded", None)
    return isinstance(succeeded, int) and succeeded > 0


def _job_failed(status_obj: object) -> bool:
    failed = getattr(status_obj, "failed", None)
    return isinstance(failed, int) and failed > 0


def _build_job_failure_message(job_name: str, status_obj: object) -> str:
    conditions = cast(list[Any], getattr(status_obj, "conditions", None) or [])
    for condition in conditions:
        reason = getattr(condition, "reason", None)
        message = getattr(condition, "message", None)
        if isinstance(reason, str) and reason:
            if isinstance(message, str) and message:
                return f"Kubernetes job {job_name} failed: {reason} - {message}"
            return f"Kubernetes job {job_name} failed: {reason}"
    return f"Kubernetes job {job_name} failed."


async def _inspect_job_pods(
    core: client.CoreV1Api,
    app_settings: Settings,
    job_name: str,
) -> tuple[str | None, bool]:
    pod_list = await core.list_namespaced_pod(
        namespace=app_settings.kubernetes_namespace,
        label_selector=f"job-name={job_name}",
    )
    items = cast(list[Any], getattr(pod_list, "items", None) or [])
    pod_running = False
    for pod in items:
        pod_status = getattr(pod, "status", None)
        pod_phase = getattr(pod_status, "phase", None)
        pod_name = getattr(getattr(pod, "metadata", None), "name", job_name)

        if pod_phase == "Running":
            pod_running = True
        if pod_phase == "Failed":
            reason = getattr(pod_status, "reason", None) or "PodFailed"
            message = getattr(pod_status, "message", None) or ""
            detail = f"{reason}: {message}".strip(": ")
            return f"Kubernetes pod {pod_name} failed ({detail}).", pod_running

        container_statuses = cast(
            list[Any],
            getattr(pod_status, "container_statuses", None) or [],
        )
        for container_status in container_statuses:
            state = getattr(container_status, "state", None)
            waiting = getattr(state, "waiting", None)
            reason = getattr(waiting, "reason", None)
            message = getattr(waiting, "message", None)
            if isinstance(reason, str) and reason in _FAILED_POD_REASONS:
                detail = f"{reason}: {message}".strip(": ")
                return (
                    f"Kubernetes pod {pod_name} is blocked before execution ({detail}).",
                    pod_running,
                )
    return None, pod_running


def on_k8s_submission_error(job_id: str, exc: BaseException) -> None:
    try:
        storage = get_storage()
        store = get_job_store(storage)
        store.mark_failed(job_id, message=f"Kubernetes job submission failed: {exc}")
    except StorageError:
        return
