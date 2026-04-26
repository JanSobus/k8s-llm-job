import asyncio
import logging

from backend.app.config import Settings
from backend.app.llm import generate_chat_response

_LOG = logging.getLogger(__name__)


def run_llm_summary(user_prompt: str, settings: Settings) -> str | None:
    """Run the same OpenAI-compatible chat path as the FastAPI app (async under the hood)."""
    try:
        return asyncio.run(_chat(user_prompt, settings))
    except Exception:  # noqa: BLE001 — optional summary; return None on any provider error
        _LOG.exception("LLM summary failed; continuing with deterministic output only")
        return None


async def _chat(user_prompt: str, settings: Settings) -> str:
    return await generate_chat_response([{"role": "user", "content": user_prompt}], settings)
