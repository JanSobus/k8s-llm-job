from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]


app = FastAPI(title="KServe Smoke Predictor")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/chat/completions")
@app.post("/chat/completions")
async def chat_completions(request: ChatCompletionRequest) -> dict[str, Any]:
    last_user = next(
        (message.content for message in reversed(request.messages) if message.role == "user"),
        "",
    )
    system_context = next(
        (message.content for message in request.messages if message.role == "system"),
        "",
    )
    context_note = " Context attached." if system_context else ""
    content = f"[kserve-smoke:{request.model}] Received: {last_user.strip()}.{context_note}"
    return {
        "id": "chatcmpl-kserve-smoke",
        "object": "chat.completion",
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }
