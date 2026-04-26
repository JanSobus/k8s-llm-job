import asyncio
import html
import json
import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from kubernetes_asyncio.client import ApiException  # type: ignore[import-untyped]

from backend.app.config import JobExecutionMode, Settings, get_settings
from backend.app.jobs import JobStore, get_job_store
from backend.app.k8s_jobs import on_k8s_submission_error, submit_and_reconcile_kubernetes_job
from backend.app.local_jobs import submit_local_job
from backend.app.metrics import note_job_active
from backend.app.routing import (
    UnsupportedUploadTypeError,
    UploadRoute,
    resolve_upload_route,
    safe_filename,
)
from backend.app.schemas import JobRecord
from backend.app.storage import ObjectStorage, StorageError, get_storage
from backend.app.tmpl import TEMPLATES

LOG = logging.getLogger(__name__)

router = APIRouter()


def storage_dependency() -> ObjectStorage:
    return get_storage()


def job_store_dependency(
    storage: Annotated[ObjectStorage, Depends(storage_dependency)],
) -> JobStore:
    return get_job_store(storage)


async def _run_k8s_submission(
    job_id: str,
    route: UploadRoute,
) -> None:
    settings = get_settings()
    try:
        await submit_and_reconcile_kubernetes_job(job_id, route, settings)
    except (OSError, ValueError, ApiException) as exc:
        LOG.exception("Kubernetes job submission failed for %s", job_id)
        on_k8s_submission_error(job_id, exc)


@router.get("/jobs", response_class=HTMLResponse)
async def list_jobs(
    request: Request,
    job_store: Annotated[JobStore, Depends(job_store_dependency)],
) -> HTMLResponse:
    jobs: list[JobRecord] = []
    error: str | None = None
    try:
        jobs = await asyncio.to_thread(job_store.list_jobs, 20)
    except StorageError:
        error = "Could not load jobs from storage. Check MinIO and retry."
    return HTMLResponse(
        TEMPLATES.get_template("_job_list.html").render(
            {"request": request, "jobs": jobs, "error": error}
        )
    )


@router.post("/upload", response_class=HTMLResponse)
async def upload_file(
    file: Annotated[UploadFile, File()],
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[ObjectStorage, Depends(storage_dependency)],
    job_store: Annotated[JobStore, Depends(job_store_dependency)],
) -> HTMLResponse:
    original_filename = file.filename or ""
    try:
        filename = safe_filename(original_filename)
        content_type = _normalized_content_type(file.content_type)
        if content_type not in settings.allowed_upload_mime_types:
            raise ValueError(f"Unsupported content type: {content_type}")
        body = await _read_limited_upload(file, settings.upload_max_bytes)
        route = resolve_upload_route(filename, content_type, body[:4096])
        record = await asyncio.to_thread(
            job_store.build_queued_job,
            original_filename=original_filename,
            safe_filename=filename,
            content_type=content_type,
            route=route,
        )
        await asyncio.to_thread(
            storage.put_bytes,
            record.input_object_key,
            body,
            record.content_type,
        )
        record = await asyncio.to_thread(job_store.save_job, record)
        note_job_active(record.job_id, record.worker_type.value)
    except (UnsupportedUploadTypeError, ValueError) as exc:
        return upload_error_response(str(exc))
    except StorageError as exc:
        return upload_error_response(
            "Could not store the upload. Check MinIO and retry.",
            detail=str(exc),
        )

    if settings.job_execution_mode is JobExecutionMode.LOCAL:
        submit_local_job(record.job_id, route.worker_type, settings)
    elif settings.job_execution_mode is JobExecutionMode.KUBERNETES:
        background_tasks.add_task(_run_k8s_submission, record.job_id, route)

    return HTMLResponse(_render_job_card(record))


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    job_store: Annotated[JobStore, Depends(job_store_dependency)],
) -> JobRecord:
    try:
        return await asyncio.to_thread(job_store.get_job, job_id)
    except (StorageError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}") from exc


@router.get("/jobs/{job_id}/fragment", response_class=HTMLResponse)
async def get_job_fragment(
    job_id: str,
    job_store: Annotated[JobStore, Depends(job_store_dependency)],
    storage: Annotated[ObjectStorage, Depends(storage_dependency)],
) -> HTMLResponse:
    try:
        job = await asyncio.to_thread(job_store.get_job, job_id)
    except (StorageError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}") from exc
    result_payload: dict[str, object] | None = None
    result_missing = False
    if job.status == "succeeded" and job.result_object_key:
        try:
            result_payload = await asyncio.to_thread(storage.get_json, job.result_object_key)
        except StorageError:
            result_missing = True
    return HTMLResponse(_render_job_fragment_html(job, result_payload, result_missing))


@router.get("/jobs/{job_id}/result", response_class=HTMLResponse)
async def get_job_result_json_preview(
    job_id: str,
    job_store: Annotated[JobStore, Depends(job_store_dependency)],
    storage: Annotated[ObjectStorage, Depends(storage_dependency)],
) -> HTMLResponse:
    try:
        job = await asyncio.to_thread(job_store.get_job, job_id)
    except (StorageError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}") from exc
    if job.status != "succeeded" or not job.result_object_key:
        raise HTTPException(status_code=400, detail="Result not available yet")
    try:
        payload = await asyncio.to_thread(storage.get_json, job.result_object_key)
    except StorageError as exc:
        raise HTTPException(status_code=404, detail="Result object missing") from exc
    text = json.dumps(payload, indent=2, sort_keys=True)
    return HTMLResponse(f"<pre>{html.escape(text[:8000])}</pre>")


async def _read_limited_upload(file: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > max_bytes:
            raise ValueError(f"Upload exceeds maximum size of {max_bytes} bytes")
        chunks.append(chunk)

    if total == 0:
        raise ValueError("Upload file is empty")

    return b"".join(chunks)


def _normalized_content_type(content_type: str | None) -> str:
    if content_type is None:
        return "application/octet-stream"
    return content_type.split(";")[0].strip().lower()


def _render_job_card(record: JobRecord) -> str:
    jid = html.escape(record.job_id)
    poll_attrs = (
        f' hx-get="/jobs/{jid}/fragment" hx-trigger="load delay: 400ms, every 2s" '
        f'hx-swap="outerHTML"'
    )
    return (
        f'<section class="response-card" id="job-{jid}"{poll_attrs}>'
        "<h3>Upload accepted</h3>"
        f'<p class="meta">Job {jid} / {html.escape(record.worker_type.value)}</p>'
        f'<p>Status: <strong>{html.escape(record.status)}</strong></p>'
        f'<p>Stored input: <code>{html.escape(record.input_object_key)}</code></p>'
        f'<p><a href="/jobs/{jid}">View job JSON</a></p>'
        '<p class="meta">Refreshing status every 2s…</p>'
        "</section>"
    )


def render_upload_error(message: str, *, detail: str | None = None) -> str:
    detail_html = ""
    if detail:
        detail_html = f'<p class="meta">{html.escape(detail)}</p>'
    return (
        '<section class="response-card" role="alert" '
        'style="border-color:#f5c2c0;background:#fdecea;color:#8a1f17;">'
        "<h3>Upload not accepted</h3>"
        f"<p>{html.escape(message)}</p>"
        f"{detail_html}"
        "</section>"
    )


def upload_error_response(message: str, *, detail: str | None = None) -> HTMLResponse:
    # Return 200 so HTMX swaps the fragment into #upload-response without extra JS config.
    return HTMLResponse(render_upload_error(message, detail=detail))


def _render_job_fragment_html(
    job: JobRecord,
    result_payload: dict[str, object] | None,
    result_missing: bool = False,
) -> str:
    jid = html.escape(job.job_id)
    terminal = job.status in {"succeeded", "failed"}
    poll = "" if terminal else (
        f' hx-get="/jobs/{jid}/fragment" hx-trigger="load delay: 1s, every 2s" hx-swap="outerHTML"'
    )
    result_block = ""
    if job.status == "succeeded" and job.result_object_key:
        if result_missing:
            result_block = "<p>Result key recorded but object not found yet.</p>"
        elif result_payload is not None:
            text = json.dumps(result_payload, indent=2, sort_keys=True)
            if len(text) > 1_200:
                text = text[:1_200] + "\n… (truncated)"
            result_block = (
                f'<h4>Result (preview)</h4><pre class="result-json">{html.escape(text)}</pre>'
                f'<p><a href="/jobs/{jid}/result">View full result</a></p>'
            )
    msg = ""
    if job.message:
        msg = f'<p class="meta">{html.escape(job.message)}</p>'
    return (
        f'<section class="response-card" id="job-{jid}"{poll}>'
        f'<p class="meta">Job {jid} / {html.escape(job.worker_type.value)}</p>'
        f'<p>Status: <strong>{html.escape(job.status)}</strong></p>'
        f"{msg}"
        f'<p>Metadata: <a href="/jobs/{jid}">JSON</a></p>'
        f"{result_block}"
        "</section>"
    )
