import asyncio
import json
import time
from typing import Annotated, cast

import httpx
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from backend.app.chat_context import build_system_message
from backend.app.config import Settings, get_settings
from backend.app.jobs import JobStore, get_job_store
from backend.app.llm import generate_chat_response, resolve_llm_connection
from backend.app.metrics import CHAT_LATENCY, CHAT_REQUESTS
from backend.app.storage import ObjectStorage, StorageError, get_storage
from backend.app.tmpl import TEMPLATES

router = APIRouter()

_Message = dict[str, str]
_MAX_NON_SYSTEM_MESSAGES = 24


def _storage_dep() -> ObjectStorage:
    return get_storage()


def _job_store_dep(
    storage: Annotated[ObjectStorage, Depends(_storage_dep)],
) -> JobStore:
    return get_job_store(storage)


def _decode_history(history: str) -> list[_Message]:
    if not history.strip():
        return []
    try:
        data = json.loads(history)
        if isinstance(data, list):
            return [
                cast(_Message, m) for m in cast(list[object], data)
                if isinstance(m, dict) and "role" in m and "content" in m
            ]
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def _trim_history(messages: list[_Message]) -> tuple[list[_Message], str | None]:
    system_message: _Message | None = None
    if messages and messages[0].get("role") == "system":
        system_message = messages[0]
        messages = messages[1:]

    trimmed = False
    if len(messages) > _MAX_NON_SYSTEM_MESSAGES:
        messages = messages[-_MAX_NON_SYSTEM_MESSAGES:]
        trimmed = True

    output = ([system_message] if system_message is not None else []) + messages
    notice = None
    if trimmed:
        notice = (
            f"Conversation was trimmed to the most recent {_MAX_NON_SYSTEM_MESSAGES} "
            "messages to keep the demo responsive."
        )
    return output, notice


def _friendly_provider_error(exc: Exception, provider_name: str) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        if status_code in {401, 403}:
            return (
                f"{provider_name} authentication failed. "
                "Check the API key or provider credentials and retry."
            )
        if status_code == 404:
            return (
                f"{provider_name} could not find the configured model or endpoint. "
                "Check the base URL and model settings."
            )
        if status_code == 429:
            return f"{provider_name} rate-limited the request. Wait a moment and retry."
        if status_code >= 500:
            return f"{provider_name} returned a server error ({status_code}). Retry shortly."
        return f"{provider_name} request failed with HTTP {status_code}."
    if isinstance(exc, httpx.TimeoutException):
        return f"{provider_name} timed out before responding. Retry or reduce load."
    if isinstance(exc, httpx.ConnectError):
        return (
            f"{provider_name} could not be reached. Check that the provider is running "
            "and that the base URL is correct."
        )
    return f"{provider_name} request failed. Check the logs and provider settings."


def _render_panel(
    request: Request,
    messages: list[_Message],
    attached_filename: str,
    *,
    error_message: str | None = None,
    notice_message: str | None = None,
) -> HTMLResponse:
    return HTMLResponse(
        TEMPLATES.get_template("_chat_panel.html").render(
            {
                "request": request,
                "messages": messages,
                "messages_json": json.dumps(messages),
                "attached_filename": attached_filename,
                "error_message": error_message,
                "notice_message": notice_message,
            }
        )
    )


@router.post("/chat", response_class=HTMLResponse)
async def chat_post(
    request: Request,
    message: Annotated[str, Form(min_length=1, max_length=4_000)],
    settings: Annotated[Settings, Depends(get_settings)],
    history: Annotated[str, Form()] = "",
    attached_filename: Annotated[str, Form()] = "",
) -> HTMLResponse:
    messages, notice_message = _trim_history(_decode_history(history))
    connection = resolve_llm_connection(settings)
    messages.append({"role": "user", "content": message})
    t0 = time.perf_counter()
    try:
        reply = await generate_chat_response(messages, settings)
        CHAT_REQUESTS.labels(provider=connection.provider.value, status="success").inc()
    except Exception as exc:
        CHAT_REQUESTS.labels(provider=connection.provider.value, status="error").inc()
        messages, trim_notice = _trim_history(messages)
        return _render_panel(
            request,
            messages,
            attached_filename,
            error_message=_friendly_provider_error(exc, connection.provider.value),
            notice_message=trim_notice or notice_message,
        )
    finally:
        CHAT_LATENCY.labels(provider=connection.provider.value).observe(
            time.perf_counter() - t0
        )
    messages.append({"role": "assistant", "content": reply})
    messages, trim_notice = _trim_history(messages)
    return _render_panel(
        request,
        messages,
        attached_filename,
        notice_message=trim_notice or notice_message,
    )


@router.post("/chat/attach/{job_id}", response_class=HTMLResponse)
async def chat_attach(
    request: Request,
    job_id: str,
    job_store: Annotated[JobStore, Depends(_job_store_dep)],
    storage: Annotated[ObjectStorage, Depends(_storage_dep)],
    history: Annotated[str, Form()] = "",
) -> HTMLResponse:
    messages, notice_message = _trim_history(_decode_history(history))
    try:
        record = await asyncio.to_thread(job_store.get_job, job_id)
    except (StorageError, ValueError):
        return _render_panel(
            request,
            messages,
            "",
            error_message=f"Job not found: {job_id}",
            notice_message=notice_message,
        )
    if record.status != "succeeded":
        return _render_panel(
            request,
            messages,
            "",
            error_message="That job is not ready for discussion yet. Wait for it to succeed.",
            notice_message=notice_message,
        )
    if not record.result_object_key:
        return _render_panel(
            request,
            messages,
            "",
            error_message="That job has no result payload attached yet.",
            notice_message=notice_message,
        )
    try:
        result = await asyncio.to_thread(storage.get_json, record.result_object_key)
    except StorageError:
        return _render_panel(
            request,
            messages,
            "",
            error_message="The job result object is missing from storage.",
            notice_message=notice_message,
        )

    system_content = build_system_message(record, result)
    if messages and messages[0]["role"] == "system":
        messages[0] = {"role": "system", "content": system_content}
    else:
        messages.insert(0, {"role": "system", "content": system_content})
    messages, trim_notice = _trim_history(messages)
    return _render_panel(
        request,
        messages,
        record.original_filename,
        notice_message=trim_notice or notice_message,
    )


@router.post("/chat/detach", response_class=HTMLResponse)
async def chat_detach(
    request: Request,
    history: Annotated[str, Form()] = "",
) -> HTMLResponse:
    messages = [m for m in _decode_history(history) if m["role"] != "system"]
    messages, notice_message = _trim_history(messages)
    return _render_panel(request, messages, "", notice_message=notice_message)


@router.post("/chat/clear", response_class=HTMLResponse)
async def chat_clear(request: Request) -> HTMLResponse:
    return _render_panel(request, [], "")
