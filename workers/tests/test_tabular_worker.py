from collections.abc import Callable, Mapping
from typing import cast

import polars as pl
import pytest

from backend.app.config import Settings
from backend.app.jobs import MinioJobStore
from backend.app.routing import CSV_ROUTE
from backend.tests.fakes import FakeStorage
from workers.tabular import worker as tabular_worker


def _queue_tabular_job(storage: FakeStorage) -> tuple[MinioJobStore, str, str]:
    store = MinioJobStore(storage)
    record = store.create_queued_job(
        original_filename="events.csv",
        safe_filename="events.csv",
        content_type="text/csv",
        route=CSV_ROUTE,
    )
    return store, record.job_id, record.input_object_key


def _column_stats(payload: dict[str, object], name: str) -> dict[str, object]:
    stats = cast(list[dict[str, object]], payload["column_stats"])
    for item in stats:
        if item.get("name") == name:
            return item
    raise AssertionError(f"missing stats for column {name}")


def test_tabular_worker_writes_stats_and_llm_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    storage = FakeStorage()
    store, job_id, input_key = _queue_tabular_job(storage)
    prompts: list[str] = []

    def fake_summary(prompt: str, settings: Settings) -> str:
        prompts.append(prompt)
        return "Tabular summary from test"

    monkeypatch.setattr(tabular_worker, "run_llm_summary", fake_summary)

    storage.put_bytes(
        input_key,
        b"name,value,optional\natlas,42,\ncms,7,5\n",
        "text/csv",
    )
    tabular_worker.run_tabular_job(job_id, storage=storage, store=store)
    final = store.get_job(job_id)
    assert final.status == "succeeded"
    assert final.result_object_key is not None
    assert final.result_object_key in storage.json_objects
    payload = storage.get_json(final.result_object_key)
    assert payload.get("kind") == "tabular"
    assert payload.get("row_count") == 2
    assert payload.get("columns") == ["name", "value", "optional"]
    assert payload.get("llm_summary") == "Tabular summary from test"
    assert f"Data preview job {job_id}" in prompts[0]

    value_stats = _column_stats(payload, "value")
    assert value_stats.get("min") == 7
    assert value_stats.get("max") == 42
    assert value_stats.get("mean") == 24.5

    optional_stats = _column_stats(payload, "optional")
    assert optional_stats.get("null_count") == 1


def test_tabular_worker_records_llm_fallback_note(monkeypatch: pytest.MonkeyPatch) -> None:
    storage = FakeStorage()
    store, job_id, input_key = _queue_tabular_job(storage)
    storage.put_bytes(input_key, b"name,value\natlas,42\n", "text/csv")

    def fake_summary(prompt: str, settings: Settings) -> None:
        return None

    monkeypatch.setattr(tabular_worker, "run_llm_summary", fake_summary)

    tabular_worker.run_tabular_job(job_id, storage=storage, store=store)

    final = store.get_job(job_id)
    assert final.status == "succeeded"
    assert final.result_object_key is not None
    payload = storage.get_json(final.result_object_key)
    assert payload.get("llm_summary") is None
    assert "No LLM summary" in str(payload.get("llm_note"))


def test_tabular_worker_marks_bad_csv_failed() -> None:
    storage = FakeStorage()
    store, job_id, input_key = _queue_tabular_job(storage)
    storage.put_bytes(input_key, b"name,value\natlas,\xff\n", "text/csv")

    tabular_worker.run_tabular_job(job_id, storage=storage, store=store)

    final = store.get_job(job_id)
    assert final.status == "failed"
    assert final.message is not None
    assert "Tabular job failed:" in final.message
    assert final.result_object_key not in storage.json_objects


def test_json_safe_scalar_normalizes_nan() -> None:
    json_safe_scalar = cast(
        Callable[[object], object],
        vars(tabular_worker)["_json_safe_scalar"],
    )

    assert json_safe_scalar(1.5) == 1.5
    assert json_safe_scalar(float("nan")) is None
    assert json_safe_scalar({"nested": "value"}) == "{'nested': 'value'}"


def test_build_column_stats_handles_numeric_and_null_values() -> None:
    df = pl.DataFrame({"name": ["atlas", "cms"], "value": [42, None]})
    build_column_stats = cast(
        Callable[[pl.DataFrame], list[Mapping[str, object]]],
        vars(tabular_worker)["_build_column_stats"],
    )

    stats = build_column_stats(df)

    value_stats = next(item for item in stats if item.get("name") == "value")
    assert value_stats.get("null_count") == 1
    assert value_stats.get("min") == 42
    assert value_stats.get("max") == 42
    assert value_stats.get("mean") == 42.0
