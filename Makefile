.PHONY: demo up down load-test lint typecheck test build-worker-pdf build-worker-tabular

demo:
	pwsh -File scripts/demo.ps1

up:
	pwsh -File scripts/up.ps1

down:
	pwsh -File scripts/down.ps1

load-test:
	pwsh -File scripts/load-test.ps1

lint:
	uv run ruff check .

typecheck:
	uv run pyright

test:
	uv run pytest

# Optional: build images for APP_JOB_EXECUTION_MODE=kubernetes
build-worker-pdf:
	docker build -f workers/pdf/Dockerfile -t cern-ml-demo-worker-pdf:local .

build-worker-tabular:
	docker build -f workers/tabular/Dockerfile -t cern-ml-demo-worker-tabular:local .
