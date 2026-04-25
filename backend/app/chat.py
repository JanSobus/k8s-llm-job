from html import escape
from typing import Annotated

from fastapi import APIRouter, Depends, Form
from fastapi.responses import HTMLResponse

from backend.app.config import Settings, get_settings
from backend.app.llm import generate_chat_response, resolve_llm_connection
from backend.app.schemas import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/chat", response_class=HTMLResponse)
async def chat_fragment(
    message: Annotated[str, Form(min_length=1, max_length=4_000)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HTMLResponse:
    response = await create_chat_response(ChatRequest(message=message), settings)
    return HTMLResponse(
        "<section class=\"response-card\">"
        f"<p class=\"meta\">{escape(response.provider.value)} / {escape(response.model)}</p>"
        f"<p>{escape(response.content)}</p>"
        "</section>"
    )


async def create_chat_response(request: ChatRequest, settings: Settings) -> ChatResponse:
    connection = resolve_llm_connection(settings)
    content = await generate_chat_response(request.message, settings)
    return ChatResponse(
        provider=connection.provider,
        model=connection.model,
        content=content,
        fake_mode=connection.fake_mode,
    )
