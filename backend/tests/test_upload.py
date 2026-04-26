from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.config import Settings, get_settings
from backend.app.main import app
from backend.app.storage import StorageError
from backend.app.uploads import storage_dependency
from backend.tests.fakes import FakeStorage


class FailingPutStorage(FakeStorage):
    def put_bytes(self, key: str, body: bytes, content_type: str) -> None:
        raise StorageError("write failed")


def test_jobs_list_empty_storage_renders_empty_state() -> None:
    storage = FakeStorage()
    app.dependency_overrides[storage_dependency] = lambda: storage
    client = TestClient(app)

    try:
        response = client.get("/jobs")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "No jobs yet" in response.text


def test_upload_csv_creates_job_and_stores_object() -> None:
    storage = FakeStorage()
    app.dependency_overrides[storage_dependency] = lambda: storage
    client = TestClient(app)

    try:
        with patch("backend.app.uploads.submit_local_job"):
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
        with patch("backend.app.uploads.submit_local_job"):
            response = client.post(
                "/upload",
                files={"file": ("notes.txt", b"hello", "text/plain")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Upload not accepted" in response.text
    assert "Unsupported content type" in response.text


def test_upload_storage_failure_does_not_persist_queued_metadata() -> None:
    storage = FailingPutStorage()
    app.dependency_overrides[storage_dependency] = lambda: storage
    client = TestClient(app)

    try:
        with patch("backend.app.uploads.submit_local_job"):
            response = client.post(
                "/upload",
                files={"file": ("events.csv", b"name,value\natlas,1\n", "text/csv")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Could not store the upload" in response.text
    assert storage.json_objects == {}


def test_upload_missing_file_returns_visible_error_fragment() -> None:
    storage = FakeStorage()
    app.dependency_overrides[storage_dependency] = lambda: storage
    client = TestClient(app)

    try:
        response = client.post("/upload", files={})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Choose a PDF or CSV file" in response.text


def test_upload_empty_file_returns_visible_error_fragment() -> None:
    storage = FakeStorage()
    app.dependency_overrides[storage_dependency] = lambda: storage
    client = TestClient(app)

    try:
        response = client.post(
            "/upload",
            files={"file": ("events.csv", b"", "text/csv")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Upload file is empty" in response.text


def test_upload_too_large_returns_visible_error_fragment() -> None:
    storage = FakeStorage()
    app.dependency_overrides[storage_dependency] = lambda: storage
    app.dependency_overrides[get_settings] = lambda: Settings(upload_max_bytes=4)
    client = TestClient(app)

    try:
        response = client.post(
            "/upload",
            files={"file": ("events.csv", b"name,value\natlas,1\n", "text/csv")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Upload exceeds maximum size" in response.text
