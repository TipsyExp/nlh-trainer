
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
