from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from backend.app.config import Settings
from backend.app.jobs import MinioJobStore
from backend.app.routing import PDF_ROUTE
from backend.tests.fakes import FakeStorage
from workers.pdf import worker as pdf_worker

_ROOT = Path(__file__).resolve().parents[2]


def _queue_pdf_job(storage: FakeStorage) -> tuple[MinioJobStore, str, str]:
    store = MinioJobStore(storage)
    record = store.create_queued_job(
        original_filename="sample.pdf",
        safe_filename="sample.pdf",
        content_type="application/pdf",
        route=PDF_ROUTE,
    )
    return store, record.job_id, record.input_object_key


def test_pdf_worker_writes_extraction_and_llm_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    sample = _ROOT / "examples" / "sample.pdf"
    body = sample.read_bytes()
    storage = FakeStorage()
    store, job_id, input_key = _queue_pdf_job(storage)
    prompts: list[str] = []

    def fake_summary(prompt: str, settings: Settings) -> str:
        prompts.append(prompt)
        return "PDF summary from test"

    monkeypatch.setattr(pdf_worker, "run_llm_summary", fake_summary)

    storage.put_bytes(input_key, body, "application/pdf")
    pdf_worker.run_pdf_job(job_id, storage=storage, store=store)
    final = store.get_job(job_id)
    assert final.status == "succeeded"
    assert final.result_object_key is not None
    payload = storage.get_json(final.result_object_key)
    assert payload.get("kind") == "pdf"
    page_count = payload.get("page_count")
    assert isinstance(page_count, int) and page_count >= 1
    assert isinstance(payload.get("metadata"), dict)
    assert isinstance(payload.get("first_page_text_excerpt"), str)
    assert payload.get("llm_summary") == "PDF summary from test"
    assert "Pages:" in prompts[0]


def test_pdf_worker_records_llm_fallback_note(monkeypatch: pytest.MonkeyPatch) -> None:
    storage = FakeStorage()
    store, job_id, input_key = _queue_pdf_job(storage)
    storage.put_bytes(
        input_key,
        (_ROOT / "examples" / "sample.pdf").read_bytes(),
        "application/pdf",
    )

    def fake_summary(prompt: str, settings: Settings) -> None:
        return None

    monkeypatch.setattr(pdf_worker, "run_llm_summary", fake_summary)

    pdf_worker.run_pdf_job(job_id, storage=storage, store=store)

    final = store.get_job(job_id)
    assert final.status == "succeeded"
    assert final.result_object_key is not None
    payload = storage.get_json(final.result_object_key)
    assert payload.get("llm_summary") is None
    assert "No LLM summary" in str(payload.get("llm_note"))


def test_pdf_worker_marks_invalid_pdf_failed() -> None:
    storage = FakeStorage()
    store, job_id, input_key = _queue_pdf_job(storage)
    storage.put_bytes(input_key, b"not a pdf", "application/pdf")

    pdf_worker.run_pdf_job(job_id, storage=storage, store=store)

    final = store.get_job(job_id)
    assert final.status == "failed"
    assert final.message is not None
    assert "PDF job failed:" in final.message
    assert final.result_object_key not in storage.json_objects


def test_clean_meta_strips_whitespace_and_handles_empty_values() -> None:
    clean_meta = cast(Callable[[str | None], str], vars(pdf_worker)["_clean_meta"])

    assert clean_meta("  Example Title  ") == "Example Title"
    assert clean_meta("") == ""
    assert clean_meta(None) == ""
