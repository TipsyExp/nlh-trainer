
---

# docs/CONFIGURATION.md

```markdown
# CONFIGURATION

The app is a local, single-user NLH training simulator. Third-party engines/evaluators
live outside the repo behind thin adapters. Defaults are chosen so the backend runs
out-of-the-box with no extra binaries.

---

## 1) Environment Variables (runtime switches)

> Put these in your shell, a `.env`, or export inline when launching `uvicorn`.

| Key                     | Values                      | Default              | Notes |
|-------------------------|-----------------------------|----------------------|-------|
| `ENGINE`                | `PokerKit`                  | `PokerKit`           | Primary gameplay engine (adapter under `adapters/engines/`). |
| `EVALUATOR`             | `PokerKit` \| `HenryRLee`   | `PokerKit`           | Hand/equity evaluator. `HenryRLee` requires `phevaluator`. |
| `LOG_DB_PATH`           | file path                   | `./.data/app.sqlite` | SQLite log DB (sessions, hands, actions, exports). `.data/` is git-ignored. |
| `BOT_PROFILE`           | `CALLCHECK` \| `TAG`        | `CALLCHECK`          | **Bot policy select.** Default keeps legacy check/call behavior. |
| `COACH_ENABLED`         | `true` \| `false`           | `false`              | **Future.** Gates solver/coach codepaths. |
| `TEXASSOLVER_PATH`      | absolute path               | *(unset)*            | **Future.** Required iff `COACH_ENABLED=true`. Not bundled. |
| `COACH_CACHE_MAX_ROWS`  | integer                     | `5000`               | **Future.** Solver advice cache size. |
| `COACH_CACHE_TTL_DAYS`  | integer                     | `30`                 | **Future.** Solver cache TTL. |

**bash/zsh**
```bash
export LOG_DB_PATH="./.data/app.sqlite"
export ENGINE="PokerKit"
export EVALUATOR="PokerKit"
# Optional bot profile:
# export BOT_PROFILE="TAG"
# Future (coach):
# export COACH_ENABLED="true"
# export TEXASSOLVER_PATH="/ABS/PATH/TO/TexasSolver"

PowerShell
$env:LOG_DB_PATH = ".\.data\app.sqlite"
$env:ENGINE = "PokerKit"
$env:EVALUATOR = "PokerKit"
# Optional bot profile:
# $env:BOT_PROFILE = "TAG"
# Future (coach):
# $env:COACH_ENABLED = "true"
# $env:TEXASSOLVER_PATH = "C:\ABS\PATH\TexasSolver.exe"

2) Engines

Engines are plug-ins under adapters/engines/*.

Primary: PokerKit

Install: pip install pokerkit

Adapter: adapters/engines/pokerkit_adapter.py

Select: ENGINE=PokerKit

PyPokerEngine is not used in this milestone.

3) Evaluators

Default: PokerKit evaluator (bundled with PokerKit)
Used for showdown/sanity in current flow.

Optional: HenryRLee (phevaluator)

Install: pip install phevaluator

Adapter: adapters/evaluator/pheval_adapter.py

Select: EVALUATOR=HenryRLee

4) Bot Profiles

CALLCHECK (default): deterministic check/call only; used by tests and docs/examples.

TAG (opt-in):

Preflop: integrates with backend/policy/range_manager.py to select fold/call/raise buckets deterministically.

Postflop (thin slice): if IP + first action on street + to_call==0, stabs with the smallest simple Nx bucket; else check/call.

Deterministic via a stable RNG seeded from session/hand/action context.

Enable TAG with:
export BOT_PROFILE=TAG

or on Windows PowerShell:
$env:BOT_PROFILE = "TAG"

5) Determinism & Seeding

Determinism is per session via base_seed when calling POST /api/session.

Each hand derives a deck_seed from the base_seed.

Bot decisions (for either profile) use a stable RNG:
seed_components = [base_seed, session_id, hand_id, decision_idx, bot_seat, "bot"]

ensuring identical decisions with the same seed and path.

Exports include enough info to replay deterministically.

6) Storage & Exports

SQLite at LOG_DB_PATH for sessions, hands, and actions.

Every action is indexed and a hands snapshot is upserted after each action.

JSON/CSV exports are available via the /api/export/* endpoints.

7) Services

Backend: FastAPI + Uvicorn, Pydantic models.

Frontend: (Optional) Next.js + Tailwind (minimal shell).

Install: use root requirements.txt.

8) Distribution (slim .zip)

CI can produce a slim source archive (dist/*.zip) including repo source only
(no third-party sources or solver binaries).

After unzip:
pip install -r requirements.txt
to fetch Python deps.

9) TexasSolver adapter settings

- COACH_ENABLED=true            # gate for calling external solver
- TEXASSOLVER_PATH=/abs/path/to/console_solver(.exe)

Tuning (deterministic by default):
- COACH_TS_THREADS=1            # threads for solver; 1 keeps results stable
- COACH_TS_ACCURACY=1.0         # smaller => slower, more accurate
- COACH_TS_MAX_ITERS=200        # iteration cap for quick goldens
- COACH_TS_TIMEOUT_S=90         # subprocess timeout seconds

10) Coach / Solver Configuration
Enabling
•	Set COACH_ENABLED=true to turn on coach routes and logic.
•	With COACH_ENABLED=false (default), coach endpoints return 501 with {"meta":{"status":"disabled"}}.
Solver path
•	When enabled and hitting nodes that require solving, set:
o	TEXASSOLVER_PATH to an absolute path to the TexasSolver console binary (e.g., C:\path\to\console_solver.exe on Windows).
•	If the binary is missing/invalid, solver calls will fail; endpoints may surface "unsupported" or "disabled" depending on the code path.
Supported spots (Task-17)
•	Heads-up postflop only:
o	Single-raised pots (SRP)
o	3-bet pots (3BP)
•	Preflop and multi-way are intentionally unsupported and return 501 with {"meta":{"status":"unsupported"}}.
Tuning / determinism
•	Optional environment variables:
o	COACH_TS_THREADS (default 1)
o	COACH_TS_ACCURACY (default 1.0)
o	COACH_TS_MAX_ITERS (default 200)
o	COACH_TS_TIMEOUT_S (default 90) → exceeded time yields 504 with {"meta":{"status":"timeout"}}.
CI posture
•	CI runs with COACH_ENABLED=false. No solver is required and coach paths are inert.

11) Coach / Solver
| Variable           | Type   | Default | Description                                                                                                    |
| ------------------ | ------ | ------- | -------------------------------------------------------------------------------------------------------------- |
| `COACH_ENABLED`    | bool   | `false` | Enables coach endpoints. When `false`, API returns `501 disabled`.                                             |
| `TEXASSOLVER_PATH` | string | —       | Filesystem path to the solver binary used by `TexasSolverAdapter`. Required when coach is enabled and solving. |

Implementation notes

Cache storage: SQLite table solver_cache(node_key TEXT PRIMARY KEY, payload_json TEXT NOT NULL, created_at TEXT NOT NULL) is created automatically.

node_key: SHA-256 over canonical node JSON. Includes SHA-256 of ip_range and oop_range to keep keys compact.

Changing solver knobs (COACH_TS_THREADS, COACH_TS_ACCURACY, COACH_TS_MAX_ITERS) does not alter the node_key. If you need to refresh advice after such changes, lower COACH_CACHE_TTL_DAYS temporarily or clear the table.

Optional solver knobs
| Variable             | Type | Default | Effect                                                                          |
| -------------------- | ---- | ------- | ------------------------------------------------------------------------------- |
| `COACH_TS_THREADS`   | int  | `1`     | Passed through to the adapter; can be set by warm-cache script via `--threads`. |
| `COACH_TS_ACCURACY`  | str  | `1.0`   | Adapter-specific target accuracy (if supported).                                |
| `COACH_TS_MAX_ITERS` | str  | `200`   | Adapter-specific iteration cap (if supported).                                  |

12) Configuration

Set env vars in your shell or copy `.env.example` → `.env` (backend) and `frontend/.env.example` → `frontend/.env.local`.

## Backend

- `COACH_ENABLED` (default `false`)
  - `false`: `/api/coach/advice` returns `501` with a disabled payload.
  - UI maps this to “Coach off/disabled”.

- `BOT_MODE` = `none` | `heuristic` | `rlcard` (default `heuristic`)
  - `none`: no autoplay; you must act for all seats.
  - `heuristic`: built-in policy (CALLCHECK or TAG via `BOT_PROFILE`).
  - `rlcard`: enables the RLCard bridge (placeholder implemented). If the bridge is slow or returns invalid actions, backend safely degrades to check/call.

- `BOT_PROFILE` = `CALLCHECK` | `TAG` (default `CALLCHECK`)
  - Profile for the heuristic bot.

- `BOT_TIME_BUDGET_MS` (default `150`)
  - Per-decision timeout. On timeout/error, backend applies a safe fallback (check/call).

- `HAND_AUTO_ENABLED` = `true|false` (default `false`)
  - Gates dev endpoint `POST /api/hand/auto`. Leave `false` in prod.

- `RLCARD_MODEL_PATH` (optional)
  - Path to model/assets for RLCard mode.

## Frontend

- `NEXT_PUBLIC_API_BASE` (default `http://127.0.0.1:8000`)
  - Backend origin.

- `NEXT_PUBLIC_ENABLE_HAND_AUTO` = `true|false` (default `false`)
  - When `true`, UI will call `POST /api/hand/auto` during bot sequences (dev only).
  - Regardless of this flag, UI **polls** `/api/hand/state` until it’s your turn or showdown.

- `NEXT_PUBLIC_DEV_TOOLS` = `true|false` (default `false`)
  - Shows additional dev UI (e.g., “Copy state” button).

## Typical Setups

**Local dev (with auto-step & dev tools):**
```env
# backend/.env
COACH_ENABLED=false
BOT_MODE=heuristic
BOT_PROFILE=TAG
BOT_TIME_BUDGET_MS=150
HAND_AUTO_ENABLED=true

# frontend/.env.local
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000
NEXT_PUBLIC_ENABLE_HAND_AUTO=true
NEXT_PUBLIC_DEV_TOOLS=true

13) Production

# backend/.env
COACH_ENABLED=false
BOT_MODE=heuristic
BOT_PROFILE=CALLCHECK
BOT_TIME_BUDGET_MS=150
HAND_AUTO_ENABLED=false

# frontend/.env
NEXT_PUBLIC_API_BASE=https://your.api.host
NEXT_PUBLIC_ENABLE_HAND_AUTO=false
NEXT_PUBLIC_DEV_TOOLS=false
