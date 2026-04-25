import pytest
from pydantic import SecretStr

from backend.app.config import Provider, Settings
from backend.app.llm import generate_chat_response, resolve_llm_connection


def test_resolve_openai_connection_without_key_uses_fake_mode() -> None:
    settings = Settings(
        llm_provider=Provider.OPENAI,
        llm_fake_mode=False,
        openai_api_key=None,
    )

    connection = resolve_llm_connection(settings)

    assert connection.provider == Provider.OPENAI
    assert connection.model == "gpt-4o-mini"
    assert connection.fake_mode is True


def test_resolve_openai_connection_with_empty_key_uses_fake_mode() -> None:
    """Empty env value (APP_OPENAI_API_KEY=) must behave like a missing key."""
    settings = Settings(
        llm_provider=Provider.OPENAI,
        llm_fake_mode=False,
        openai_api_key=SecretStr(""),
    )

    connection = resolve_llm_connection(settings)

    assert connection.provider == Provider.OPENAI
    assert connection.api_key is None
    assert connection.fake_mode is True


def test_resolve_ollama_connection() -> None:
    settings = Settings(llm_provider=Provider.OLLAMA, llm_fake_mode=False)

    connection = resolve_llm_connection(settings)

    assert connection.provider == Provider.OLLAMA
    assert connection.base_url == "http://localhost:11434/v1"
    assert connection.model == "qwen2.5:0.5b"
    assert connection.fake_mode is False


@pytest.mark.asyncio
async def test_generate_chat_response_fake_mode() -> None:
    settings = Settings(llm_provider=Provider.KSERVE, llm_fake_mode=True)

    response = await generate_chat_response("hello", settings)

    assert "fake kserve" in response
    assert "hello" in response
