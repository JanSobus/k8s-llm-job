# Build from repo root: docker build -f backend/Dockerfile -t k8s-llm-job-backend:local .
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_LINK_MODE=copy
ENV PYTHONPATH=/app
ENV PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock ./
COPY backend ./backend
RUN uv sync --frozen --no-dev --extra backend
EXPOSE 8000
CMD ["uv", "run", "--frozen", "--no-dev", "--extra", "backend", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
