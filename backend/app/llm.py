from dataclasses import dataclass
from typing import cast

import httpx

from backend.app.config import Provider, Settings


@dataclass(frozen=True)
class LLMConnection:
    provider: Provider
    base_url: str
    model: str
    api_key: str | None
    fake_mode: bool


def resolve_llm_connection(settings: Settings) -> LLMConnection:
    match settings.llm_provider:
        case Provider.OPENAI:
            api_key = (
                settings.openai_api_key.get_secret_value()
                if settings.openai_api_key is not None
                else None
            )
            return LLMConnection(
                provider=Provider.OPENAI,
                base_url=settings.openai_base_url,
                model=settings.openai_model,
                api_key=api_key,
                fake_mode=settings.llm_fake_mode or api_key is None,
            )
        case Provider.OLLAMA:
            return LLMConnection(
                provider=Provider.OLLAMA,
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
                api_key=None,
                fake_mode=settings.llm_fake_mode,
            )
        case Provider.KSERVE:
            return LLMConnection(
                provider=Provider.KSERVE,
                base_url=settings.kserve_base_url,
                model=settings.kserve_model,
                api_key=None,
                fake_mode=settings.llm_fake_mode,
            )


async def generate_chat_response(message: str, settings: Settings) -> str:
    connection = resolve_llm_connection(settings)
    if connection.fake_mode:
        return fake_chat_response(message, connection)

    headers: dict[str, str] = {}
    if connection.api_key is not None:
        headers["Authorization"] = f"Bearer {connection.api_key}"

    payload: dict[str, object] = {
        "model": connection.model,
        "messages": [{"role": "user", "content": message}],
        "stream": False,
    }

    async with httpx.AsyncClient(base_url=connection.base_url, timeout=30.0) as client:
        response = await client.post("/chat/completions", headers=headers, json=payload)
        response.raise_for_status()

    data = cast(dict[str, object], response.json())
    choices_obj = data.get("choices")
    if not isinstance(choices_obj, list) or not choices_obj:
        raise ValueError("LLM response did not contain choices")

    choices = cast(list[object], choices_obj)
    first_choice_obj = choices[0]
    if not isinstance(first_choice_obj, dict):
        raise ValueError("LLM response choice was malformed")
    first_choice = cast(dict[str, object], first_choice_obj)

    response_message_obj = first_choice.get("message")
    if not isinstance(response_message_obj, dict):
        raise ValueError("LLM response message was malformed")
    response_message = cast(dict[str, object], response_message_obj)

    content_obj = response_message.get("content")
    if not isinstance(content_obj, str):
        raise ValueError("LLM response content was missing")
    return content_obj


def fake_chat_response(message: str, connection: LLMConnection) -> str:
    return (
        f"[fake {connection.provider.value}:{connection.model}] "
        f"Received: {message.strip() or '(empty message)'}"
    )
