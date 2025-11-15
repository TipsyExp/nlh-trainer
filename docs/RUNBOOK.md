
# Runbook

This runbook provides a high-level overview of how to run and interact with
the trainer backend. It reflects the latest API semantics.

---

## Starting the backend

Install dependencies and launch the server with [`uvicorn`](https://www.uvicorn.org/):

```bash
python -m pip install -r requirements.txt
uvicorn backend.main:app
Configure behaviour via environment variables. See
Configuration for details.

Creating a session
Use the /api/session endpoint to create a new session. Include table params
to match your environment. For example:
curl -X POST http://localhost:8000/api/session \
  -H "Content-Type: application/json" \
  -d '{
    "seats": 2,
    "sb": 50,
    "bb": 100,
    "stacks": [10000, 10000],
    "bot_mode": "heuristic",
    "bot_profile": "TAG"
  }'

The response contains a session_id which must be supplied to subsequent hand
and action calls.
________________________________________
Starting a hand
curl -X POST http://localhost:8000/api/hand/start \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "seat": 0}'

If bots are enabled (BOT_MODE != "none"), the engine will automatically
apply all bot actions until it is the human's turn. The response contains the
full state and the actor information.
________________________________________
Posting an action
curl -X POST http://localhost:8000/api/hand/action \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "seat": 0, "action": "bet", "amount": 320}'

The amount is a total commitment target; the engine will snap off-tree
totals to the nearest bucket. The response includes a pre-bot snapshot of the
state and an array of bot actions applied in response (bots_applied).
Tip: include an X-Request-ID header (any unique string) on API calls. This
value is echoed in debug events and helps correlate requests with engine
transitions.
________________________________________
Auto-stepping bots
For development convenience, bots can be auto-advanced via /api/hand/auto.
Ensure HAND_AUTO_ENABLED=true and call:
curl -X POST http://localhost:8000/api/hand/auto \
  -H "Content-Type: application/json" \
  -d '{"session_id": "..."}'

When HAND_AUTO_ENABLED=false, this endpoint returns HTTP 501 Not Implemented.
________________________________________
Debugging
Set ENGINE_DEBUG_HTTP=true to enable structured debug events. Subscribe to
them via Server-Sent Events at /api/debug/engine/events. Use the
X-Request-ID header on API calls to correlate client requests with engine
transitions.
To capture a complete hand for analysis, call /api/debug/engine/bundle to
download a ZIP archive of events and state.
________________________________________
Equity & preflop advisor
This section covers how to verify the equity service and preflop advisor,
how to enable and inspect snapshots via exports, and how to debug common
issues.
See also:
•	EQUITY.md for backend details and capabilities.
•	PREFLOP-ADVISOR.md for backend details and capabilities.
•	API-CONTRACT.md for full endpoint schemas.
Verifying the equity service
The equity service computes exact or Monte Carlo (MC) equity for fixed hands
and, when supported, ranges.
1.	Basic HU sanity check
With the backend running, call:
curl -X POST http://localhost:8000/api/equity \
  -H "Content-Type: application/json" \
  -d '{
    "players": [
      { "hand": ["As", "Kd"] },
      { "hand": ["Qc", "Jh"] }
    ],
    "board": [],
    "dead": [],
    "iters": 20000,
    "exact": false
  }'
•  Verify in the response:
•	ok is true.
•	backend is one of pokerkit, henry, or pbots.
•	mode is "hands".
•	n_players is 2.
•	The sum of equity in players[*].equity is ≈ 1.0.
•  Exact vs MC
•	Repeat the same request with "exact": true and omit iters.
•	Expect exact=true and iters=null (or 0 depending on backend).
•	MC (exact=false) runs will vary slightly between calls unless
EQUITY_SEED is set.
•  Ranges (when supported)
If you have a ranges-capable backend (e.g. pbots) installed and
EQUITY_BACKEND_POLICY allows it:

curl -X POST http://localhost:8000/api/equity \
  -H "Content-Type: application/json" \
  -d '{
    "players": [
      { "range": "JJ+" },
      { "range": "random" }
    ],
    "board": [],
    "dead": [],
    "iters": 50000,
    "exact": false
  }'
•	•  
mode should be "ranges".
•	If no ranges-capable backend is available, expect a 400 with a clear
message about unsupported mode.
•  CLI helper & benchmark
For quick local experiments:
# CLI script (hands or ranges)
python -m backend.scripts.equity_cli --hand AsKd --hand QcJh --iters 20000

# or via Makefile:
make equity HANDS='AsKd,QcJh' ITERS=20000

# Tiny benchmark matrix (writes CSV)
python -m backend.scripts.benchmark_equity --out bench_equity.csv

# or:
make bench-equity OUT=bench_equity.csv

1.	Inspect bench_equity.csv for columns like backend, policy,
board_len, iters, elapsed_ms, evals_per_sec.
________________________________________
Verifying the preflop advisor
The preflop advisor is chart-first, with optional equity fallback. It can be
fully disabled via COACH_ENABLED=false.
1.	Enable coach and charts
Set (for example in .env):
COACH_ENABLED=true
PREFLOP_CHART_PATHS=devdata/charts/hu_example.json

•  Restart the backend so charts are loaded on startup.
•  Query the advisor
Make sure you have an active hand (via /api/hand/start), then:

curl http://localhost:8000/api/coach/preflop?hand_id=H1&idx=0

•  (Replace H1 with a real hand id from your session.)
On success (HTTP 200), the response should contain:
•	source: "chart", "equity", or "rule".
•	bucket: recommended action bucket (e.g. "fold", "call", "2.5x").
•	rationale: short string describing why this action was chosen.
•	strategy_bar: map from bucket label to weight (sums ≈ 1.0).
•  Behaviour by mode
•	If the hand/node appears in your chart:
o	source="chart" and bucket matches the chart row.
•	If the chart misses and equity fallback is available (ranges-capable
backend + preflop rules):
o	source="equity" and rationale mentions the threshold and villain
range assumption.
•	If neither chart nor equity can be used:
o	Either source="rule" (conservative default) or HTTP 501 depending
on PREFLOP_FALLBACK_REQUIRED. See PREFLOP-ADVISOR.md
1.	Coach disabled
If COACH_ENABLED=false, the same request should return 501 Not Implemented
with a descriptive message.
________________________________________
Snapshot logging & exports
Equity and preflop advice calls can be logged and surfaced in JSON exports
to aid debugging and analysis.
1.	Enable snapshot logging
Set some or all of:
LOG_EQUITY_SNAPSHOT=true
LOG_PREFLOP_ADVICE=true
LOG_EQUITY_SNAPSHOT_REDACT=true  # recommended in shared/prod envs

•  Restart the backend.
•  Generate snapshots
•	Play a hand normally via /api/hand/start and /api/hand/action.
•	Call POST /api/equity with hand_id and idx query parameters:
curl -X POST "http://localhost:8000/api/equity?hand_id=H1&idx=0" \
  -H "Content-Type: application/json" \
  -d '{ "players":[{"hand":["As","Kd"]},{"hand":["Qc","Jh"]}], "board":[], "dead":[], "iters":20000 }'

•	•  
Call GET /api/coach/preflop?hand_id=H1&idx=0 during that same hand.
These calls will be tied to the action at index idx for hand H1.
•  Inspect JSON exports
•	Export a specific hand:
curl "http://localhost:8000/api/export/hand/H1.json" | jq .

Export a session:
curl "http://localhost:8000/api/export/session/1.json" | jq .

In the resulting JSON:
•	Each hand contains an actions array.
•	Individual actions may include:
{
  "action": "bet",
  "amount": 320,
  "...": "...",
  "equity_snapshot": { /* decoded snapshot from /api/equity (if logged) */ },
  "preflop_advice": { /* decoded advice from /api/coach/preflop (if logged) */ }
}

1.	Notes:
o	These fields are optional. If logging is disabled, they are simply
omitted.
o	CSV exports (/api/export/hand/{id}.csv, /api/export/session/{id}.csv)
intentionally do not contain snapshot columns; JSON is the source
of truth for snapshots.
________________________________________
Troubleshooting
Common issues and how to diagnose them.
Equity service
Symptom: Equity always reports backend: "pokerkit" even though you
expect pbots/Henry.
•	Check EQUITY_BACKEND_POLICY:
o	auto is fine; the service will try pbots, then Henry, then PokerKit.
o	If it’s explicitly pokerkit, that’s what you’ll always get.
•	Confirm optional backends are installed in your environment (for pbots) or
that HREVAL_LIB_PATH points to a valid Henry library.
•	Look at the raw field in the /api/equity response or backend logs for
import/load errors.
Symptom: /api/equity returns 400 with an error about unsupported mode.
•	You likely requested ranges ("range": "...") but no ranges-capable
backend is available under the current EQUITY_BACKEND_POLICY.
•	Either:
o	Switch to fixed hands ("hand": ["Ah","Ad"] style), or
o	Install/enable a ranges-capable backend and set EQUITY_BACKEND_POLICY
to auto or the appropriate backend.
Symptom: Results are noisy or “change every time.”
•	MC sampling is in use (exact=false).
•	Options:
o	Increase EQUITY_ITERS or the iters field in the request.
o	Set EQUITY_SEED to a fixed integer for deterministic MC runs.
o	Use exact=true where the backend supports it (small HU trees).
________________________________________
Preflop advisor
Symptom: GET /api/coach/preflop returns 501.
•	Check COACH_ENABLED:
o	If false, this is expected.
•	Verify PREFLOP_CHART_PATHS is set correctly and points to at least one
valid chart file.
•	Ensure the advisor code is present and wired into the app (see
PREFLOP-ADVISOR.md
Symptom: GET /api/coach/preflop returns 404.
•	The request likely refers to a hand/node that isn’t covered by any loaded
chart and equity fallback is either disabled or unavailable.
•	Check:
o	Chart metadata (positions, stack depth, format version).
o	PREFLOP_EQ_DEFEND_THRESH and PREFLOP_FALLBACK_REQUIRED.
o	Equity backend: equity fallback needs ranges-capable support.
________________________________________
Snapshot logging & exports
Symptom: equity_snapshot / preflop_advice are missing in JSON exports.
•	Verify the flags:
LOG_EQUITY_SNAPSHOT
LOG_PREFLOP_ADVICE
LOG_EQUITY_SNAPSHOT_REDACT
•	Check that calls to /api/equity and /api/coach/preflop included
hand_id and idx (these are required to tie snapshots to actions).
•	Ensure the equity/advice calls succeeded with ok=true / HTTP 200.
•	Remember: CSV exports intentionally exclude snapshots; use JSON.
________________________________________
If a problem persists after these checks, capture a minimal reproduction:
1.	Enable ENGINE_DEBUG_HTTP=true.
2.	Reproduce the issue while sending a unique X-Request-ID.
3.	Download /api/debug/engine/bundle and the relevant /api/export/hand/*.json.
4.	Attach these artefacts when reporting the issue.

