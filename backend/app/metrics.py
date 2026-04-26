from datetime import UTC, datetime
from threading import Lock
from typing import Any

from prometheus_client import Counter, Gauge, Histogram  # type: ignore[import-untyped]

# Chat endpoint
CHAT_REQUESTS: Any = Counter(
    "k8s_llm_chat_requests_total",
    "Total chat requests",
    ["provider", "status"],  # status: success | error
)

CHAT_LATENCY: Any = Histogram(
    "k8s_llm_chat_latency_seconds",
    "Chat request round-trip latency",
    ["provider"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

# Job lifecycle
ACTIVE_JOBS: Any = Gauge(
    "k8s_llm_active_jobs",
    "Jobs currently in queued or running state",
    ["worker_type"],  # pdf | tabular
)

JOB_COMPLETIONS: Any = Counter(
    "k8s_llm_job_completions_total",
    "Completed jobs by outcome",
    ["worker_type", "status"],  # status: succeeded | failed
)

JOB_DURATION: Any = Histogram(
    "k8s_llm_job_duration_seconds",
    "Time from job creation to terminal state",
    ["worker_type"],
    buckets=[1, 5, 15, 30, 60, 120, 300, 600],
)

_job_metrics_lock = Lock()
_active_job_ids: dict[str, str] = {}
_completed_job_ids: set[str] = set()


def note_job_active(job_id: str, worker_type: str) -> None:
    with _job_metrics_lock:
        if job_id in _active_job_ids:
            return
        _active_job_ids[job_id] = worker_type
    ACTIVE_JOBS.labels(worker_type=worker_type).inc()


def note_job_terminal(
    job_id: str,
    worker_type: str,
    status: str,
    created_at: str,
) -> None:
    with _job_metrics_lock:
        active_worker_type = _active_job_ids.pop(job_id, None)
        already_completed = job_id in _completed_job_ids
        if not already_completed:
            _completed_job_ids.add(job_id)

    if active_worker_type is not None:
        ACTIVE_JOBS.labels(worker_type=active_worker_type).dec()

    if already_completed:
        return

    JOB_COMPLETIONS.labels(worker_type=worker_type, status=status).inc()
    try:
        created = datetime.fromisoformat(created_at)
        duration = (datetime.now(UTC) - created).total_seconds()
        JOB_DURATION.labels(worker_type=worker_type).observe(duration)
    except (ValueError, TypeError):
        return
