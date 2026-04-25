import csv
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePath


class WorkerType(StrEnum):
    PDF = "pdf"
    TABULAR = "tabular"


class UploadKind(StrEnum):
    PDF = "pdf"
    CSV = "csv"


class UnsupportedUploadTypeError(ValueError):
    pass


@dataclass(frozen=True)
class UploadRoute:
    worker_type: WorkerType
    input_kind: UploadKind
    job_template_name: str


PDF_ROUTE = UploadRoute(
    worker_type=WorkerType.PDF,
    input_kind=UploadKind.PDF,
    job_template_name="worker-pdf",
)
CSV_ROUTE = UploadRoute(
    worker_type=WorkerType.TABULAR,
    input_kind=UploadKind.CSV,
    job_template_name="worker-tabular",
)

CSV_MIME_TYPES = {"text/csv", "application/csv", "application/vnd.ms-excel"}


def resolve_upload_route(filename: str, content_type: str | None, sample: bytes) -> UploadRoute:
    suffix = PurePath(filename).suffix.lower()
    normalized_content_type = (content_type or "").split(";")[0].strip().lower()

    if (
        suffix == ".pdf"
        and normalized_content_type == "application/pdf"
        and sample.startswith(b"%PDF-")
    ):
        return PDF_ROUTE

    if suffix == ".csv" and normalized_content_type in CSV_MIME_TYPES and _looks_like_csv(sample):
        return CSV_ROUTE

    raise UnsupportedUploadTypeError(
        "Only PDF and CSV uploads are supported. "
        "Check the file extension, content type, and content."
    )


def safe_filename(filename: str) -> str:
    name = PurePath(filename).name.strip().replace(" ", "_")
    safe = "".join(char for char in name if char.isalnum() or char in {"-", "_", "."})
    if not safe or safe in {".", ".."}:
        raise ValueError("Upload filename is empty or unsafe")
    return safe


def _looks_like_csv(sample: bytes) -> bool:
    try:
        text = sample.decode("utf-8-sig")
    except UnicodeDecodeError:
        return False

    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return False

    sample_text = "\n".join(lines[:5])
    try:
        dialect = csv.Sniffer().sniff(sample_text)
    except csv.Error:
        return "," in lines[0]

    return dialect.delimiter in {",", ";", "\t"}
