# NLH Trainer — Slim Distribution Contents

This document describes what’s included in the **allowlisted** distribution zip produced by:

```bash
python tools/build_dist.py --include-file dist-include.txt --out-dir dist

Output artifact: dist/nlh-trainer-<shortsha>.zip
Size: small (~60–100 KiB depending on commit)
Source of truth for packaging: dist-include.txt (allowlist-only)

Why an allowlist?

Predictable & tiny: Only ship what’s needed to run the backend and read docs.

Safe for CI: No vendored deps, caches, or virtualenvs.

Reproducible: Packaging is deterministic from an explicit list.

Included (high-level)

The exact list is defined in dist-include.txt. Current highlights:

Runtime backend code

backend/ (API, models, adapters wiring, logger/DB, scripts)

adapters/ (engine adapters; PokerKit stub used for M0/M1 tests)

Documentation

docs/ (API contract, state schema, runbook, policy notes)

docs/examples/ (live-captured JSON/CSV example payloads)

Top-level metadata & entrypoints

README.md, LICENSE (if present), Makefile

requirements.txt (includes -r backend/requirements.txt)

backend/requirements.txt (runtime+tests; CI may install tests separately)

Note: backend/scripts/autoplay.py is included for headless runs.

Excluded by design

To keep the archive lean and avoid surprises:

Development environments & caches:

.venv/, node_modules/, __pycache__/, .pytest_cache/

VCS & build artifacts:

.git/, any dist/ contents, coverage files

Large or vendored code:

third_party/ (if present)

Test suites:

backend/tests/ (tests run from the repository, not from the dist zip)

Tooling not needed inside the zip:

tools/build_dist.py, dist-include.txt