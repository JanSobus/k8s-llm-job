"""Object key helpers shared with the backend (single convention)."""

from backend.app.storage import job_metadata_key, job_result_key, upload_object_key

__all__ = [
    "job_metadata_key",
    "job_result_key",
    "upload_object_key",
]
