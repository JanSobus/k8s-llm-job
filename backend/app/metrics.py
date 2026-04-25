from typing import Any

from prometheus_client import Counter, Gauge, Histogram  # type: ignore[import-untyped]

# Chat endpoint
CHAT_REQUESTS: Any = Counter(
    "cern_ml_chat_requests_total",
    "Total chat requests",
    ["provider", "status"],  # status: success | error
)

CHAT_LATENCY: Any = Histogram(
    "cern_ml_chat_latency_seconds",
    "Chat request round-trip latency",
    ["provider"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

# Job lifecycle
ACTIVE_JOBS: Any = Gauge(
    "cern_ml_active_jobs",
    "Jobs currently in queued or running state",
    ["worker_type"],  # pdf | tabular
)

JOB_COMPLETIONS: Any = Counter(
    "cern_ml_job_completions_total",
    "Completed jobs by outcome",
    ["worker_type", "status"],  # status: succeeded | failed
)

JOB_DURATION: Any = Histogram(
    "cern_ml_job_duration_seconds",
    "Time from job creation to terminal state",
    ["worker_type"],
    buckets=[1, 5, 15, 30, 60, 120, 300, 600],
)
