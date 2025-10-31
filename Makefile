## Makefile for NLH Training Simulator (M1)
#
# Convenience targets for dev, tests, autoplay, and building a slim dist.

.PHONY: api web test autoplay dist dist-clean

# Choose the Python entry (Windows-friendly)
PY ?= python

##
## Launch the FastAPI backend in development mode
##
api:
	@echo "Starting backend on http://localhost:8000 …"
	$(PY) -m uvicorn backend.main:app --reload

##
## Launch the Next.js frontend in development mode
##
web:
	@echo "Starting frontend on http://localhost:3000 …"
	cd frontend && npm run dev

##
## Run backend + frontend tests
##
test:
	@echo "Running backend tests…"
	$(PY) -m pytest -q backend/tests
	@echo "Running frontend tests…"
	cd frontend && npm test -- --passWithNoTests

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
## Build a slim distribution zip using allowlist-only includes
##
dist:
	@echo "Creating slim distribution zip (allowlist)…"
	@$(PY) tools/build_dist.py --include-file dist-include.txt --out-dir dist

##
## Clean distribution artifacts
##
dist-clean:
	@rm -rf dist
	@echo "Cleaned dist/"

.PHONY: dist dist-clean

dist-clean:
	@echo "Cleaning dist/…"
	@python - <<'PY'
import shutil, os
shutil.rmtree("dist", ignore_errors=True)
print("OK")
PY

dist:
	@echo "Building allowlisted distribution…"
	@python tools/build_dist.py --include-file dist-include.txt --out-dir dist
