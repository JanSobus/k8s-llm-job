# Build from repo root: docker build -f workers/pdf/Dockerfile -t cern-ml-demo-worker-pdf:local .
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_LINK_MODE=copy
ENV PYTHONPATH=/app
COPY pyproject.toml uv.lock ./
COPY backend ./backend
COPY workers ./workers
RUN uv sync --frozen --no-dev
CMD ["python", "-m", "workers.pdf.main"]
