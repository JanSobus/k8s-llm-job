from collections.abc import Mapping


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.json_objects: dict[str, dict[str, object]] = {}

    def ensure_bucket(self) -> None:
        return None

    def put_bytes(self, key: str, body: bytes, content_type: str) -> None:
        self.objects[key] = (body, content_type)

    def put_json(self, key: str, payload: Mapping[str, object]) -> None:
        self.objects[key] = (repr(dict(payload)).encode("utf-8"), "application/json")
        self.json_objects[key] = dict(payload)

    def get_bytes(self, key: str) -> bytes:
        return self.objects[key][0]

    def get_json(self, key: str) -> dict[str, object]:
        return self.json_objects[key]

    def presigned_get_url(self, key: str, expires_in: int = 3600) -> str:
        return f"https://example.test/{key}?expires={expires_in}"

