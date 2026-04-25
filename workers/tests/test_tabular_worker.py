from backend.app.jobs import MinioJobStore
from backend.app.routing import CSV_ROUTE
from backend.tests.fakes import FakeStorage
from workers.tabular.worker import run_tabular_job


def test_tabular_worker_succeeds_with_fake_storage() -> None:
    storage = FakeStorage()
    store = MinioJobStore(storage)
    record = store.create_queued_job(
        original_filename="events.csv",
        safe_filename="events.csv",
        content_type="text/csv",
        route=CSV_ROUTE,
    )
    storage.put_bytes(record.input_object_key, b"name,value\natlas,42\n", "text/csv")
    run_tabular_job(record.job_id, storage=storage, store=store)
    final = store.get_job(record.job_id)
    assert final.status == "succeeded"
    assert record.result_object_key is not None
    assert record.result_object_key in storage.json_objects
    payload = storage.get_json(record.result_object_key)
    assert payload.get("kind") == "tabular"
    assert payload.get("row_count") == 1
