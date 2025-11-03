# Runbook

This runbook provides a concise guide for setting up and operating the NLH Trainer backend as of milestone **M1**. It covers local installation, running the server, exporting hands, and replaying exported data to verify determinism.

---

## Local Setup

1. **Clone the repository** and navigate to its root.

2. **(Optional) Create a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows PowerShell: .\.venv\Scripts\Activate.ps1

Install dependencies using Python 3.12+:
python -m pip install -r requirements.txt
The root requirements.txt pulls in backend dependencies (FastAPI, Uvicorn, etc.). Keep rlcard installed; it’s used by the default engine.

Run the backend (FastAPI via Uvicorn):
uvicorn backend.main:app --reload

The API will be available at http://localhost:8000/api
Makefile shortcuts (optional):

make api – runs the API locally

make test – backend tests

make autoplay – quick autoplay smoke

make dist – builds the slim distribution zip

Export & Replay Workflow (Determinism)

One of the M1 acceptance checks verifies that exporting a hand and replaying it with the same seed yields an identical outcome. Below is a manual version of that workflow.

1) Start a Session

POST /api/session with a fixed base_seed so results are reproducible:
curl -X POST "http://localhost:8000/api/session?base_seed=DOCS-EXAMPLES"

Response includes a numeric session_id (e.g. 1).

2) Start a Hand

POST /api/hand/start with that session_id:
curl -X POST "http://localhost:8000/api/hand/start?session_id=1"

Response includes a string hand_id (e.g. "H1").

3) Act Deterministically

Fetch state to see the acting seat and allowed buckets:
curl "http://localhost:8000/api/hand/state?hand_id=H1"

Use a fixed rule for the first decision to keep runs comparable (e.g., check if you can, otherwise call). Submit actions with:

curl -X POST "http://localhost:8000/api/hand/action?hand_id=H1" \
  -H "Content-Type: application/json" \
  -d '{"action":"check"}'

Bots will auto-respond. Repeat until the hand naturally ends.

4) Export the Hand

Export as JSON and CSV:
curl "http://localhost:8000/api/export/hand/H1.json" -o hand.json
curl "http://localhost:8000/api/export/hand/H1.csv"  -o hand.csv

JSON contains actions plus a final state snapshot.

CSV has one row per action. The current header is:
hand_id,idx,street,actor_seat,action,amount,bucket,to_call_after,pot_after,snapped,engine,evaluator

Notes:

snapped is present; it may be empty when not applicable.

Engine/evaluator fields reflect the engine used (e.g., PokerKit).

5) Replay & Verify

To validate determinism:

Create a new session with the same base_seed (DOCS-EXAMPLES).

Start a new hand and follow the same first-decision policy you used before (e.g., check-or-call rule).

Let the hand complete and export again.

Compare canonical aspects between the two exports:

actions[*].type/action, amount, bucket, to_call_after, pot_after

seating/position info in state (e.g., dealer_seat, sb_seat, bb_seat, street)

table config (sb, bb, ante, seat_count)

The automated test backend/tests/test_export_roundtrip.py performs this comparison programmatically.

CSV Usage

Exported CSVs are convenient for analysis. Each row corresponds to one decision (human or bot). Buckets reflect discretized sizes (see docs/BET-TREES.md). The snapped column indicates when an off-tree size was adjusted to the nearest allowed bucket.

Troubleshooting

Coach disabled / 501 responses: If you hit a coach/solver endpoint while coaching is disabled (no solver wired, or COACH_ENABLED=false), you should see 501 Not Implemented. Normal play and export endpoints do not require the coach.

Determinism drift: Ensure you’re using the same base_seed and making the same initial decision policy; otherwise, action sequences can diverge.

Ports in use: If :8000 is busy, either stop the other service or run Uvicorn on a different port with --port 8001.