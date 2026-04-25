from pydantic import BaseModel, Field

from backend.app.config import Provider
from backend.app.routing import UploadKind, WorkerType


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)


class ChatResponse(BaseModel):
    provider: Provider
    model: str
    content: str
    fake_mode: bool


class HealthResponse(BaseModel):
    status: str
    app: str


class JobRecord(BaseModel):
    job_id: str
    original_filename: str
    safe_filename: str
    content_type: str
    worker_type: WorkerType
    input_kind: UploadKind
    job_template_name: str
    input_object_key: str
    metadata_object_key: str
    result_object_key: str | None = None
    status: str
    created_at: str
    updated_at: str
    message: str | None = None


class UploadAccepted(BaseModel):
    job_id: str
    status: str
    worker_type: WorkerType
    input_object_key: str
    metadata_object_key: str
