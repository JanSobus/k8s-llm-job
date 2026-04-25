from fastapi.testclient import TestClient

from backend.app.config import Provider, Settings, get_settings
from backend.app.main import app


def test_healthz() -> None:
    client = TestClient(app)

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_index_renders() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "CERN ML Demo" in response.text


def test_chat_fake_mode() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        llm_provider=Provider.OPENAI,
        llm_fake_mode=True,
        openai_api_key=None,
    )
    client = TestClient(app)

    try:
        response = client.post("/chat", data={"message": "hello"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "fake openai" in response.text


def test_metrics_endpoint_exposes_custom_metrics() -> None:
    client = TestClient(app)

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    body = response.text
    # All five metric families must be registered, even before any traffic
    assert "cern_ml_chat_requests_total" in body
    assert "cern_ml_chat_latency_seconds" in body
    assert "cern_ml_active_jobs" in body
    assert "cern_ml_job_completions_total" in body
    assert "cern_ml_job_duration_seconds" in body
