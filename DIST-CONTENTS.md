# NLH Trainer — Slim Distribution Contents
This document describes what’s included in the allowlisted zip produced by the slim distribution build.

Build
python tools/build_dist.py --include-file dist-include.txt --out-dir dist

•	Output artifact: dist/nlh-trainer-<shortsha>.zip
•	Size: tiny (~60–100 KiB, commit-dependent)
•	Source of truth: dist-include.txt (explicit allowlist)
________________________________________
Why an allowlist?
•	Predictable & tiny: Only ship what’s needed to run the backend and read docs.
•	Safe for CI: No vendored deps, caches, or virtualenvs.
•	Reproducible: Packaging is deterministic from the explicit list.
________________________________________
What’s included (high-level)
Exact files are enumerated in dist-include.txt. Typical highlights:
Runtime backend code
•	backend/ – API, models, adapters wiring, logger/DB, minimal scripts
•	adapters/ – engine adapters (PokerKit used for M0/M1 tests)
Documentation
•	docs/ – API contract, state schema, bet trees, configuration, debugging, policy notes, runbook, QA
•	docs/examples/ – canonical JSON/CSV example payloads (generated deterministically by docs/scripts/capture_examples.py in the repo; the script itself is not required inside the zip)
Top-level metadata & entry points
•	README.md, LICENSE (if present), Makefile
•	backend/requirements.txt (runtime deps)
•	requirements.txt (if present; may include -r backend/requirements.txt)
Note: backend/scripts/autoplay.py is included for headless runs if referenced by dist-include.txt.
________________________________________
What’s excluded (by design)
To keep the archive lean and avoid surprises:
Development environments & caches
•	.venv/, node_modules/, __pycache__/, .pytest_cache/
VCS & build artifacts
•	.git/, any dist/ contents, coverage files, editor configs
Large or vendored code
•	third_party/ (if present) unless explicitly allowlisted
Test suites & CI only assets
•	backend/tests/, .github/ workflows, CI helpers
Tooling not needed at runtime
•	tools/build_dist.py, dist-include.txt, docs/scripts/* (only the outputs under docs/examples/ are included)
Frontend
•	frontend/ (Next.js) is intentionally not included in the slim backend zip
________________________________________
Verifying a build
List the archive contents:
unzip -l dist/nlh-trainer-<shortsha>.zip

Smoke run the backend from the zip:
unzip dist/nlh-trainer-<shortsha>.zip -d /tmp/nlh-trainer
cd /tmp/nlh-trainer
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8000

Docs examples & CI drift
•	Canonical examples live in docs/examples/* and are deterministic.
•	CI runs Docs Examples Drift; if it fails, regenerate locally:
python docs/scripts/capture_examples.py
git add docs/examples
git commit -m "docs: refresh examples"

The distribution zip includes the generated examples, not the generator script.
________________________________________
Maintaining the allowlist
When adding runtime code or docs that should be shipped:
1.	Update dist-include.txt with the new paths.
2.	Ensure backend/requirements.txt reflects any dependency changes.
3.	Rebuild the dist zip and verify contents.
If you add dev-only tooling or large assets, keep them out of the allowlist unless strictly required at runtime.
________________________________________
Notes
•	The backend follows total-amount semantics for bet/raise sizing and exposes pre-bot snapshots in action responses; see docs/API-CONTRACT.md, docs/STATE-SCHEMA.md, and docs/BET-TREES.md.
•	Debug endpoints and SSE are documented in docs/debugging.md and are optional at runtime.
