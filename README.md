NLH Trainer  
A no-limit hold’em training simulator with a FastAPI backend and a Next.js frontend.

Current focus: Milestone M2 – pluggable equity service, preflop advisor (charts + rules), clean exports, and CI matrix for optional deps.

Milestone M0/M1 delivered a fully playable engine and UI (no solver), clear API semantics, deterministic examples, and tight CI.

________________________________________
Features

• FastAPI backend with clean HTTP API  
• Next.js frontend (Tailwind) with modern UI  
• Total-amount bet sizing (not deltas) with bucket snapping  
• Pre-bot snapshot in action responses + `bots_applied` list  
• Auto-advance gating via `HAND_AUTO_ENABLED` (returns 501 when disabled)  
• Structured debug events (SSE) + export bundles (hand/session/events)  
• Deterministic docs examples regeneration with drift-check in CI  

M2 equity / preflop features:

• Pluggable equity service with multiple backends (pure-Python PokerKit fallback, optional pbots_calc and Henry native evaluator)  
• Equity exposed via `POST /api/equity` (hands or ranges, exact or Monte-Carlo, multi-backend, multiway with pbots)  
• Chart-driven preflop advisor with rule / equity fallback via `GET /api/coach/preflop`  
• Optional per-action snapshots (`equity_snapshot`, `preflop_advice`) included in JSON exports when logging is enabled  
• Tiny equity benchmark harness (`backend/scripts/benchmark_equity.py`) and pbots-enabled CI job (non-gating) that uploads CSV artifacts for inspection  

See the docs in `docs/` for details (API contract, state schema, bet trees, equity service, preflop advisor, configuration, debugging, QA, etc.).

________________________________________
Prerequisites

• Python ≥ 3.12  
• Node.js ≥ 20 (LTS recommended), npm ≥ 10  

________________________________________
Quick Start

1) Backend setup

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell
# .\.venv\Scripts\Activate.ps1

pip install -r backend/requirements.txt

Start it:

# via Makefile (recommended)
make api  # FastAPI on http://127.0.0.1:8000

# or directly
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

Frontend setup

cd frontend
npm install

Start it:

# via Makefile from repo root
make web  # Next.js on http://127.0.0.1:3000

# or directly
npm run dev

Visit http://localhost:3000

Configuration

Backend behavior is driven by environment variables. Common ones:
| Variable                     | Purpose                                                                                            | Typical dev                      |
| ---------------------------- | -------------------------------------------------------------------------------------------------- | -------------------------------- |
| `HAND_AUTO_ENABLED`          | Enables `/api/hand/auto` and auto-advancing after actions. If false, `/api/hand/auto` returns 501. | `true`                           |
| `BOT_MODE`                   | `"heuristic"` to enable built-in bot, `"none"` to disable.                                         | `heuristic`                      |
| `BOT_PROFILE`                | Policy name (e.g. `TAG`, `CALLCHECK`).                                                             | `TAG`                            |
| `BOT_MAX_STEPS`              | Caps auto-advance loop steps.                                                                      | `100`                            |
| `BOT_TIME_BUDGET_MS`         | Time budget per bot decision.                                                                      | `1000`                           |
| `ENGINE_DEBUG_HTTP`          | Expose debug endpoints/SSE.                                                                        | `true` (dev)                     |
| `LOG_DB_PATH`                | Path to SQLite log DB.                                                                             | `.data/dev.sqlite`               |
| `EQUITY_BACKEND_POLICY`      | Equity backend selection: `auto`, `pokerkit`, `henry`, `pbots`.                                    | `auto`                           |
| `EQUITY_ITERS`               | Default Monte-Carlo iterations for non-exact equity runs.                                          | `20000`                          |
| `EQUITY_SEED`                | Optional RNG seed for deterministic equity MC runs.                                                | `42` (dev)                       |
| `COACH_ENABLED`              | Gate for preflop advisor. When `false`, `/api/coach/preflop` returns 501.                          | `true` (dev), `false` in prod    |
| `PREFLOP_CHART_PATHS`        | Colon/semicolon-separated list of preflop chart files for the coach.                               | `devdata/charts/hu_example.json` |
| `PREFLOP_EQ_DEFEND_THRESH`   | Equity threshold for preflop fallback defend vs fold.                                              | `0.5`                            |
| `LOG_EQUITY_SNAPSHOT`        | When `true`, `/api/equity` calls tied to a hand/index are stored for export.                       | `true` (dev)                     |
| `LOG_PREFLOP_ADVICE`         | When `true`, `/api/coach/preflop` responses are stored for export.                                 | `true` (dev)                     |
| `LOG_EQUITY_SNAPSHOT_REDACT` | When `true`, equity snapshots can be redacted before export.                                       | `true`                           |

Example .env (backend):
ENGINE_DEBUG_HTTP=true
BOT_MODE=heuristic
BOT_PROFILE=TAG
BOT_MAX_STEPS=100
BOT_TIME_BUDGET_MS=1000
HAND_AUTO_ENABLED=true

# Equity service (M2)
EQUITY_BACKEND_POLICY=auto
EQUITY_ITERS=20000
EQUITY_SEED=42

# Preflop advisor (M2)
COACH_ENABLED=true
PREFLOP_CHART_PATHS=devdata/charts/hu_example.json
PREFLOP_EQ_DEFEND_THRESH=0.5

# Snapshot logging (M2)
LOG_EQUITY_SNAPSHOT=true
LOG_PREFLOP_ADVICE=true
LOG_EQUITY_SNAPSHOT_REDACT=true

# Logging DB
LOG_DB_PATH=.data/dev.sqlite

Frontend env (Next.js) in frontend/.env.local:
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000
NEXT_PUBLIC_ENABLE_HAND_AUTO=true
NEXT_PUBLIC_DEV_TOOLS=true

Older variables like ALLOW_DEV_AUTO / MAX_BOT_STEPS are deprecated. Use the ones above.

API Quickstart

All amounts for bet/raise are totals (final commitment), not deltas. Off-tree totals are snapped to nearest legal bucket; responses indicate snapped.

Create a session:

curl -sS -X POST http://127.0.0.1:8000/api/session \
  -H "Content-Type: application/json" \
  -d '{"seats":2,"sb":50,"bb":100,"ante":0,"stacks":[10000,10000],"bot_mode":"heuristic","bot_profile":"TAG"}'

Start a hand:
curl -sS -X POST http://127.0.0.1:8000/api/hand/start

Get state:
curl -sS http://127.0.0.1:8000/api/hand/state

Act (example: open for total 320 = “2.2x” class):
curl -sS -X POST http://127.0.0.1:8000/api/hand/action \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: demo-123" \
  -d '{"seat":0,"action":"bet","amount":320}'

  -d '{"seat":0,"action":"bet","amount":320}'

Auto-advance bots (if gated on):
curl -sS -X POST http://127.0.0.1:8000/api/hand/auto

Exports:

• GET /api/export/hand/{hand_id}.json|.csv
• GET /api/export/session/{session_id}.json|.csv

Debugging (when ENGINE_DEBUG_HTTP=true):

• GET /api/debug/engine/events (SSE). Filter: ?street=flop
• GET /api/debug/engine/bundle (ZIP with events/hand/session)

Tip: include an X-Request-ID header in API calls to correlate with debug events.

Equity & Preflop Quickstart (M2)

These endpoints and tools are primarily for development, QA, and preflop advisor research. They are not required for the core game loop.

Equity helper: POST /api/equity

Simple HU hands:
curl -sS -X POST http://127.0.0.1:8000/api/equity \
  -H "Content-Type: application/json" \
  -d '{
    "players":[
      {"hand":["Ah","Ad"]},
      {"hand":["Kh","Qh"]}
    ],
    "board":["As","Kd","2c"],
    "dead":[],
    "iters":20000,
    "exact":false
  }'

Ranges (requires a ranges-capable backend such as pbots):
curl -sS -X POST http://127.0.0.1:8000/api/equity \
  -H "Content-Type: application/json" \
  -d '{
    "players":[
      {"range":"JJ+"},
      {"range":"random"}
    ],
    "iters":50000,
    "exact":false
  }'

Developer entrypoints for equity:

• HTTP: POST /api/equity
• CLI: python -m backend.scripts.equity_cli
• Make target: make equity (wrapper over the CLI)
• Benchmark: python -m backend.scripts.benchmark_equity or make bench-equity

See EQUITY.md and API-CONTRACT.md for full contract and backend selection details.

Preflop advisor: GET /api/coach/preflop

With COACH_ENABLED=true and PREFLOP_CHART_PATHS pointing at at least one HU chart:
curl -sS "http://127.0.0.1:8000/api/coach/preflop?hand_id=H1&idx=0"

On success, the response includes:
{
  "source": "chart|equity|rule",
  "bucket": "fold|call|2.2x|2.5x|3.0x|jam",
  "rationale": "chart:... or equity rule explanation",
  "strategy_bar": {
    "fold": 0.15,
    "call": 0.55,
    "2.5x": 0.30
  }
}

Developer entrypoints for preflop:

• HTTP: GET /api/coach/preflop
• Charts: files under devdata/charts/ for HU examples
• Config: COACH_ENABLED, PREFLOP_CHART_PATHS, PREFLOP_EQ_DEFEND_THRESH, PREFLOP_FALLBACK_REQUIRED

Snapshots:

• When LOG_EQUITY_SNAPSHOT=true and you pass hand_id / idx to /api/equity, the response is stored and later appears as equity_snapshot in JSON exports.
• When LOG_PREFLOP_ADVICE=true, /api/coach/preflop responses are stored as preflop_advice entries in JSON exports.
• CSV export schemas remain unchanged; snapshots are JSON-only.

See PREFLOP-ADVISOR.md, EQUITY.md, API-CONTRACT.md and CONFIGURATION.md for deeper details.

Buckets & Sizing

• Labels like 2.2x, 2.5xR are sizing classes, not always a literal multiplier × big blind.
• When to_call = 0 (including SB HU open): ["2.2x","2.5x","3.0x","jam"]
• When facing a bet/raise: ["2.5xR","3.0xR","jam"]
• Minimum raise total: current_price + max(bb, last_raise_size) → sub-min raises return 400 with a descriptive error.
• It’s fine to submit any total; engine snaps to nearest legal bucket and reports last_action.snapped.

See docs/BET-TREES.md and docs/API-CONTRACT.md.

Deterministic Docs Examples & CI “Drift”

The docs examples in docs/examples/* are generated by:
python docs/scripts/capture_examples.py

This script:

• Resets the docs SQLite DB so session_id starts at 1
• Normalizes line endings to LF
• Strips volatile fields (created_at, time_ms, rng_seed, meta)
• Plays a deterministic first human action (check/call)

CI runs a “Docs Examples Drift” job to ensure committed examples match a fresh run. If the job fails, regenerate locally with the script and commit the updated files.

Development

Quality gates:
# Ruff + Black + Mypy + Pytest
ruff check .
black .
mypy backend
pytest -q

Frontend checks:
cd frontend
npm run lint
npm run typecheck

Equity / coach-related dev helpers:
# Quick equity checks
make equity HANDS='AhAd,KhQh' BOARD='AsKd2c' EXACT=0

# Tiny benchmark (also used in pbots-enabled CI job)
make bench-equity OUT=bench_equity.csv POLICIES=auto,pbots

# Coach smoke test (when enabled)
curl -sS "http://127.0.0.1:8000/api/coach/preflop?hand_id=H1&idx=0"

Common troubleshooting:

• Port conflicts: change --port for uvicorn or PORT for Next.js
• CORS: ensure NEXT_PUBLIC_API_BASE points to your backend host:port
• SQLite locks: stop other processes or change LOG_DB_PATH
• Equity backend mismatch: check EQUITY_BACKEND_POLICY and logs; if ranges are requested without a ranges-capable backend, expect a 400
• Coach disabled or misconfigured: check COACH_ENABLED and PREFLOP_CHART_PATHS values

Project Layout
.
├── backend/                     # FastAPI application & adapters
│   └── scripts/                 # CLI helpers (equity_cli, autoplay, benchmark_equity, etc.)
├── frontend/                    # Next.js app (Tailwind)
├── docs/                        # API, schema, bet trees, equity, preflop, configuration, debugging, QA
│   ├── examples/                # Canonical example payloads (generated)
│   └── scripts/capture_examples.py
├── .github/workflows/           # CI (lint, tests, packaging, docs drift, pbots matrix)
├── .data/                       # Local SQLite (ignored by Git)
├── Makefile                     # make api / make web / make equity / make bench-equity / etc.
└── README.md
Key docs:

• API-CONTRACT.md – endpoints, errors, gating, pre-bot snapshots, equity and coach contracts
• STATE-SCHEMA.md – full state, allowed, last_action
• BET-TREES.md – sizing classes, min-raise, snapping
• EQUITY.md – equity backends, configuration, API/CLI/benchmark usage
• PREFLOP-ADVISOR.md – chart format, metadata, fallback rules, limitations
• CONFIGURATION.md – env vars and recommended dev setup
• debugging.md – SSE, invariants, exports
• QA-CHECKLIST.md – what CI and reviewers verify (including M2 checks)
• BOT-POLICY.md – policy input/outputs and profiles

Roadmap

• M0: playable engine + UI, clean API, docs, CI ✅
• M1: expanded policies, UX iteration, export/reporting polish
• M2: equity backends + preflop advisor (charts + rules), logging/export snapshots, pbots CI matrix (current milestone)

(See TASKS-M0.md, TASKS-M1.md and the M2 task planning docs under docs/ if present.)

Contributing

• Use feature branches and focused PRs (one task per PR)
• Ensure CI is green, including Docs Examples Drift
• Follow QA-CHECKLIST.md before requesting review

License

See LICENSING-NOTES.md for third-party licenses and usage notes.