from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest  # type: ignore[import-untyped]

from backend.app.chat import router as chat_router
from backend.app.config import Settings, get_settings
from backend.app.llm import resolve_llm_connection
from backend.app.schemas import HealthResponse
from backend.app.tmpl import TEMPLATES
from backend.app.uploads import render_upload_error
from backend.app.uploads import router as uploads_router

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="K8s LLM Job")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(chat_router)
app.include_router(uploads_router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> Response:
    if request.url.path == "/upload":
        return HTMLResponse(render_upload_error("Choose a PDF or CSV file before uploading."))
    return await request_validation_exception_handler(request, exc)


@app.get("/", response_class=Response)
async def index(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    connection = resolve_llm_connection(settings)
    return TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {
            "app_name": settings.app_name,
            "provider": connection.provider.value,
            "model": connection.model,
            "fake_mode": connection.fake_mode,
            "grafana_url": settings.grafana_url,
        },
    )


@app.get("/healthz")
async def healthz(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name)


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
