.PHONY: demo up down load-test lint typecheck test \
        build-backend build-worker-pdf build-worker-tabular build-images \
        kind-up kind-down

demo:
	pwsh -File scripts/demo.ps1

up:
	pwsh -File scripts/up.ps1

down:
	pwsh -File scripts/down.ps1

kind-up:
	pwsh -File scripts/up.ps1 -Mode kind

kind-down:
	pwsh -File scripts/down.ps1 -Mode kind

load-test:
	pwsh -File scripts/load-test.ps1

lint:
	uv run ruff check .

typecheck:
	uv run pyright

test:
	uv run pytest

build-backend:
	docker build -f backend/Dockerfile -t cern-ml-demo-backend:local .

build-worker-pdf:
	docker build -f workers/pdf/Dockerfile -t cern-ml-demo-worker-pdf:local .

build-worker-tabular:
	docker build -f workers/tabular/Dockerfile -t cern-ml-demo-worker-tabular:local .

build-images: build-backend build-worker-pdf build-worker-tabular
