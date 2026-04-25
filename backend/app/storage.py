from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from json import dumps, loads
from typing import TYPE_CHECKING, Any, Protocol, cast

import boto3
from boto3.session import Session
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client

from backend.app.config import Settings, get_settings


class StorageError(RuntimeError):
    pass


class ObjectStorage(Protocol):
    def ensure_bucket(self) -> None: ...

    def put_bytes(self, key: str, body: bytes, content_type: str) -> None: ...

    def put_json(self, key: str, payload: Mapping[str, object]) -> None: ...

    def get_bytes(self, key: str) -> bytes: ...

    def get_json(self, key: str) -> dict[str, object]: ...

    def presigned_get_url(self, key: str, expires_in: int = 3600) -> str: ...


@dataclass(frozen=True)
class MinioStorage:
    client: S3Client
    bucket: str

    @classmethod
    def from_settings(cls, settings: Settings) -> MinioStorage:
        session: Session = boto3.session.Session()
        client: S3Client = cast(  # type: ignore[type-arg]
            Any,
            cast(Any, session.client)(  # pyright: ignore[reportUnknownMemberType]
                "s3",
                endpoint_url=settings.minio_endpoint,
                aws_access_key_id=settings.minio_access_key.get_secret_value(),
                aws_secret_access_key=settings.minio_secret_key.get_secret_value(),
                use_ssl=settings.minio_secure,
            ),
        )
        return cls(client=client, bucket=settings.minio_bucket)

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            error = cast(dict[str, Any], exc.response.get("Error", {}))
            code = str(error.get("Code", ""))
            if code not in {"404", "NoSuchBucket", "NotFound"}:
                raise StorageError(f"Could not access bucket {self.bucket}") from exc
            self.client.create_bucket(Bucket=self.bucket)

    def put_bytes(self, key: str, body: bytes, content_type: str) -> None:
        self.ensure_bucket()
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=BytesIO(body),
            ContentType=content_type,
        )

    def put_json(self, key: str, payload: Mapping[str, object]) -> None:
        body = dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.put_bytes(key, body, "application/json")

    def get_bytes(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            raise StorageError(f"Object not found: {key}") from exc
        return response["Body"].read()

    def get_json(self, key: str) -> dict[str, object]:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            raise StorageError(f"Object not found: {key}") from exc

        raw_body = response["Body"].read()
        data = loads(raw_body.decode("utf-8"))
        if not isinstance(data, dict):
            raise StorageError(f"Object is not a JSON object: {key}")
        return cast(dict[str, object], data)

    def presigned_get_url(self, key: str, expires_in: int = 3600) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )


def upload_object_key(job_id: str, filename: str) -> str:
    return f"jobs/{job_id}/input/{filename}"


def job_metadata_key(job_id: str) -> str:
    return f"jobs/{job_id}/metadata.json"


def job_result_key(job_id: str) -> str:
    return f"jobs/{job_id}/result.json"


def get_storage() -> ObjectStorage:
    return MinioStorage.from_settings(get_settings())
