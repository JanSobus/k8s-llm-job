from backend.app.config import JobExecutionMode, Provider, Settings


def test_default_settings_use_openai_fake_mode() -> None:
    settings = Settings(
        llm_provider=Provider.OPENAI,
        llm_fake_mode=True,
        openai_api_key=None,
    )

    assert settings.llm_provider == Provider.OPENAI
    assert settings.llm_fake_mode is True
    assert settings.openai_model == "gpt-4o-mini"
    assert settings.minio_endpoint == "http://localhost:9000"
    assert settings.job_execution_mode is JobExecutionMode.LOCAL


def test_provider_can_be_overridden() -> None:
    settings = Settings(llm_provider=Provider.OLLAMA, ollama_model="llama3.2:1b")

    assert settings.llm_provider == Provider.OLLAMA
    assert settings.ollama_model == "llama3.2:1b"
