from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.uploads import storage_dependency
from backend.tests.fakes import FakeStorage


def test_upload_csv_creates_job_and_stores_object() -> None:
    storage = FakeStorage()
    app.dependency_overrides[storage_dependency] = lambda: storage
    client = TestClient(app)

    try:
        with patch("backend.app.uploads.run_local_job_sync"):
            response = client.post(
                "/upload",
                files={"file": ("events.csv", b"name,value\natlas,1\n", "text/csv")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "tabular" in response.text.lower()
    assert any(key.endswith("/input/events.csv") for key in storage.objects)
    assert any(key.endswith("/metadata.json") for key in storage.json_objects)


def test_upload_rejects_unsupported_file() -> None:
    storage = FakeStorage()
    app.dependency_overrides[storage_dependency] = lambda: storage
    client = TestClient(app)

    try:
        with patch("backend.app.uploads.run_local_job_sync"):
            response = client.post(
                "/upload",
                files={"file": ("notes.txt", b"hello", "text/plain")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
