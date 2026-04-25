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
