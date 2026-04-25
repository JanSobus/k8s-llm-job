from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from backend.app.routing import UploadRoute
from backend.app.schemas import JobRecord
from backend.app.storage import ObjectStorage, job_metadata_key, job_result_key, upload_object_key


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class JobStore(Protocol):
    def create_queued_job(
        self,
        *,
        original_filename: str,
        safe_filename: str,
        content_type: str,
        route: UploadRoute,
    ) -> JobRecord: ...

    def get_job(self, job_id: str) -> JobRecord: ...

    def update_job(
        self,
        job_id: str,
        *,
        status: str,
        message: str | None = None,
    ) -> JobRecord: ...

    def mark_running(self, job_id: str, message: str | None = None) -> JobRecord: ...

    def mark_succeeded(self, job_id: str, message: str | None = None) -> JobRecord: ...

    def mark_failed(self, job_id: str, message: str | None = None) -> JobRecord: ...


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class MinioJobStore:
    def __init__(self, storage: ObjectStorage) -> None:
        self._storage = storage

    def create_queued_job(
        self,
        *,
        original_filename: str,
        safe_filename: str,
        content_type: str,
        route: UploadRoute,
    ) -> JobRecord:
        job_id = uuid4().hex
        now = _now_iso()
        record = JobRecord(
            job_id=job_id,
            original_filename=original_filename,
            safe_filename=safe_filename,
            content_type=content_type,
            worker_type=route.worker_type,
            input_kind=route.input_kind,
            job_template_name=route.job_template_name,
            input_object_key=upload_object_key(job_id, safe_filename),
            metadata_object_key=job_metadata_key(job_id),
            result_object_key=job_result_key(job_id),
            status=JobStatus.QUEUED.value,
            created_at=now,
            updated_at=now,
            message="Queued. Execution will start shortly.",
        )
        self._storage.put_json(record.metadata_object_key, record.model_dump(mode="json"))
        return record

    def get_job(self, job_id: str) -> JobRecord:
        payload = self._storage.get_json(job_metadata_key(job_id))
        return JobRecord.model_validate(payload)

    def _persist(self, record: JobRecord) -> None:
        self._storage.put_json(record.metadata_object_key, record.model_dump(mode="json"))

    def update_job(
        self,
        job_id: str,
        *,
        status: str,
        message: str | None = None,
    ) -> JobRecord:
        record = self.get_job(job_id)
        now = _now_iso()
        updated = record.model_copy(
            update={"status": status, "updated_at": now, "message": message},
        )
        self._persist(updated)
        return updated

    def mark_running(self, job_id: str, message: str | None = "Running.") -> JobRecord:
        return self.update_job(job_id, status=JobStatus.RUNNING.value, message=message)

    def mark_succeeded(self, job_id: str, message: str | None = "Succeeded.") -> JobRecord:
        return self.update_job(job_id, status=JobStatus.SUCCEEDED.value, message=message)

    def mark_failed(self, job_id: str, message: str | None = "Failed.") -> JobRecord:
        return self.update_job(job_id, status=JobStatus.FAILED.value, message=message)


def get_job_store(storage: ObjectStorage) -> JobStore:
    return MinioJobStore(storage)
