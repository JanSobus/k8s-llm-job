"""Tests for the stateless chat routes."""
import json
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.config import Provider, Settings, get_settings
from backend.app.jobs import MinioJobStore
from backend.app.main import app
from backend.app.routing import CSV_ROUTE
from backend.tests.fakes import FakeStorage


def _fake_settings() -> Settings:
    return Settings(llm_provider=Provider.OPENAI, llm_fake_mode=True, openai_api_key=None)


def test_chat_post_single_message() -> None:
    app.dependency_overrides[get_settings] = _fake_settings
    client = TestClient(app)
    try:
        r = client.post("/chat", data={"message": "hello"})
        assert r.status_code == 200
        assert "hello" in r.text
    finally:
        app.dependency_overrides.clear()


def test_chat_post_with_history_shows_full_transcript() -> None:
    app.dependency_overrides[get_settings] = _fake_settings
    client = TestClient(app)
    prior_history = json.dumps([
        {"role": "user", "content": "prior message"},
        {"role": "assistant", "content": "prior reply"},
    ])
    try:
        r = client.post("/chat", data={"message": "new message", "history": prior_history})
        assert r.status_code == 200
        assert "prior message" in r.text
        assert "new message" in r.text
    finally:
        app.dependency_overrides.clear()


def test_chat_clear_returns_empty_transcript() -> None:
    app.dependency_overrides[get_settings] = _fake_settings
    client = TestClient(app)
    try:
        r = client.post("/chat/clear")
        assert r.status_code == 200
        assert "prior message" not in r.text
    finally:
        app.dependency_overrides.clear()


def test_chat_detach_strips_system_message() -> None:
    app.dependency_overrides[get_settings] = _fake_settings
    client = TestClient(app)
    history_with_system = json.dumps([
        {"role": "system", "content": "You are discussing job abc123."},
        {"role": "user", "content": "hello"},
    ])
    try:
        r = client.post("/chat/detach", data={"history": history_with_system})
        assert r.status_code == 200
        assert "You are discussing" not in r.text
        assert "hello" in r.text
    finally:
        app.dependency_overrides.clear()


def test_chat_attach_sets_context() -> None:
    storage = FakeStorage()
    store = MinioJobStore(storage)
    record = store.create_queued_job(
        original_filename="test.csv",
        safe_filename="test.csv",
        content_type="text/csv",
        route=CSV_ROUTE,
    )
    store.mark_succeeded(record.job_id)
    result_payload: dict[str, object] = {
        "kind": "tabular",
        "row_count": 5,
        "columns": ["a", "b"],
        "llm_summary": None,
    }
    storage.put_json(record.result_object_key or "jobs/x/result.json", result_payload)

    app.dependency_overrides[get_settings] = _fake_settings
    client = TestClient(app)
    try:
        with patch("backend.app.chat.get_storage", return_value=storage):
            r = client.post(f"/chat/attach/{record.job_id}", data={"history": "[]"})
        assert r.status_code == 200
        assert "test.csv" in r.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_generate_chat_response_receives_full_history() -> None:
    from backend.app.llm import generate_chat_response

    settings = Settings(llm_provider=Provider.OPENAI, llm_fake_mode=True)
    messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply1"},
        {"role": "user", "content": "second"},
    ]
    response = await generate_chat_response(messages, settings)
    assert "second" in response


def test_chat_post_provider_error_renders_inline_message() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        llm_provider=Provider.OPENAI,
        llm_fake_mode=False,
        openai_api_key=SecretStr("test-key"),
    )
    client = TestClient(app)
    try:
        with patch(
            "backend.app.chat.generate_chat_response",
            side_effect=httpx.ConnectError("provider down"),
        ):
            r = client.post("/chat", data={"message": "hello"})
        assert r.status_code == 200
        assert "could not be reached" in r.text
        assert "hello" in r.text
    finally:
        app.dependency_overrides.clear()


def test_chat_post_trims_old_history() -> None:
    app.dependency_overrides[get_settings] = _fake_settings
    client = TestClient(app)
    history = json.dumps(
        [{"role": "user", "content": f"old-{idx}"} for idx in range(30)]
    )
    try:
        r = client.post("/chat", data={"message": "latest", "history": history})
        assert r.status_code == 200
        assert "Conversation was trimmed" in r.text
        assert "old-0" not in r.text
        assert "latest" in r.text
    finally:
        app.dependency_overrides.clear()


def test_chat_attach_missing_job_renders_inline_message() -> None:
    storage = FakeStorage()
    app.dependency_overrides[get_settings] = _fake_settings
    client = TestClient(app)
    try:
        with patch("backend.app.chat.get_storage", return_value=storage):
            r = client.post("/chat/attach/missing-job", data={"history": "[]"})
        assert r.status_code == 200
        assert "Job not found" in r.text
    finally:
        app.dependency_overrides.clear()
