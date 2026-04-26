from typing import Any, cast

from botocore.exceptions import ClientError

from backend.app.storage import MinioStorage, job_metadata_key, job_result_key, upload_object_key


def test_storage_key_conventions() -> None:
    assert upload_object_key("abc", "events.csv") == "jobs/abc/input/events.csv"
    assert job_metadata_key("abc") == "jobs/abc/metadata.json"
    assert job_result_key("abc") == "jobs/abc/result.json"


def test_list_keys_reads_all_pages() -> None:
    class FakeS3Client:
        def __init__(self) -> None:
            self.calls = 0

        def list_objects_v2(self, **kwargs: object) -> dict[str, object]:
            self.calls += 1
            if "ContinuationToken" not in kwargs:
                return {
                    "Contents": [{"Key": "jobs/a/metadata.json"}],
                    "IsTruncated": True,
                    "NextContinuationToken": "next",
                }
            return {
                "Contents": [{"Key": "jobs/b/metadata.json"}],
                "IsTruncated": False,
            }

    client = FakeS3Client()
    storage = MinioStorage(client=cast(Any, client), bucket="demo")

    assert storage.list_keys("jobs/") == ["jobs/a/metadata.json", "jobs/b/metadata.json"]
    assert client.calls == 2


def test_ensure_bucket_tolerates_concurrent_create() -> None:
    class FakeS3Client:
        def head_bucket(self, Bucket: str) -> None:
            _ = Bucket
            raise ClientError({"Error": {"Code": "404"}}, "HeadBucket")

        def create_bucket(self, Bucket: str) -> None:
            _ = Bucket
            raise ClientError({"Error": {"Code": "BucketAlreadyOwnedByYou"}}, "CreateBucket")

    storage = MinioStorage(client=cast(Any, FakeS3Client()), bucket="demo")

    storage.ensure_bucket()
