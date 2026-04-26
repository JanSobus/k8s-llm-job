from concurrent.futures import Future
from unittest.mock import patch

from backend.app.jobs import JobStatus, MinioJobStore
from backend.app.local_jobs import mark_local_job_future_result
from backend.app.metrics import ACTIVE_JOBS, JOB_COMPLETIONS, note_job_active
from backend.app.routing import CSV_ROUTE, WorkerType
from backend.tests.fakes import FakeStorage


def test_update_job_status_transitions() -> None:
    storage = FakeStorage()
    store = MinioJobStore(storage)
    created = store.create_queued_job(
        original_filename="events.csv",
        safe_filename="events.csv",
        content_type="text/csv",
        route=CSV_ROUTE,
    )
    after_run = store.mark_running(created.job_id, message="Go")
    assert after_run.status == JobStatus.RUNNING.value
    done = store.mark_succeeded(created.job_id, message="Done")
    assert done.status == JobStatus.SUCCEEDED.value
    assert store.get_job(created.job_id).message == "Done"
    failed = store.create_queued_job(
        original_filename="b.csv",
        safe_filename="b.csv",
        content_type="text/csv",
        route=CSV_ROUTE,
    )
    store.mark_failed(failed.job_id, message="err")
    assert store.get_job(failed.job_id).status == JobStatus.FAILED.value


def test_create_queued_job_writes_metadata_to_storage() -> None:
    storage = FakeStorage()
    store = MinioJobStore(storage)

    record = store.create_queued_job(
        original_filename="events.csv",
        safe_filename="events.csv",
        content_type="text/csv",
        route=CSV_ROUTE,
    )

    assert record.status == JobStatus.QUEUED.value
    assert record.worker_type == WorkerType.TABULAR
    assert record.metadata_object_key in storage.json_objects


def test_get_job_reads_metadata_from_storage() -> None:
    storage = FakeStorage()
    store = MinioJobStore(storage)
    created = store.create_queued_job(
        original_filename="events.csv",
        safe_filename="events.csv",
        content_type="text/csv",
        route=CSV_ROUTE,
    )

    loaded = store.get_job(created.job_id)

    assert loaded == created


def test_terminal_metrics_are_idempotent_for_repeated_failure_marks() -> None:
    storage = FakeStorage()
    store = MinioJobStore(storage)
    created = store.create_queued_job(
        original_filename="events.csv",
        safe_filename="events.csv",
        content_type="text/csv",
        route=CSV_ROUTE,
    )

    active_metric = ACTIVE_JOBS.labels(worker_type=created.worker_type.value)
    completion_metric = JOB_COMPLETIONS.labels(
        worker_type=created.worker_type.value,
        status=JobStatus.FAILED.value,
    )
    active_before = active_metric._value.get()
    failed_before = completion_metric._value.get()

    note_job_active(created.job_id, created.worker_type.value)
    assert active_metric._value.get() == active_before + 1

    store.mark_failed(created.job_id, message="boom")
    assert active_metric._value.get() == active_before
    assert completion_metric._value.get() == failed_before + 1

    store.mark_failed(created.job_id, message="boom")
    assert active_metric._value.get() == active_before
    assert completion_metric._value.get() == failed_before + 1


def test_local_worker_future_exception_marks_job_failed() -> None:
    storage = FakeStorage()
    store = MinioJobStore(storage)
    created = store.create_queued_job(
        original_filename="events.csv",
        safe_filename="events.csv",
        content_type="text/csv",
        route=CSV_ROUTE,
    )
    future: Future[None] = Future()
    future.set_exception(RuntimeError("worker import failed"))

    with patch("backend.app.local_jobs.get_storage", return_value=storage):
        mark_local_job_future_result(created.job_id, future)

    failed = store.get_job(created.job_id)
    assert failed.status == JobStatus.FAILED.value
    assert failed.message is not None
    assert "worker import failed" in failed.message
