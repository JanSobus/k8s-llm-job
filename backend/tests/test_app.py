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
    assert "K8s LLM Job" in response.text
    assert "/static/htmx-lite.js" in response.text


def test_static_htmx_lite_asset_is_served() -> None:
    client = TestClient(app)

    response = client.get("/static/htmx-lite.js")

    assert response.status_code == 200
    assert "Minimal local HTMX-compatible behavior" in response.text


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
    assert "k8s_llm_chat_requests_total" in body
    assert "k8s_llm_chat_latency_seconds" in body
    assert "k8s_llm_active_jobs" in body
    assert "k8s_llm_job_completions_total" in body
    assert "k8s_llm_job_duration_seconds" in body
