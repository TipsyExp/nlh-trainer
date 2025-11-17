# Runbook

This runbook shows how to run and interact with the trainer backend. It reflects the latest equity stack (OMPEval → Eval7 → PokerKit), total-amount bet semantics, unified gating, and snapshot logging.

---

## 1) Start the backend

Install backend deps (plus optional deps if you want Eval7), then launch via `uvicorn`.

```bash
# From repo root
python -m pip install -r backend/requirements.txt
# Optional (Eval7 fallback and build helpers; OMPEval is a native build — see docs/BUILD-OMPEVAL.md)
python -m pip install -r backend/requirements-optional.txt

# Run the API (hot reload for dev)
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
Configure behavior via environment variables (recommended in a .env). See docs/CONFIGURATION.md
2) Create a session
Use /api/session to define table params (seats, blinds, stacks, bot mode/profile, etc.).
curl -X POST http://127.0.0.1:8000/api/session \
  -H "Content-Type: application/json" \
  -d '{
    "seats": 2,
    "sb": 50,
    "bb": 100,
    "stacks": [10000, 10000],
    "bot_mode": "heuristic",
    "bot_profile": "TAG"
  }'
The response includes session_id—pass it to subsequent hand/action calls.
________________________________________
3) Start a hand
curl -X POST http://127.0.0.1:8000/api/hand/start \
  -H "Content-Type: application/json" \
  -d '{"session_id": "YOUR_SESSION_ID", "seat": 0}'

If bots are enabled (bot_mode != "none"), the engine auto-plays until the first human decision. The response includes the full state and the current actor.
________________________________________
4) Post an action (total-amount semantics)
When betting or raising, you specify the total stack commitment target (the engine snaps it to the nearest legal bucket if needed).
curl -X POST http://127.0.0.1:8000/api/hand/action \
  -H "Content-Type: application/json" \
  -d '{"session_id":"YOUR_SESSION_ID","seat":0,"action":"bet","amount":320}'
The response includes:
•	a pre-bot state snapshot, and
•	bots_applied: the auto-played responses (if any).
Tips
•	If you send an off-tree total, the engine snaps to a legal bucket and sets snapped=true in state.last_action.
•	You can pass a unique X-Request-ID header to correlate with debug streams.
________________________________________
5) Auto-step bots (dev convenience)
Enable via HAND_AUTO_ENABLED=true then:
curl -X POST http://127.0.0.1:8000/api/hand/auto \
  -H "Content-Type: application/json" \
  -d '{"session_id": "YOUR_SESSION_ID"}'

If disabled, you get HTTP 501.
________________________________________
6) Debugging
Set ENGINE_DEBUG_HTTP=true to expose structured events.
•	SSE stream: /api/debug/engine/events
•	Bundle: /api/debug/engine/bundle (zip of recent events and state)
Include X-Request-ID in API calls to correlate client requests with engine transitions.
________________________________________
7) Equity & preflop advisor
Equity service
Computes exact or Monte Carlo (MC) equities for hands and, where supported, ranges/multiway.
•	Primary backend: OMPEval (native, fast, 2–6 players, ranges + exact/MC, multithreaded)
•	Fallback: Eval7 (pip, ranges; slower)
•	Last resort: PokerKit (pure Python; hands-focused)
Backends are auto-selected via EQUITY_BACKEND_POLICY=auto (ompeval → eval7 → pokerkit). See EQUITY.md for details.
HU sanity check (hands)
curl -X POST http://127.0.0.1:8000/api/equity \
  -H "Content-Type: application/json" \
  -d '{
    "players":[
      {"hand":["As","Kd"]},
      {"hand":["Qc","Jh"]}
    ],
    "board":[],
    "dead":[],
    "iters":20000,
    "exact":false
  }'

Verify:
•	ok: true
•	backend is one of "ompeval", "eval7", "pokerkit"
•	mode: "hands", n_players: 2
•	sum(players[*].equity) ≈ 1.0
Exact vs MC
•	Repeat with "exact": true (omit iters). Expect exact=true, iters=null.
•	MC runs vary unless you set EQUITY_SEED.
Ranges & multiway (requires ranges-capable backend)
With OMPEval built or Eval7 installed:
curl -X POST http://127.0.0.1:8000/api/equity \
  -H "Content-Type: application/json" \
  -d '{
    "players":[
      {"range":"JJ+"},
      {"range":"random"}
    ],
    "board":[],
    "dead":[],
    "iters":50000,
    "exact":false
  }'
•	Expect mode: "ranges".
•	If your environment lacks a ranges-capable backend, the endpoint returns 400 with a clear message.
CLI helper & benchmark
# Quick CLI
python -m backend.scripts.equity_cli --hand AsKd --hand QcJh --iters 20000
# or via Makefile
make equity HANDS='AsKd,QcJh' ITERS=20000

# Tiny benchmark matrix (CSV)
python -m backend.scripts.benchmark_equity --out bench_equity.csv
# or
make bench-equity OUT=bench_equity.csv
Open the CSV and inspect columns like backend, policy, board_len, iters, elapsed_ms, evals_per_sec.
Preflop advisor
Chart-first with optional equity fallback. Gated by COACH_ENABLED.
1.	Enable and load a chart (e.g. HU dev chart):
# .env or environment
COACH_ENABLED=true
PREFLOP_CHART_PATHS=devdata/charts/hu_example.json
Restart the backend.
2.	Query:
# Use a real hand_id/idx from your session
curl "http://127.0.0.1:8000/api/coach/preflop?hand_id=H1&idx=0"
Response contains:
•	source: "chart", "equity", or "rule"
•	bucket: recommended primary bucket (e.g., "fold", "call", "2.5x")
•	rationale: brief explanation
•	strategy_bar: bucket → weight (≈ sum to 1)
Behavior:
•	Chart hit → source="chart"
•	Chart miss + ranges-capable equity → source="equity" with threshold in rationale
•	Otherwise → conservative default ("rule") or 501 depending on PREFLOP_FALLBACK_REQUIRED
If COACH_ENABLED=false, the endpoint returns 501.
________________________________________
8) Snapshot logging & exports
You can log equity and preflop advice snapshots and surface them in JSON exports.
1.	Enable:
LOG_EQUITY_SNAPSHOT=true
LOG_PREFLOP_ADVICE=true
LOG_EQUITY_SNAPSHOT_REDACT=true  # recommended for shared/prod
Restart the backend.
2.	Generate snapshots:
•	Play a hand normally via /api/hand/start + /api/hand/action.
•	Call equity with hand_id and idx:
curl -X POST "http://127.0.0.1:8000/api/equity?hand_id=H1&idx=0" \
  -H "Content-Type: application/json" \
  -d '{ "players":[{"hand":["As","Kd"]},{"hand":["Qc","Jh"]}], "board":[], "dead":[], "iters":20000 }'
Call preflop coach during that same decision:
curl http://127.0.0.1:8000/api/coach/preflop?hand_id=H1&idx=0
Inspect exports:
# Hand
curl "http://127.0.0.1:8000/api/export/hand/H1.json" | jq .

# Session
curl "http://127.0.0.1:8000/api/export/session/1.json" | jq .
Exported actions[*] may include:
{
  "action": "bet",
  "amount": 320,
  "...": "...",
  "equity_snapshot": { /* decoded snapshot from /api/equity (if logged) */ },
  "preflop_advice": { /* decoded advice from /api/coach/preflop (if logged) */ }
}
Notes
•	These fields are optional; if logging is disabled they are omitted.
•	CSV exports do not include snapshot columns; JSON is the source of truth.
________________________________________
9) Troubleshooting
Equity
Symptom: backend: "pokerkit" even though you expect OMPEval/Eval7
•	Check EQUITY_BACKEND_POLICY:
o	auto tries ompeval → eval7 → pokerkit.
o	If explicitly pokerkit, that’s what you’ll get.
•	Ensure optional deps are present:
o	Build OMPEval (see docs/BUILD-OMPEVAL.md).
o	Install eval7 (via backend/requirements-optional.txt).
•	Inspect raw in the equity response; look for hints like threads, samples, stderr.
Symptom: /api/equity returns 400 about unsupported mode
•	You likely requested range equities but no ranges-capable backend is available under the current policy.
•	Either:
o	Switch to fixed hand inputs, or
o	Build/enable OMPEval or install Eval7 and set EQUITY_BACKEND_POLICY=auto|ompeval|eval7.
Symptom: Results are noisy/run-to-run different
•	MC sampling is in use (exact=false).
•	Options:
o	Increase EQUITY_ITERS or request-level iters.
o	Set EQUITY_SEED for deterministic MC.
o	Use exact=true where supported (small trees).
Preflop advisor
Symptom: GET /api/coach/preflop returns 501
•	Check COACH_ENABLED.
•	Verify PREFLOP_CHART_PATHS points to at least one valid chart file.
Symptom: GET /api/coach/preflop returns 404 / no advice
•	Node/hand may be missing from charts and equity fallback is unavailable or disabled.
•	Check:
o	Chart metadata (positions, stack depth, format version).
o	PREFLOP_EQ_DEFEND_THRESH and PREFLOP_FALLBACK_REQUIRED.
o	Equity backend availability (ranges-capable for fallback).
Snapshots / Exports
Symptom: equity_snapshot / preflop_advice missing in JSON exports
•	Verify flags:
o	LOG_EQUITY_SNAPSHOT
o	LOG_PREFLOP_ADVICE
o	LOG_EQUITY_SNAPSHOT_REDACT (redacts content, doesn’t disable)
•	Ensure you included hand_id and idx in the equity/coach calls.
•	Confirm those API calls succeeded (ok: true / HTTP 200).
•	Remember: CSV exports do not include snapshots (JSON only).
________________________________________
10) Helpful Make targets
# Start backend (dev)
make api

# Install deps
make install-backend
make install-optional   # installs backend/requirements-optional.txt if present

# Tests & quality
make test-backend
make test-frontend
make test
make lint
make fmt

# Equity helpers
make equity HANDS='AhAd,KhQh' BOARD='AsKd2c' EXACT=1
make equity RANGES='JJ+,random' ITERS=50000
make bench-equity OUT=bench_equity.csv POLICIES='auto,ompeval,eval7'

# Frontend (if present)
make web

If problems persist:
1.	Enable ENGINE_DEBUG_HTTP=true.
2.	Reproduce with a unique X-Request-ID.
3.	Download /api/debug/engine/bundle and relevant /api/export/*.json.
4.	Attach these artifacts when reporting issues.
