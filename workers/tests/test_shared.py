import pytest

from backend.app.config import Settings
from backend.app.storage import job_metadata_key, job_result_key, upload_object_key
from workers.shared import llm as shared_llm
from workers.shared import storage as shared_storage


def test_run_llm_summary_returns_chat_response(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[dict[str, str]]] = []

    async def fake_generate_chat_response(
        messages: list[dict[str, str]], settings: Settings
    ) -> str:
        calls.append(messages)
        return "summary from provider"

    monkeypatch.setattr(shared_llm, "generate_chat_response", fake_generate_chat_response)

    summary = shared_llm.run_llm_summary("summarize this", Settings())

    assert summary == "summary from provider"
    assert calls == [[{"role": "user", "content": "summarize this"}]]


def test_run_llm_summary_returns_none_on_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_generate_chat_response(
        messages: list[dict[str, str]], settings: Settings
    ) -> str:
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(shared_llm, "generate_chat_response", fake_generate_chat_response)

    assert shared_llm.run_llm_summary("summarize this", Settings()) is None


def test_shared_storage_exports_backend_key_convention() -> None:
    assert shared_storage.upload_object_key("abc123", "sample.csv") == upload_object_key(
        "abc123", "sample.csv"
    )
    assert shared_storage.job_metadata_key("abc123") == job_metadata_key("abc123")
    assert shared_storage.job_result_key("abc123") == job_result_key("abc123")
