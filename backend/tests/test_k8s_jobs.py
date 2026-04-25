from backend.app.config import Settings
from backend.app.k8s_jobs import build_worker_job
from backend.app.routing import CSV_ROUTE, PDF_ROUTE


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
