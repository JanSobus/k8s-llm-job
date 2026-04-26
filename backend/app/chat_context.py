from __future__ import annotations

from typing import cast

from backend.app.routing import WorkerType
from backend.app.schemas import JobRecord


def build_system_message(record: JobRecord, result: dict[str, object]) -> str:
    if record.worker_type == WorkerType.TABULAR:
        rows = result.get("row_count", "?")
        cols_raw = result.get("columns", [])
        col_list: list[object] = cast(list[object], cols_raw) if isinstance(cols_raw, list) else []
        n_cols = len(col_list)
        col_names = ", ".join(str(c) for c in col_list[:10])
        llm_note = result.get("llm_summary") or "n/a"
        return (
            f"You are discussing tabular job {record.job_id} ({record.original_filename}). "
            f"The result has {rows} rows × {n_cols} columns. "
            f"Columns: {col_names}. "
            f"LLM note: {llm_note}."
        )
    else:
        pages = result.get("page_count", "?")
        title = result.get("title") or ""
        excerpt_raw = result.get("first_page_text_excerpt", "")
        excerpt = str(excerpt_raw)[:300] if excerpt_raw else ""
        llm_note = result.get("llm_summary") or "n/a"
        return (
            f"You are discussing PDF job {record.job_id} ({record.original_filename}). "
            f"The PDF has {pages} pages, title '{title}'. "
            f"First excerpt: {excerpt}. "
            f"LLM note: {llm_note}."
        )
