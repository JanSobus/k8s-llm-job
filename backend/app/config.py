from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Provider(StrEnum):
    KSERVE = "kserve"
    OPENAI = "openai"
    OLLAMA = "ollama"


class JobExecutionMode(StrEnum):
    LOCAL = "local"
    KUBERNETES = "kubernetes"


class Settings(BaseSettings):
    app_name: str = "K8s LLM Job"
    llm_provider: Provider = Provider.OPENAI
    llm_fake_mode: bool = True

    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2.5:0.5b"

    kserve_base_url: str = "http://vllm-predictor.default.svc.cluster.local/v1"
    kserve_model: str = "Qwen/Qwen2.5-0.5B-Instruct"
    llm_timeout_seconds: float = 60.0

    minio_endpoint: str = "http://localhost:9000"
    minio_console_url: str = "http://localhost:9001"
    minio_access_key: SecretStr = SecretStr("minioadmin")
    minio_secret_key: SecretStr = SecretStr("minioadmin")
    minio_bucket: str = "k8s-llm-job"
    minio_secure: bool = False
    upload_max_bytes: int = 10 * 1024 * 1024
    allowed_upload_mime_types: tuple[str, ...] = Field(
        default=("application/pdf", "text/csv", "application/csv", "application/vnd.ms-excel")
    )
    minio_connect_timeout_seconds: float = 3.0
    minio_read_timeout_seconds: float = 10.0
    minio_max_attempts: int = 2
    max_concurrent_jobs: int = 5

    grafana_url: str | None = None

    job_execution_mode: JobExecutionMode = JobExecutionMode.LOCAL
    worker_image_pdf: str = "k8s-llm-job-worker-pdf:local"
    worker_image_tabular: str = "k8s-llm-job-worker-tabular:local"
    kubernetes_namespace: str = "default"
    job_ttl_seconds_after_finished: int = 600
    worker_poll_timeout_seconds: int = 300
    job_name_prefix: str = "k8s-llm-job-wk-"
    worker_cpu_request: str = "100m"
    worker_cpu_limit: str = "1"
    worker_memory_request: str = "256Mi"
    worker_memory_limit: str = "1Gi"
    # When true, use in-cluster service account (worker pods in cluster)
    backend_kubernetes_in_cluster: bool = False
    kubeconfig_path: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="APP_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
