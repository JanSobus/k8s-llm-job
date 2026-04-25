from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest  # type: ignore[import-untyped]

from backend.app.chat import router as chat_router
from backend.app.config import Settings, get_settings
from backend.app.llm import resolve_llm_connection
from backend.app.schemas import HealthResponse
from backend.app.uploads import router as uploads_router

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

app = FastAPI(title="CERN ML Demo")
app.include_router(chat_router)
app.include_router(uploads_router)


@app.get("/", response_class=Response)
async def index(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    connection = resolve_llm_connection(settings)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "app_name": settings.app_name,
            "provider": connection.provider.value,
            "model": connection.model,
            "fake_mode": connection.fake_mode,
        },
    )


@app.get("/healthz")
async def healthz(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name)


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
