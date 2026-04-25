from pathlib import Path

from backend.app.jobs import MinioJobStore
from backend.app.routing import PDF_ROUTE
from backend.tests.fakes import FakeStorage
from workers.pdf.worker import run_pdf_job

_ROOT = Path(__file__).resolve().parents[2]


def test_pdf_worker_succeeds_with_sample_pdf() -> None:
    sample = _ROOT / "examples" / "sample.pdf"
    body = sample.read_bytes()
    storage = FakeStorage()
    store = MinioJobStore(storage)
    record = store.create_queued_job(
        original_filename="sample.pdf",
        safe_filename="sample.pdf",
        content_type="application/pdf",
        route=PDF_ROUTE,
    )
    storage.put_bytes(record.input_object_key, body, "application/pdf")
    run_pdf_job(record.job_id, storage=storage, store=store)
    final = store.get_job(record.job_id)
    assert final.status == "succeeded"
    assert record.result_object_key is not None
    payload = storage.get_json(record.result_object_key)
    assert payload.get("kind") == "pdf"
    page_count = payload.get("page_count")
    assert isinstance(page_count, int) and page_count >= 1
