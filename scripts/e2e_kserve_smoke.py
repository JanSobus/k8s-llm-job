from __future__ import annotations

import argparse
import html
import json
import re
import time
from pathlib import Path

import httpx

JOB_ID_RE = re.compile(r"Job ([0-9a-f]+)")
HISTORY_RE = re.compile(r'id="history-field"[^>]+value="([^"]*)"')


def _extract_history(fragment: str) -> list[dict[str, str]]:
    match = HISTORY_RE.search(fragment)
    if match is None:
        raise AssertionError("chat response did not include a history field")
    history = json.loads(html.unescape(match.group(1)))
    if not isinstance(history, list):
        raise AssertionError("history field did not decode to a list")
    return history


def _wait_for_job(
    client: httpx.Client,
    job_id: str,
    *,
    timeout_seconds: int,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    last_status = "unknown"
    while time.monotonic() < deadline:
        response = client.get(f"/jobs/{job_id}")
        response.raise_for_status()
        payload = response.json()
        last_status = str(payload.get("status", "unknown"))
        print(f"job {job_id}: {last_status}")
        if last_status == "succeeded":
            return payload
        if last_status == "failed":
            raise AssertionError(f"job {job_id} failed: {payload.get('message')}")
        time.sleep(2)
    raise TimeoutError(f"job {job_id} did not finish; last status was {last_status}")


def run_smoke(base_url: str, upload_path: Path, timeout_seconds: int) -> None:
    with httpx.Client(base_url=base_url, timeout=60.0, follow_redirects=True) as client:
        health = client.get("/healthz")
        health.raise_for_status()
        print(f"health: {health.json()}")

        home = client.get("/")
        home.raise_for_status()
        if "kserve /" not in home.text or "fake mode" in home.text:
            raise AssertionError("homepage does not show real kserve provider mode")
        print("homepage: kserve provider visible")

        chat = client.post("/chat", data={"message": "hello from e2e", "history": "[]"})
        chat.raise_for_status()
        if "kserve-smoke" not in chat.text:
            raise AssertionError("chat response did not come from the KServe smoke predictor")
        print("chat: backend reached KServe predictor")

        content_type = "text/csv" if upload_path.suffix.lower() == ".csv" else "application/pdf"
        with upload_path.open("rb") as handle:
            upload = client.post(
                "/upload",
                files={"file": (upload_path.name, handle, content_type)},
            )
        upload.raise_for_status()
        match = JOB_ID_RE.search(upload.text)
        if match is None:
            raise AssertionError("upload response did not include a job id")
        job_id = match.group(1)
        print(f"upload: job {job_id}")

        job = _wait_for_job(client, job_id, timeout_seconds=timeout_seconds)
        result_key = job.get("result_object_key")
        if not isinstance(result_key, str) or not result_key:
            raise AssertionError("succeeded job did not include a result object key")

        result = client.get(f"/jobs/{job_id}/result")
        result.raise_for_status()
        if "kserve-smoke" not in result.text:
            raise AssertionError("worker result did not include KServe-backed LLM summary")
        print("worker: result summary came from KServe")

        attached = client.post(f"/chat/attach/{job_id}", data={"history": "[]"})
        attached.raise_for_status()
        if upload_path.name not in attached.text:
            raise AssertionError("attached chat panel did not show the uploaded filename")
        history = _extract_history(attached.text)
        if not history or history[0].get("role") != "system":
            raise AssertionError("attached chat history did not start with system context")
        print("context: job result attached to chat")

        follow_up = client.post(
            "/chat",
            data={
                "message": "Summarize the attached file in one sentence",
                "history": json.dumps(history),
                "attached_filename": upload_path.name,
            },
        )
        follow_up.raise_for_status()
        if "kserve-smoke" not in follow_up.text or "Context attached." not in follow_up.text:
            raise AssertionError("attached-context chat did not reach KServe with system context")
        print("context chat: KServe response used attached context")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the kind + KServe e2e smoke test.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--upload", type=Path, default=Path("examples/sample.csv"))
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args()

    run_smoke(args.base_url, args.upload, args.timeout_seconds)
    print("KServe e2e smoke passed.")


if __name__ == "__main__":
    main()
