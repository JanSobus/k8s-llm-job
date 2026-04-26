from backend.app.chat_context import build_system_message
from backend.app.routing import CSV_ROUTE, PDF_ROUTE
from backend.app.schemas import JobRecord


def _make_record(route: object, filename: str = "test.csv") -> JobRecord:
    from backend.app.routing import UploadRoute
    r: UploadRoute = route  # type: ignore[assignment]
    return JobRecord(
        job_id="abc123",
        original_filename=filename,
        safe_filename=filename,
        content_type="text/csv",
        worker_type=r.worker_type,
        input_kind=r.input_kind,
        job_template_name=r.job_template_name,
        input_object_key="jobs/abc123/input/test.csv",
        metadata_object_key="jobs/abc123/metadata.json",
        result_object_key="jobs/abc123/result.json",
        status="succeeded",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:01:00+00:00",
    )


def test_build_system_message_tabular() -> None:
    record = _make_record(CSV_ROUTE, "data.csv")
    result: dict[str, object] = {
        "kind": "tabular",
        "row_count": 42,
        "columns": ["x", "y", "z"],
        "llm_summary": "A simple dataset.",
    }
    msg = build_system_message(record, result)
    assert "42 rows" in msg
    assert "3 columns" in msg
    assert "x, y, z" in msg
    assert "A simple dataset." in msg
    assert "data.csv" in msg


def test_build_system_message_pdf() -> None:
    record = _make_record(PDF_ROUTE, "paper.pdf")
    result: dict[str, object] = {
        "kind": "pdf",
        "page_count": 10,
        "title": "My Paper",
        "first_page_text_excerpt": "Abstract: This paper describes...",
        "llm_summary": "A physics paper.",
    }
    msg = build_system_message(record, result)
    assert "10 pages" in msg
    assert "My Paper" in msg
    assert "Abstract: This paper" in msg
    assert "A physics paper." in msg
    assert "paper.pdf" in msg


def test_build_system_message_tabular_no_llm_summary() -> None:
    record = _make_record(CSV_ROUTE)
    result: dict[str, object] = {
        "kind": "tabular",
        "row_count": 5,
        "columns": ["a"],
        "llm_summary": None,
    }
    msg = build_system_message(record, result)
    assert "n/a" in msg
