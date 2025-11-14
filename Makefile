# NLH Training Simulator — Makefile
#
# Convenience targets for dev, tests, autoplay, docs examples, and slim dist.

.PHONY: api web dev install-backend install-frontend install-optional \
        test test-backend test-frontend lint fmt autoplay docs-examples \
        equity dist dist-clean

# Choose the Python and Node entry points (Windows-friendly)
PY    ?= python
NODE  ?= npm

# Backend dev server options
API_ADDR     ?= 127.0.0.1
API_PORT     ?= 8000
UVICORN_OPTS ?= --reload --host $(API_ADDR) --port $(API_PORT)

##
## Launch the FastAPI backend in development mode
##
api:
	@echo "Starting backend on http://$(API_ADDR):$(API_PORT) …"
	$(PY) -m uvicorn backend.main:app $(UVICORN_OPTS)

##
## Launch the Next.js frontend in development mode
##
web:
	@echo "Starting frontend on http://localhost:3000 …"
	cd frontend && $(NODE) run dev

##
## Start both backend and frontend (parallel)
##
dev:
	@echo "Starting backend + frontend …"
	@$(MAKE) -j2 api web

##
## Install dependencies
##
install-backend:
	$(PY) -m pip install -r backend/requirements.txt

install-frontend:
	cd frontend && $(NODE) install

# Optional extras (e.g., pbots_calc for range equities)
install-optional:
	@if [ -f backend/requirements-optional.txt ]; then \
		$(PY) -m pip install -r backend/requirements-optional.txt ; \
	else \
		echo "No backend/requirements-optional.txt found."; \
	fi

##
## Tests & quality
##
test-backend:
	$(PY) -m pytest -q backend/tests

test-frontend:
	cd frontend && $(NODE) test -- --passWithNoTests

test: test-backend test-frontend

lint:
	ruff check .
	mypy backend

fmt:
	ruff check . --fix
	black .

##
## Autoplay a small sample (headless)
## Usage: make autoplay N=100 SEED=autoplay SEATS=2 SB=50 BB=100
##
autoplay:
	@echo "Running autoplay…"
	@if [ -f backend/scripts/autoplay.py ]; then \
		$(PY) backend/scripts/autoplay.py --hands $${N:-100} --seed $${SEED:-autoplay} --seats $${SEATS:-2} --sb $${SB:-50} --bb $${BB:-100}; \
	else \
		echo "autoplay script not found: backend/scripts/autoplay.py"; \
		exit 1; \
	fi

##
## Re-capture docs/examples from the live API (deterministic env)
##
docs-examples:
	@echo "Capturing docs/examples via docs/scripts/capture_examples.py …"
	COACH_ENABLED=false PYTHONHASHSEED=0 $(PY) docs/scripts/capture_examples.py
	@echo "Done. Check docs/examples/"

##
## Equity helper (hands or ranges via equity_cli)
## Examples:
##   make equity HANDS='AhAd,KhQh' BOARD='AsKd2c' EXACT=1
##   make equity RANGES='JJ+,random' ITERS=50000
##
equity:
	@echo "Equity helper…"
	@if [ -n "$$HANDS" ]; then \
		set -e; \
		h1=$$(echo $$HANDS | cut -d, -f1); \
		h2=$$(echo $$HANDS | cut -d, -f2); \
		$(PY) -m backend.scripts.equity_cli --hand $$h1 --hand $$h2 --board "$${BOARD:-}" --dead "$${DEAD:-}" $$( [ "$${EXACT:-}" = "1" ] && echo --exact ); \
	elif [ -n "$$RANGES" ]; then \
		r1=$$(echo $$RANGES | cut -d, -f1); \
		r2=$$(echo $$RANGES | cut -d, -f2); \
		$(PY) -m backend.scripts.equity_cli --range "$$r1" --range "$$r2" --iters "$${ITERS:-20000}"; \
	else \
		echo "Provide HANDS='AhAd,KhQh' or RANGES='JJ+,random' (see comments)."; \
		exit 2; \
	fi

##
## Build a slim distribution zip using allowlist-only includes
##
dist:
	@echo "Building allowlisted distribution…"
	$(PY) tools/build_dist.py --include-file dist-include.txt --out-dir dist

##
## Clean distribution artifacts
##
dist-clean:
	rm -rf dist
	@echo "Cleaned dist/"
