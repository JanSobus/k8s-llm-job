from __future__ import annotations

import io
import logging
from collections.abc import Mapping
from typing import Any
from typing import cast as typing_cast

import polars as pl

from backend.app.config import Settings
from backend.app.jobs import MinioJobStore
from backend.app.storage import MinioStorage, ObjectStorage, StorageError, job_result_key
from workers.shared.llm import run_llm_summary

_LOG = logging.getLogger(__name__)


def _json_safe_scalar(v: object) -> object:
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float) and (v == v):
        return v
    if isinstance(v, float):
        return None
    return str(v)


def _build_column_stats(df: pl.DataFrame) -> list[Mapping[str, object]]:
    out: list[Mapping[str, object]] = []
    for name in df.columns:
        s = df[name]
        dt = s.dtype
        null_count = int(s.null_count())
        item: dict[str, Any] = {
            "name": name,
            "dtype": str(dt),
            "null_count": null_count,
        }
        if (dt.is_integer() or dt.is_float()) and s.len() - null_count > 0:
            non_null = s.drop_nulls()
            if non_null.is_empty():
                pass
            else:
                item["min"] = _json_safe_scalar(typing_cast(object, non_null.min()))  # pyright: ignore[reportUnknownMemberType]
                item["max"] = _json_safe_scalar(typing_cast(object, non_null.max()))  # pyright: ignore[reportUnknownMemberType]
                item["mean"] = _json_safe_scalar(typing_cast(object, non_null.mean()))  # pyright: ignore[reportUnknownMemberType]
        out.append(item)
    return out


def run_tabular_job(
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
        store.mark_running(job_id, message="Processing CSV with Polars.")
        record = store.get_job(job_id)
        body = storage.get_bytes(record.input_object_key)
        df = pl.read_csv(io.BytesIO(body))
        stats: dict[str, object] = {
            "kind": "tabular",
            "job_id": job_id,
            "row_count": int(df.height),
            "columns": [str(c) for c in df.columns],
            "column_stats": _build_column_stats(df),
        }
        summary_prompt = (
            f"Data preview job {job_id}. "
            f"Row count: {df.height}, columns: {', '.join(df.columns[:20])}."
            " One short human sentence describing this dataset (no code)."
        )
        llm = run_llm_summary(summary_prompt, settings)
        if llm is not None:
            stats["llm_summary"] = llm
        else:
            stats["llm_summary"] = None
            stats["llm_note"] = "No LLM summary (optional step failed or fake mode)."

        result_key_name = record.result_object_key or job_result_key(job_id)
        storage.put_json(result_key_name, stats)
        store.mark_succeeded(
            job_id,
            message=f"Tabular result written to {result_key_name}.",
        )
    except Exception as exc:  # noqa: BLE001 - worker must persist terminal status.
        _LOG.exception("Tabular job failed: %s", job_id)
        try:
            store.mark_failed(job_id, message=f"Tabular job failed: {exc}")
        except StorageError:
            _LOG.exception("Could not persist failed status for %s", job_id)
