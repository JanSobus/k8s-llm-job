import pytest

from backend.app.routing import (
    UnsupportedUploadTypeError,
    WorkerType,
    resolve_upload_route,
    safe_filename,
)


def test_pdf_route_requires_extension_mime_and_magic() -> None:
    route = resolve_upload_route("paper.pdf", "application/pdf", b"%PDF-1.4")

    assert route.worker_type == WorkerType.PDF
    assert route.job_template_name == "worker-pdf"


def test_csv_route_accepts_csv_content() -> None:
    route = resolve_upload_route("events.csv", "text/csv", b"name,value\natlas,1\n")

    assert route.worker_type == WorkerType.TABULAR
    assert route.job_template_name == "worker-tabular"


def test_rejects_unsupported_upload() -> None:
    with pytest.raises(UnsupportedUploadTypeError):
        resolve_upload_route("notes.txt", "text/plain", b"hello")


def test_safe_filename_strips_path_and_unsafe_chars() -> None:
    assert safe_filename("../my file.csv") == "my_file.csv"
