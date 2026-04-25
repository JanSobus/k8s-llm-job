from backend.app.jobs import JobStatus, MinioJobStore
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
