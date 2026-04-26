from fastapi.testclient import TestClient

from backend.app.kserve_smoke import app


def test_kserve_smoke_predictor_returns_openai_compatible_response() -> None:
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "smoke-model",
            "messages": [
                {"role": "system", "content": "Attached context"},
                {"role": "user", "content": "Summarize it"},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "smoke-model"
    assert payload["choices"][0]["message"]["role"] == "assistant"
    assert "kserve-smoke:smoke-model" in payload["choices"][0]["message"]["content"]
    assert "Context attached." in payload["choices"][0]["message"]["content"]
