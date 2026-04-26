ifeq ($(OS),Windows_NT)
SCRIPT_DEMO = pwsh -File scripts/demo.ps1
SCRIPT_UP = pwsh -File scripts/up.ps1
SCRIPT_DOWN = pwsh -File scripts/down.ps1
SCRIPT_KIND_UP = pwsh -File scripts/up.ps1 -Mode kind
SCRIPT_KIND_UP_KSERVE = pwsh -File scripts/up.ps1 -Mode kind -WithKServe
SCRIPT_KIND_DOWN = pwsh -File scripts/down.ps1 -Mode kind
SCRIPT_LOAD_TEST = pwsh -File scripts/load-test.ps1
else
SCRIPT_DEMO = bash scripts/demo.sh
SCRIPT_UP = bash scripts/up.sh
SCRIPT_DOWN = bash scripts/down.sh
SCRIPT_KIND_UP = bash scripts/up.sh --mode kind
SCRIPT_KIND_UP_KSERVE = bash scripts/up.sh --mode kind --with-kserve
SCRIPT_KIND_DOWN = bash scripts/down.sh --mode kind
SCRIPT_LOAD_TEST = bash scripts/load-test.sh
endif

.PHONY: demo up down load-test smoke-context lint typecheck test \
        build-backend build-worker-pdf build-worker-tabular build-images \
        kind-up kind-up-kserve kind-down \
        demo-ps up-ps down-ps kind-up-ps kind-up-kserve-ps kind-down-ps load-test-ps \
        demo-sh up-sh down-sh kind-up-sh kind-up-kserve-sh kind-down-sh load-test-sh

demo:
	$(SCRIPT_DEMO)

up:
	$(SCRIPT_UP)

down:
	$(SCRIPT_DOWN)

kind-up:
	$(SCRIPT_KIND_UP)

kind-up-kserve:
	$(SCRIPT_KIND_UP_KSERVE)

kind-down:
	$(SCRIPT_KIND_DOWN)

load-test:
	$(SCRIPT_LOAD_TEST)

demo-ps:
	pwsh -File scripts/demo.ps1

up-ps:
	pwsh -File scripts/up.ps1

down-ps:
	pwsh -File scripts/down.ps1

kind-up-ps:
	pwsh -File scripts/up.ps1 -Mode kind

kind-up-kserve-ps:
	pwsh -File scripts/up.ps1 -Mode kind -WithKServe

kind-down-ps:
	pwsh -File scripts/down.ps1 -Mode kind

load-test-ps:
	pwsh -File scripts/load-test.ps1

demo-sh:
	bash scripts/demo.sh

up-sh:
	bash scripts/up.sh

down-sh:
	bash scripts/down.sh

kind-up-sh:
	bash scripts/up.sh --mode kind

kind-up-kserve-sh:
	bash scripts/up.sh --mode kind --with-kserve

kind-down-sh:
	bash scripts/down.sh --mode kind

load-test-sh:
	bash scripts/load-test.sh

smoke-context:
	uv run --all-extras python scripts/test_context_injection.py

lint:
	uv run ruff check .

typecheck:
	uv run pyright

test:
	uv run pytest

build-backend:
	docker build -f backend/Dockerfile -t k8s-llm-job-backend:local .

build-worker-pdf:
	docker build -f workers/pdf/Dockerfile -t k8s-llm-job-worker-pdf:local .

build-worker-tabular:
	docker build -f workers/tabular/Dockerfile -t k8s-llm-job-worker-tabular:local .

build-images: build-backend build-worker-pdf build-worker-tabular
