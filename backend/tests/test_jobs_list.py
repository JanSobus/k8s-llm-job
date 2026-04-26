from backend.app.jobs import MinioJobStore
from backend.app.routing import CSV_ROUTE
from backend.tests.fakes import FakeStorage


def _make_store() -> tuple[MinioJobStore, FakeStorage]:
    storage = FakeStorage()
    return MinioJobStore(storage), storage


def test_list_jobs_empty() -> None:
    store, _ = _make_store()
    assert store.list_jobs() == []


def test_list_jobs_returns_records_sorted_desc() -> None:
    store, _ = _make_store()
    store.create_queued_job(
        original_filename="a.csv",
        safe_filename="a.csv",
        content_type="text/csv",
        route=CSV_ROUTE,
    )
    store.create_queued_job(
        original_filename="b.csv",
        safe_filename="b.csv",
        content_type="text/csv",
        route=CSV_ROUTE,
    )
    jobs = store.list_jobs()
    assert len(jobs) == 2
    assert jobs[0].created_at >= jobs[1].created_at
    assert {j.original_filename for j in jobs} == {"a.csv", "b.csv"}


def test_list_jobs_respects_limit() -> None:
    store, _ = _make_store()
    for i in range(5):
        store.create_queued_job(
            original_filename=f"file{i}.csv",
            safe_filename=f"file{i}.csv",
            content_type="text/csv",
            route=CSV_ROUTE,
        )
    jobs = store.list_jobs(limit=3)
    assert len(jobs) == 3


def test_list_jobs_skips_non_metadata_keys() -> None:
    store, storage = _make_store()
    store.create_queued_job(
        original_filename="a.csv",
        safe_filename="a.csv",
        content_type="text/csv",
        route=CSV_ROUTE,
    )
    # Seed an unrelated key that should be ignored
    storage.put_json("jobs/abc123/result.json", {"kind": "tabular"})
    jobs = store.list_jobs()
    assert len(jobs) == 1
