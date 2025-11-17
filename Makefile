# NLH Training Simulator — Makefile
#
# Convenience targets for dev, tests, autoplay, docs examples, and slim dist.

.PHONY: api web dev install-backend install-frontend install-optional \
        test test-backend test-frontend lint fmt autoplay docs-examples \
        equity bench-equity build-ompeval dist dist-clean

# Choose the Python and Node entry points (Windows-friendly)
PY    ?= python
NODE  ?= npm

# Backend dev server options
API_ADDR     ?= 127.0.0.1
API_PORT     ?= 8000
UVICORN_OPTS ?= --reload --host $(API_ADDR) --port $(API_PORT)

# Default benchmark policies (override with: POLICIES=auto,ompeval,eval7)
POLICIES ?= auto,ompeval,eval7,pokerkit

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
	$(NODE) --prefix frontend run dev

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
	$(NODE) --prefix frontend install

# Optional extras (e.g., eval7 + pybind11 for OMPEval build) — PowerShell-safe
install-optional:
	@$(PY) - <<'PY'
import os, sys, subprocess
p = "backend/requirements-optional.txt"
if os.path.isfile(p):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", p])
else:
    print("No backend/requirements-optional.txt found.")
PY

##
## Build OMPEval native extension (cross-platform launcher)
## - On Linux/macOS: uses scripts/build_ompeval.sh
## - On Windows: uses scripts/build_ompeval.ps1 (run from PowerShell)
##
build-ompeval:
	@$(PY) - <<'PY'
import os, sys, subprocess, platform, shutil
root = os.getcwd()
sh = os.path.join("scripts", "build_ompeval.sh")
ps = os.path.join("scripts", "build_ompeval.ps1")
if platform.system() == "Windows":
    if not os.path.isfile(ps):
        print("Missing scripts/build_ompeval.ps1")
        sys.exit(1)
    # Use PowerShell to run the script in a Windows-friendly way
    cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", ps]
else:
    if not os.path.isfile(sh):
        print("Missing scripts/build_ompeval.sh")
        sys.exit(1)
    cmd = ["bash", sh]
subprocess.check_call(cmd, cwd=root)
PY

##
## Tests & quality
##
test-backend:
	$(PY) -m pytest -q backend/tests

test-frontend:
	$(NODE) --prefix frontend test -- --passWithNoTests

test: test-backend test-frontend

lint:
	ruff check .
	mypy backend

fmt:
	ruff check . --fix
	black .

##
## Autoplay a small sample (headless) — PowerShell-safe
## Usage: make autoplay N=100 SEED=autoplay SEATS=2 SB=50 BB=100
##
autoplay:
	@echo "Running autoplay…"
	@$(PY) - <<'PY'
import os, sys, subprocess
script = os.path.join("backend", "scripts", "autoplay.py")
if not os.path.isfile(script):
    print("autoplay script not found:", script)
    sys.exit(1)
N     = os.environ.get("N", "100")
SEED  = os.environ.get("SEED", "autoplay")
SEATS = os.environ.get("SEATS", "2")
SB    = os.environ.get("SB", "50")
BB    = os.environ.get("BB", "100")
args = [sys.executable, script, "--hands", N, "--seed", SEED, "--seats", SEATS, "--sb", SB, "--bb", BB]
subprocess.check_call(args)
PY

##
## Re-capture docs/examples from the live API (deterministic env) — PowerShell-safe
##
docs-examples:
	@echo "Capturing docs/examples via docs/scripts/capture_examples.py …"
	@$(PY) - <<'PY'
import os, sys, subprocess
env = os.environ.copy()
env["COACH_ENABLED"] = "false"
env["PYTHONHASHSEED"] = "0"
subprocess.check_call([sys.executable, "docs/scripts/capture_examples.py"], env=env)
print("Done. Check docs/examples/")
PY

##
## Equity helper (hands or ranges via equity_cli) — PowerShell-safe
## Examples:
##   make equity HANDS='AhAd,KhQh' BOARD='AsKd2c' EXACT=1
##   make equity RANGES='JJ+,random' ITERS=50000
##
equity:
	@echo "Equity helper…"
	@$(PY) - <<'PY'
import os, sys, subprocess
hands  = os.environ.get("HANDS", "").strip()
ranges = os.environ.get("RANGES", "").strip()
board  = os.environ.get("BOARD", "")
dead   = os.environ.get("DEAD", "")
exact  = os.environ.get("EXACT", "")
iters  = os.environ.get("ITERS", "")

cmd = [sys.executable, "-m", "backend.scripts.equity_cli"]

if hands:
    parts = [p.strip() for p in hands.split(",") if p.strip()]
    if len(parts) < 2:
        print("HANDS must contain at least two comma-separated hands, e.g. AhAd,KhQh")
        sys.exit(2)
    for h in parts:
        cmd += ["--hand", h]
    if board:
        cmd += ["--board", board]
    if dead:
        cmd += ["--dead", dead]
    if exact == "1":
        cmd += ["--exact"]
elif ranges:
    parts = [p.strip() for p in ranges.split(",") if p.strip()]
    if len(parts) < 2:
        print("RANGES must contain at least two comma-separated ranges, e.g. JJ+,random")
        sys.exit(2)
    for r in parts:
        cmd += ["--range", r]
    if iters:
        cmd += ["--iters", iters]
else:
    print("Provide HANDS='AhAd,KhQh' or RANGES='JJ+,random' (see target comments).")
    sys.exit(2)

subprocess.check_call(cmd)
PY

##
## Equity benchmark (tiny matrix; CSV output)
## Examples:
##   make bench-equity
##   make bench-equity OUT=bench_equity.csv POLICIES=auto,ompeval,eval7
##
bench-equity:
	@echo "Running equity benchmark…"
ifeq ($(strip $(OUT)),)
	$(PY) -m backend.scripts.benchmark_equity --policies "$(POLICIES)"
else
	$(PY) -m backend.scripts.benchmark_equity --policies "$(POLICIES)" --out "$(OUT)"
endif

##
## Build a slim distribution zip using allowlist-only includes
##
dist:
	@echo "Building allowlisted distribution…"
	$(PY) tools/build_dist.py --include-file dist-include.txt --out-dir dist

##
## Clean distribution artifacts — PowerShell-safe
##
dist-clean:
	@$(PY) - <<'PY'
import shutil
shutil.rmtree("dist", ignore_errors=True)
print("Cleaned dist/")
PY
