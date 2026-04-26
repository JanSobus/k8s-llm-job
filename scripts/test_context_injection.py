# ruff: noqa: E402

import json
import pathlib
import re
import sys
from collections.abc import Sequence
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import Provider, Settings, get_settings
from backend.app.jobs import MinioJobStore
from backend.app.main import app
from backend.app.routing import CSV_ROUTE


class FakeStore:
    def __init__(self) -> None:
        self.json_objects: dict[str, dict[str, object]] = {}

    def put_json(self, key: str, data: dict[str, object]) -> None:
        self.json_objects[key] = data

    def get_json(self, key: str) -> dict[str, object]:
        return self.json_objects[key]

    def list_keys(self, prefix: str) -> list[str]:
        return [k for k in self.json_objects if k.startswith(prefix)]


def fake_settings() -> Settings:
    return Settings(llm_provider=Provider.OPENAI, llm_fake_mode=True)


def extract_history(html_text: str) -> list[dict[str, str]]:
    match = re.search(r'id="history-field"[^>]+value="([^"]*)"', html_text)
    assert match is not None, "History field was not rendered"
    history_raw = (
        match.group(1)
        .replace("&#34;", '"')
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    messages = json.loads(history_raw)
    assert isinstance(messages, list), "History payload is not a list"
    return messages


def describe_roles(messages: Sequence[dict[str, str]]) -> str:
    return ", ".join(message["role"] for message in messages)


def main() -> None:
    storage = FakeStore()
    store = MinioJobStore(storage)
    record = store.create_queued_job(
        original_filename="collision_data.csv",
        safe_filename="collision_data.csv",
        content_type="text/csv",
        route=CSV_ROUTE,
    )
    store.mark_succeeded(record.job_id)
    storage.put_json(
        record.result_object_key,
        {
            "kind": "tabular",
            "row_count": 42,
            "columns": [
                "run_id",
                "energy_gev",
                "particle_type",
                "event_count",
                "trigger_rate",
            ],
            "llm_summary": "Dataset contains LHC Run 3 collision events at 13.6 TeV.",
        },
    )

    client = TestClient(app)
    app.dependency_overrides[get_settings] = fake_settings

    try:
        with patch("backend.app.chat.get_storage", return_value=storage):
            attach_response = client.post(f"/chat/attach/{record.job_id}", data={"history": "[]"})
            assert attach_response.status_code == 200, attach_response.text
            assert "collision_data.csv" in attach_response.text

            attached_history = extract_history(attach_response.text)
            assert attached_history[0]["role"] == "system"

            chat_response = client.post(
                "/chat",
                data={
                    "message": "How many rows does this dataset have?",
                    "history": json.dumps(attached_history),
                    "attached_filename": "collision_data.csv",
                },
            )

        assert chat_response.status_code == 200, chat_response.text
        assert "fake openai" in chat_response.text

        final_history = extract_history(chat_response.text)
        assert final_history[-1]["role"] == "assistant"
        assert "How many rows" in final_history[-1]["content"]

        print("Context smoke check passed.")
        print(f"Attached roles: {describe_roles(attached_history)}")
        print(f"Final roles: {describe_roles(final_history)}")
    finally:
        app.dependency_overrides.clear()


if __name__ == "__main__":
    main()
