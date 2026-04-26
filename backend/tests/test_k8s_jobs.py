from types import SimpleNamespace

import pytest

from backend.app.config import JobExecutionMode, Settings
from backend.app.jobs import MinioJobStore
from backend.app.k8s_jobs import build_worker_job, reconcile_kubernetes_job
from backend.app.routing import CSV_ROUTE, PDF_ROUTE
from backend.tests.fakes import FakeStorage


def test_build_k8s_job_uses_tabular_image_and_module() -> None:
    settings = Settings()
    job = build_worker_job("a" * 32, CSV_ROUTE, settings)
    assert job.metadata is not None
    assert job.metadata.name is not None
    assert job.spec is not None
    assert job.spec.template is not None
    assert job.spec.template.spec is not None
    pod = job.spec.template.spec
    assert pod.containers is not None
    container = pod.containers[0]
    assert container.image == settings.worker_image_tabular
    assert container.args is not None
    assert "workers.tabular.main" in container.args


def test_build_k8s_job_uses_pdf_image() -> None:
    settings = Settings()
    job = build_worker_job("b" * 32, PDF_ROUTE, settings)
    assert job.spec is not None
    assert job.spec.template is not None
    assert job.spec.template.spec is not None
    container = job.spec.template.spec.containers[0]
    assert container.image == settings.worker_image_pdf
    assert container.args is not None
    assert "workers.pdf.main" in container.args


def test_build_k8s_job_sets_ttl_and_labels() -> None:
    settings = Settings()
    job = build_worker_job("c" * 32, CSV_ROUTE, settings)
    assert job.spec is not None
    assert job.spec.ttl_seconds_after_finished == settings.job_ttl_seconds_after_finished
    assert job.metadata is not None
    assert job.metadata.labels is not None
    assert job.metadata.labels.get("job-id") == "c" * 32


@pytest.mark.asyncio
async def test_reconcile_kubernetes_job_marks_failed_on_image_pull_backoff() -> None:
    storage = FakeStorage()
    store = MinioJobStore(storage)
    record = store.create_queued_job(
        original_filename="events.csv",
        safe_filename="events.csv",
        content_type="text/csv",
        route=CSV_ROUTE,
    )

    class FakeCoreV1Api:
        async def list_namespaced_pod(self, namespace: str, label_selector: str) -> object:
            _ = namespace, label_selector
            waiting = SimpleNamespace(reason="ImagePullBackOff", message="pull failed")
            state = SimpleNamespace(waiting=waiting)
            container_status = SimpleNamespace(state=state)
            status = SimpleNamespace(
                phase="Pending",
                reason=None,
                message=None,
                container_statuses=[container_status],
            )
            metadata = SimpleNamespace(name="worker-pod-1")
            return SimpleNamespace(items=[SimpleNamespace(metadata=metadata, status=status)])

    class FakeBatchV1Api:
        async def read_namespaced_job_status(self, name: str, namespace: str) -> object:
            _ = name, namespace
            return SimpleNamespace(
                status=SimpleNamespace(succeeded=None, failed=None, conditions=[]),
            )

    settings = Settings(
        job_execution_mode=JobExecutionMode.KUBERNETES,
        worker_poll_timeout_seconds=5,
    )

    from unittest.mock import patch

    with (
        patch("backend.app.k8s_jobs.get_storage", return_value=storage),
        patch("backend.app.k8s_jobs._load_kubernetes_config"),
        patch("backend.app.k8s_jobs.client.CoreV1Api", return_value=FakeCoreV1Api()),
        patch("backend.app.k8s_jobs.client.BatchV1Api", return_value=FakeBatchV1Api()),
    ):
        await reconcile_kubernetes_job(record.job_id, "k8s-llm-job-wk-abc", settings)

    final = store.get_job(record.job_id)
    assert final.status == "failed"
    assert final.message is not None
    assert "ImagePullBackOff" in final.message
