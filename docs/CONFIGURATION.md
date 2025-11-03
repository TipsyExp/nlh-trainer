# CONFIGURATION

This app is a local, single-user NLH training simulator. Third-party engines/evaluators/solvers live **outside** the repo and are accessed via thin adapters. Defaults are chosen so the backend runs out-of-the-box with no extra binaries.

---

## 1) Environment Variables (runtime switches)

> Put these in your shell, a `.env` for your process manager, or export them inline when launching `uvicorn`.

| Key                  | Values                            | Default            | Notes |
|----------------------|-----------------------------------|--------------------|------|
| `ENGINE`             | `PokerKit`                        | `PokerKit`         | Primary gameplay engine (adapter under `adapters/engines/`). |
| `EVALUATOR`          | `PokerKit` \| `HenryRLee`         | `PokerKit`         | Hand/equity evaluator. `HenryRLee` requires `phevaluator`. |
| `LOG_DB_PATH`        | file path                         | `./.data/app.sqlite` | SQLite log DB (sessions, hands, actions, exports). Make sure `.data/` is git-ignored (it is by default). |
| `COACH_ENABLED`      | `true` \| `false`                 | `false`            | **M1+ only.** Gates all solver/coach features. When `false`, coach codepaths remain inert. |
| `TEXASSOLVER_PATH`   | absolute path to executable       | *(unset)*          | **M1+ only.** Required iff `COACH_ENABLED=true`. Not bundled; user supplies locally. |
| `COACH_CACHE_MAX_ROWS` | integer                         | `5000`             | **M1+ only.** Max rows for solver advice cache. |
| `COACH_CACHE_TTL_DAYS` | integer                         | `30`               | **M1+ only.** Consider entries older than this expired. |

**Cross-platform examples:**

**bash/zsh**
```bash
export LOG_DB_PATH="./.data/app.sqlite"
export ENGINE="PokerKit"
export EVALUATOR="PokerKit"
# M1+ (optional):
# export COACH_ENABLED="true"
# export TEXASSOLVER_PATH="/ABS/PATH/TO/TexasSolver"

PowerShell
$env:LOG_DB_PATH = ".\.data\app.sqlite"
$env:ENGINE = "PokerKit"
$env:EVALUATOR = "PokerKit"
# M1+ (optional):
# $env:COACH_ENABLED = "true"
# $env:TEXASSOLVER_PATH = "C:\ABS\PATH\TexasSolver.exe"

2) Engines

Engines are plug-ins under adapters/engines/*.

Primary: PokerKit

Install: pip install pokerkit

Adapter: adapters/engines/pokerkit_adapter.py

Selected by: ENGINE=PokerKit

Rationale: modern, deterministic, actively maintained.

PyPokerEngine is not used in this milestone.

3) Evaluators
Default: PokerKit evaluator

Bundled with PokerKit, no extra setup.

Used for showdown/sanity in current flow.

Optional: HenryRLee

Install: pip install phevaluator

Adapter: adapters/evaluator/pheval_adapter.py

Select with: EVALUATOR=HenryRLee

Use case: cross-checks / experimentation (not required).

4) TexasSolver (Coach, M1+)

We do not bundle TexasSolver (AGPL). When you want coaching:

Set: COACH_ENABLED=true

Provide absolute path: TEXASSOLVER_PATH=/abs/path/to/TexasSolver

Optional cache tuning: COACH_CACHE_MAX_ROWS, COACH_CACHE_TTL_DAYS

If COACH_ENABLED=true but TEXASSOLVER_PATH is missing/invalid, coach endpoints should return 501 Not Implemented. When COACH_ENABLED=false (default), the app runs without any solver.

See also: docs/THIRD-PARTY-INTEGRATION.md, docs/LICENSING-NOTES.md.

5) Backend/Frontend Services

Backend: FastAPI + Uvicorn, Pydantic models.

Frontend: Next.js + Tailwind (minimal shell in this milestone).

Storage: SQLite at LOG_DB_PATH for logs; JSON/CSV export endpoints for analysis.

Install deps from the repo root: the top-level requirements.txt includes/transitively references backend requirements.

6) Determinism & Seeding

Determinism is per session, not via a global env var.

Create/reset a session with POST /api/session?base_seed=YOUR-SEED.

Each hand derives a deck_seed from the base seed; exports include enough to replay deterministically.

Replaying with the same base_seed and the same first-action rule yields identical canonical outcomes (see docs/RUNBOOK.md and tests).

7) Distribution (slim .zip)

CI produces a slim source archive (dist/*.zip) via tools/build_dist.py and the allowlist in dist-include.txt.

Contents: our source only. No third-party sources, no solver binaries.

After unzip: pip install -r requirements.txt to fetch Python deps.