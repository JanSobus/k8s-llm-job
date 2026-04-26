from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock

from backend.app.config import Settings
from backend.app.jobs import get_job_store
from backend.app.routing import WorkerType
from backend.app.storage import StorageError, get_storage

_LOG = logging.getLogger(__name__)
_executor: ThreadPoolExecutor | None = None
_executor_lock = Lock()
_executor_workers: int | None = None


def submit_local_job(job_id: str, worker_type: WorkerType, settings: Settings) -> None:
    executor = _get_executor(settings.max_concurrent_jobs)
    try:
        future = executor.submit(run_local_job_sync, job_id, worker_type)
        future.add_done_callback(lambda done: mark_local_job_future_result(job_id, done))
    except RuntimeError as exc:
        _LOG.exception("Could not enqueue local job %s", job_id)
        _mark_local_job_failed(job_id, exc)


def _get_executor(max_workers: int) -> ThreadPoolExecutor:
    global _executor, _executor_workers
    worker_count = max(1, max_workers)
    with _executor_lock:
        if _executor is None or worker_count != _executor_workers:
            if _executor is not None:
                _executor.shutdown(wait=False)
            _executor = ThreadPoolExecutor(
                max_workers=worker_count,
                thread_name_prefix="k8s-llm-local-worker",
            )
            _executor_workers = worker_count
        return _executor


def run_local_job_sync(job_id: str, worker_type: WorkerType) -> None:
    """Run worker logic synchronously inside the bounded local worker pool."""
    if worker_type is WorkerType.TABULAR:
        from workers.tabular.worker import run_tabular_job

        run_tabular_job(job_id)
        return
    from workers.pdf.worker import run_pdf_job

    run_pdf_job(job_id)


def _mark_local_job_failed(job_id: str, exc: BaseException) -> None:
    try:
        store = get_job_store(get_storage())
        store.mark_failed(job_id, message=f"Local job failed: {exc}")
    except StorageError:
        _LOG.exception("Could not persist local enqueue failure for %s", job_id)


def mark_local_job_future_result(job_id: str, future: Future[None]) -> None:
    if future.cancelled():
        _mark_local_job_failed(job_id, RuntimeError("worker task was cancelled"))
        return
    exc = future.exception()
    if exc is None:
        return
    _LOG.exception("Local worker failed for %s", job_id, exc_info=exc)
    _mark_local_job_failed(job_id, exc)
