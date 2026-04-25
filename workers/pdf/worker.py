from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, cast

import fitz  # type: ignore[import-untyped]  # PyMuPDF

from backend.app.config import Settings
from backend.app.jobs import MinioJobStore
from backend.app.storage import MinioStorage, ObjectStorage, StorageError, job_result_key
from workers.shared.llm import run_llm_summary

_LOG = logging.getLogger(__name__)

_EXCERPT_MAX = 2_000


def run_pdf_job(
    job_id: str,
    *,
    storage: ObjectStorage | None = None,
    store: MinioJobStore | None = None,
) -> None:
    settings = Settings()
    if storage is None:
        storage = MinioStorage.from_settings(settings)
    if store is None:
        store = MinioJobStore(storage)
    try:
        store.mark_running(job_id, message="Processing PDF with PyMuPDF.")
        record = store.get_job(job_id)
        body = storage.get_bytes(record.input_object_key)
        page_count, raw_meta, first_text = _extract_pdf(body)

        result: dict[str, object] = {
            "kind": "pdf",
            "job_id": job_id,
            "page_count": page_count,
            "title": _clean_meta(raw_meta.get("title", "")),
            "author": _clean_meta(raw_meta.get("author", "")),
            "metadata": cast(Mapping[str, object], dict(raw_meta)),
            "first_page_text_excerpt": first_text,
        }
        prompt = (
            f"One short human sentence describing this PDF. "
            f"Pages: {page_count}, title hint: {result.get('title', '')!s}."
        )
        llm = run_llm_summary(prompt, settings)
        if llm is not None:
            result["llm_summary"] = llm
        else:
            result["llm_summary"] = None
            result["llm_note"] = "No LLM summary (optional step failed or fake mode)."

        out_key = record.result_object_key or job_result_key(job_id)
        storage.put_json(out_key, result)
        store.mark_succeeded(
            job_id,
            message=f"PDF result written to {out_key}.",
        )
    except (StorageError, OSError, RuntimeError) as exc:
        _LOG.exception("PDF job failed: %s", job_id)
        try:
            store.mark_failed(job_id, message=f"PDF job failed: {exc}")
        except StorageError:
            _LOG.exception("Could not persist failed status for %s", job_id)


def _extract_pdf(body: bytes) -> tuple[int, dict[str, str], str]:
    with fitz.open(stream=body, filetype="pdf") as d:
        doc: Any = d
        page_count: int = len(doc)
        meta_in: dict[str, Any] = cast(dict[str, Any], doc.metadata or {})
        raw_meta = {str(k): str(v) for k, v in meta_in.items() if v}
        if page_count == 0:
            return 0, raw_meta, ""
        page0: Any = doc.load_page(0)
        text_raw: object = page0.get_text()
        text = text_raw if isinstance(text_raw, str) else str(text_raw)
        first = text[:_EXCERPT_MAX]
        return page_count, raw_meta, first


def _clean_meta(v: str | None) -> str:
    if not v:
        return ""
    return v.strip()
