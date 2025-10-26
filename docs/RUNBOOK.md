# Runbook

This runbook provides a concise guide for setting up and operating the NLH Trainer backend as of milestone M1.  It covers local installation, starting the server, exporting hands, and replaying exported data to verify determinism.

## Local Setup

1. **Clone the repository** and navigate to its root.
2. **Install dependencies** using Python 3.12 or newer:

   ```bash
   python -m pip install -r requirements.txt
   ```

   The `requirements.txt` in the project root includes both backend and frontend dependencies.  Do not remove `rlcard`; it is required for the default engine.

3. **Run the backend**.  The application uses FastAPI and can be served with Uvicorn:

   ```bash
   uvicorn backend.main:app --reload
   ```

   The API will be available at `http://localhost:8000/api` by default.

## Export & Replay Workflow

One of the acceptance tests for M1 verifies that exporting a hand and replaying it with the same seed produces an identical canonical state.  The steps below describe how to perform this process manually.

### 1. Start a Session

POST to `/api/session` with a fixed `base_seed` to ensure determinism:

```bash
curl -X POST "http://localhost:8000/api/session?base_seed=DOCS-EXAMPLES"
```

The response will contain a `session_id` (e.g. `10`).

### 2. Start a Hand

POST to `/api/hand/start` with the session ID:

```bash
curl -X POST "http://localhost:8000/api/hand/start?session_id=10"
```

This returns a `hand_id` (e.g. `H1`).

### 3. Take a Deterministic Action

Query the current state via `GET /api/hand/state?hand_id=H1` to see allowed buckets.  For the first action, choose a fixed rule (e.g. **always call** if there is an amount to call, otherwise **check**).  Submit the action:

```bash
curl -X POST "http://localhost:8000/api/hand/action?hand_id=H1" \
  -H "Content-Type: application/json" \
  -d '{"action": "check"}'
```

Bots will respond automatically.  Repeat calling and checking until the hand completes.

### 4. Export the Hand

After the hand concludes (street transitions to `showdown`), export it:

```bash
curl "http://localhost:8000/api/export/hand/H1.json" -o hand.json
curl "http://localhost:8000/api/export/hand/H1.csv" -o hand.csv
```

The JSON file contains the `actions` array and final `state`; the CSV contains one row per action.  The CSV header order is stable: `hand_id,idx,street,actor_seat,action,amount,bucket,to_call_after,pot_after,time_ms,rng_seed,snapped,meta,engine,evaluator,created_at`.

### 5. Replay and Verify

To verify determinism:

1. Start a **new session** with the **same `base_seed`** (`DOCS-EXAMPLES`).  Start a new hand and apply the **same first action rule** (e.g. always check pre‑flop).
2. Let the hand run to completion.  Export this second hand.
3. Compare canonical subsets of the two states (e.g. deck order, final chip stacks, action history types and sizes).  They should match exactly.  The test `backend/tests/test_export_roundtrip.py` automates this comparison.

## CSV Usage

Exported CSV files are convenient for statistical analysis and machine learning pipelines.  Each row represents one decision in the hand or session.  The `snapped` column is `0` for unsnapped actions and `1` when a player’s requested amount was adjusted to the nearest bucket.  Timestamps can be parsed as UTC ISO‑8601 strings.

## Troubleshooting

* If you encounter a `501` response, ensure that `COACH_ENABLED` is not set to `true` without a solver binary present.  The export endpoints function regardless of coach configuration.
* The seed must remain the same across exports to guarantee deterministic replay.  Changing the seed will alter card order and bot decisions.
