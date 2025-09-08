## Makefile for NLH Training Simulator (M0)
#
# This Makefile exposes a handful of convenience targets for
# working on the NLH simulator. These targets are used by the
# continuous integration configuration to lint, type‑check and
# test the backend and frontend.  Additional targets can be added
# as subsequent milestones require.

.PHONY: api web test autoplay dist

##
## Launch the FastAPI backend in development mode
##
api:
	@echo "Starting backend on http://localhost:8000 …"
	python3 -m uvicorn backend.main:app --reload

##
## Launch the Next.js frontend in development mode
##
web:
	@echo "Starting frontend on http://localhost:3000 …"
	cd frontend && npm run dev

##
## Run the Python and JavaScript test suites
##
test:
	@echo "Running backend tests…"
	python3 -m pytest -q backend/tests
	@echo "Running frontend tests…"
	cd frontend && npm test -- --passWithNoTests

##
## Placeholder autoplay target
##
autoplay:
	@echo "Autoplay is not implemented in M0."

##
## Build a slim distribution archive of the source tree
##
dist:
	@echo "Creating distribution zip…"
	@rm -rf dist && mkdir -p dist
	@# Exclude virtual environments, node_modules, caches, Git internals and large artifacts
	zip -rq dist/nlh_trainer_source.zip . \
		-x "*/.venv/*" \
		-x "*/node_modules/*" \
		-x "*/__pycache__/*" \
		-x "*.git/*" \
		-x "*.pytest_cache/*" \
		-x "dist/*" \
		-x "*.zip" 
	@echo "Distribution created at dist/nlh_trainer_source.zip"