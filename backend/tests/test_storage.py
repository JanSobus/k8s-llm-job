from backend.app.storage import job_metadata_key, job_result_key, upload_object_key


def test_storage_key_conventions() -> None:
    assert upload_object_key("abc", "events.csv") == "jobs/abc/input/events.csv"
    assert job_metadata_key("abc") == "jobs/abc/metadata.json"
    assert job_result_key("abc") == "jobs/abc/result.json"
