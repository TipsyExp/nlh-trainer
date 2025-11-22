# Runbook

This runbook shows how to run and interact with the trainer backend. It reflects
the latest equity stack (OMPEval → Eval7 → PokerKit), total-amount bet semantics,
unified coaching via `/api/coach/advice`, and snapshot logging for equity and
advice.

---

## 1) Start the backend

Install backend deps (plus optional deps if you want Eval7 / extra backends),
then launch via `uvicorn`.

```bash
# From repo root
python -m pip install -r backend/requirements.txt

# Optional (Eval7, helpers, etc.; OMPEval is a native build — see docs/BUILD-OMPEVAL.md)
python -m pip install -r backend/requirements-optional.txt

# Run the API (hot reload for dev)
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
Configure behaviour via environment variables (recommended in a .env). See
docs/CONFIGURATION.md.
________________________________________
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
The response includes session_id — pass it to subsequent hand/action calls.
________________________________________
3) Start a hand
curl -X POST http://127.0.0.1:8000/api/hand/start \
  -H "Content-Type: application/json" \
  -d '{"session_id": "YOUR_SESSION_ID", "seat": 0}'
If bots are enabled (bot_mode != "none"), the engine auto-plays until the first
human decision. The response includes the full state and the current actor.
________________________________________
4) Post an action (total-amount semantics)
When betting or raising, you specify the total stack commitment target. The
engine snaps it to the nearest legal bucket if needed.
curl -X POST http://127.0.0.1:8000/api/hand/action \
  -H "Content-Type: application/json" \
  -d '{"session_id":"YOUR_SESSION_ID","seat":0,"action":"bet","amount":320}'
The response includes:
•	a pre-bot state snapshot, and
•	bots_applied: the auto-played responses (if any).
Tips:
•	If you send an off-tree total, the engine snaps to a legal bucket and sets
snapped=true in state.last_action.
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
•	SSE stream: GET /api/debug/engine/events
•	Bundle: GET /api/debug/engine/bundle (zip of recent events and state)
Include X-Request-ID in API calls to correlate client requests with engine
transitions.
________________________________________
7) Equity & coaching
7.1 Equity service
Computes exact or Monte Carlo (MC) equities for hands and, where supported,
ranges/multiway. The same service is used by:
•	POST /api/equity
•	Preflop equity fallback
•	Postflop coach (HU + multiway)
Backends:
•	Primary: OMPEval (native, fast, 2–6 players, ranges + exact/MC, multithreaded)
•	Fallback: Eval7 (pip, ranges; slower)
•	Last resort: PokerKit (pure Python; hands-focused)
Backends are auto-selected via EQUITY_BACKEND_POLICY=auto
(ompeval → eval7 → pokerkit). See EQUITY.md for details.
Example call:
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
•	"ok": true
•	backend is one of "ompeval", "eval7", "pokerkit"
•	"mode": "hands", "n_players": 2
•	sum(players[*].equity) ≈ 1.0
Exact vs MC
•	Repeat with "exact": true (omit iters). Expect exact=true, iters=null.
•	MC runs vary unless you set an equity seed (see EQUITY_ITERS / backend docs).
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
•	Expect "mode": "ranges".
•	If your environment lacks a ranges-capable backend, the endpoint returns 400
with a clear message.
CLI helper & benchmark
# Quick CLI
python -m backend.scripts.equity_cli --hand AsKd --hand QcJh --iters 20000

# or via Makefile
make equity HANDS='AsKd,QcJh' ITERS=20000

# Tiny benchmark matrix (CSV)
python -m backend.scripts.benchmark_equity --out bench_equity.csv
# or
make bench-equity OUT=bench_equity.csv
# Quick CLI
python -m backend.scripts.equity_cli --hand AsKd --hand QcJh --iters 20000

# or via Makefile
make equity HANDS='AsKd,QcJh' ITERS=20000

# Tiny benchmark matrix (CSV)
python -m backend.scripts.benchmark_equity --out bench_equity.csv
# or
make bench-equity OUT=bench_equity.csv
COACH_ENABLED=true
PREFLOP_CHART_PATHS=devdata/charts/hu_example.json
PREFLOP_EQ_DEFEND_THRESH=0.48
PREFLOP_FALLBACK_REQUIRED=false

# Optional: postflop coach (HU)
POSTFLOP_COACH_ENABLED=true
POSTFLOP_COACH_ITERS=20000
POSTFLOP_COACH_PROFILE=TAG
# POSTFLOP_COACH_MULTIWAY_ENABLED=true  # once you trust multiway
Restart the backend.
7.2.2 Query advice for a decision
Use a real hand_id and idx from your session (e.g. from /api/export/hand):
curl http://127.0.0.1:8000/api/coach/advice?hand_id=H1&idx=0
Example preflop response (truncated):
{
  "version": 1,
  "status": "ok",
  "meta": {
    "street": "preflop",
    "n_players": 2,
    "hero_seat": 0,
    "source": "chart"
  },
  "recommendation": {
    "bucket": "2.5x",
    "strategy_bar": [
      { "action": "2.5x", "weight": 1.0 }
    ]
  },
  "equity": null,
  "thresholds": {},
  "rationale": "Open 2.5x from BTN per HU_25bb_srp_vsb chart."
}
Example flop HU response (equity-based, truncated):
{
  "version": 1,
  "status": "ok",
  "meta": {
    "street": "flop",
    "n_players": 2,
    "hero_seat": 0,
    "source": "equity"
  },
  "recommendation": {
    "bucket": "call",
    "strategy_bar": [
      { "action": "fold", "weight": 0.0 },
      { "action": "call", "weight": 0.7 },
      { "action": "2.5xR", "weight": 0.3 }
    ]
  },
  "equity": {
    "backend": "ompeval",
    "mode": "hands",
    "hero": 0.61,
    "players": [
      { "seat": 0, "equity": 0.61 },
      { "seat": 1, "equity": 0.39 }
    ],
    "exact": false,
    "iters": 20000
  },
  "thresholds": {
    "pot_odds": 0.42,
    "spr": 3.1
  },
  "rationale": "Hero equity 61% vs TAG range; pot odds ~42% → call/raise mix."
}
Status meanings (high level):
•	status: "ok" – Advice is actionable (bucket + strategy bar present).
•	status: "disabled" – Coaching globally off (COACH_ENABLED=false).
•	status: "unsupported" – Node not supported yet (e.g. multiway with coach disabled, exotic states).
•	status: "timeout" – Reserved for strict time-budget cases; coach should return a non-blocking result.
•	status: "not_found" – Decision context could not be resolved (hand_id / idx mismatch).
•	status: "error" – Internal error; check logs.
7.2.3 Legacy preflop endpoint (for debugging)
GET /api/coach/preflop still exists and returns the older preflop-only payload:
curl http://127.0.0.1:8000/api/coach/preflop?hand_id=H1&idx=0
This is primarily for tooling / regression tests. New UI and exports should
prefer /api/coach/advice and the unified AdviceV1 payload.
________________________________________
8) Snapshot logging & exports
You can log equity and coach advice snapshots and surface them in JSON
exports.
8.1 Enable logging
In .env:
LOG_EQUITY_SNAPSHOT=true
LOG_PREFLOP_ADVICE=true       # legacy preflop-only advice snapshots
LOG_COACH_ADVICE=true         # unified all-streets advice snapshots (AdviceV1)
LOG_EQUITY_SNAPSHOT_REDACT=true  # recommended for shared/prod
Restart the backend.
8.2 Generate snapshots
Play a hand via /api/hand/start + /api/hand/action, then call equity/coach
with hand_id and idx:
Equity snapshot:
curl -X POST "http://127.0.0.1:8000/api/equity?hand_id=H1&idx=0" \
  -H "Content-Type: application/json" \
  -d '{
    "players":[{"hand":["As","Kd"]},{"hand":["Qc","Jh"]}],
    "board":[],
    "dead":[],
    "iters":20000
  }'

Advice snapshot (unified):
curl http://127.0.0.1:8000/api/coach/advice?hand_id=H1&idx=0
(Optional) legacy preflop snapshot for comparison:
curl http://127.0.0.1:8000/api/coach/preflop?hand_id=H1&idx=0

8.3 Inspect exports
# Hand
curl "http://127.0.0.1:8000/api/export/hand/H1.json" | jq .

# Session
curl "http://127.0.0.1:8000/api/export/session/1.json" | jq .

Exported actions[*] may include:
{
  "idx": 0,
  "street": "pre",
  "actor_seat": 0,
  "action": "bet",
  "amount": 320,
  "...": "...",
  "equity_snapshot": {
    "backend": "ompeval",
    "mode": "hands",
    "board": [],
    "dead": [],
    "players": [
      { "equity": 0.62 },
      { "equity": 0.38 }
    ],
    "raw": { "...": "..." }
  },
  "preflop_advice": {
    "source": "chart",
    "bucket": "2.5x",
    "rationale": "chart:HU_25bb_srp_vsb; node=sb_open; hand=AJo",
    "strategy_bar": {
      "fold": 0.15,
      "call": 0.55,
      "2.5x": 0.30
    }
  },
  "coach_advice": {
    "version": 1,
    "status": "ok",
    "meta": {
      "street": "preflop",
      "n_players": 2,
      "hero_seat": 0,
      "source": "chart"
    },
    "recommendation": {
      "bucket": "2.5x",
      "strategy_bar": [
        { "action": "2.5x", "weight": 1.0 }
      ]
    },
    "equity": null,
    "thresholds": {},
    "rationale": "Open 2.5x from BTN per HU_25bb_srp_vsb chart."
  }
}
Notes:
•	All snapshot fields are optional:
o	If logging is disabled, equity_snapshot, preflop_advice, and
coach_advice are simply omitted.
•	CSV exports do not include snapshot columns; JSON is the source of truth.
9) Troubleshooting
9.1 Equity
Symptom: backend: "pokerkit" even though you expect OMPEval/Eval7
•	Check EQUITY_BACKEND_POLICY:
o	auto tries ompeval → eval7 → pokerkit.
o	If explicitly pokerkit, that’s what you’ll get.
•	Ensure optional deps are present:
o	Build OMPEval (see docs/BUILD-OMPEVAL.md).
o	Install Eval7 (via backend/requirements-optional.txt).
•	Inspect "raw" in the equity response; look for hints (threads, samples, stderr).
Symptom: /api/equity returns 400 about unsupported mode
•	You likely requested range equities but no ranges-capable backend is available
under the current policy.
•	Either:
o	Switch to fixed hand inputs, or
o	Build/enable OMPEval or install Eval7 and set
EQUITY_BACKEND_POLICY=auto|ompeval|eval7.
Symptom: Results are noisy / run-to-run different
•	MC sampling is in use (exact=false).
•	Options:
o	Increase EQUITY_ITERS or request-level iters.
o	Use backend-specific seeding if available.
o	Use exact=true where supported (small trees).
9.2 Coach / advice
Symptom: GET /api/coach/advice returns HTTP 501 or status: "disabled"
•	Check COACH_ENABLED (must be true for any advice).
•	Confirm that:
o	Charts exist (PREFLOP_CHART_PATHS) for chart-based preflop, and/or
o	Postflop coach is allowed to run.
Symptom: status: "unsupported" for certain nodes
Common causes:
•	Postflop coach disabled (POSTFLOP_COACH_ENABLED=false) → only preflop
supported.
•	Multiway coach disabled (POSTFLOP_COACH_MULTIWAY_ENABLED=false) but
n_players > 2.
•	No multiway-capable equity backend (e.g. OMPEval not built) under current
EQUITY_BACKEND_POLICY.
Check:
•	POSTFLOP_COACH_ENABLED
•	POSTFLOP_COACH_MULTIWAY_ENABLED
•	Backends / configuration in EQUITY_BACKEND_POLICY.
Symptom: Preflop advice differs between /api/coach/preflop and /api/coach/advice
•	/api/coach/advice is the primary route and returns the unified AdviceV1
payload.
•	/api/coach/preflop is a legacy helper that should mirror the same logic,
but small drift may appear if one of them is updated in isolation.
•	Prefer /api/coach/advice for QA and overlay; treat /coach/preflop as a
compatibility shim.
9.3 Snapshots / exports
Symptom: equity_snapshot / preflop_advice / coach_advice missing in JSON exports
•	Verify flags:
o	LOG_EQUITY_SNAPSHOT
o	LOG_PREFLOP_ADVICE
o	LOG_COACH_ADVICE
o	LOG_EQUITY_SNAPSHOT_REDACT (redacts content, doesn’t disable logging)
•	Ensure you included hand_id and idx in the /api/equity and
/api/coach/advice calls.
•	Confirm those API calls succeeded (ok: true / HTTP 200).
•	Remember:
o	CSV exports do not include snapshots (JSON only).
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

