# Runbook

This runbook provides operational guidance for running the NLH
Trainer backend, exporting hand histories and replaying them for
analysis.  It is intended for developers and QA engineers who need
to start the service, run automated matches and verify determinism.

## Starting the Service

The backend is a FastAPI application.  To run it locally:

```bash
# from the repository root
python -m uvicorn nlh-trainer.backend.main:app --reload
```

Alternatively, if you prefer to run the module directly:

```bash
python -m nlh-trainer.backend.main
```

The server listens on `localhost:8000` by default.  Use `GET /` or
`GET /health` to verify that it is up.

### Environment Variables

The following environment variables influence the backend:

| Variable                 | Description                                                                                     |
|--------------------------|-------------------------------------------------------------------------------------------------|
| `LOG_DB_PATH`           | Filesystem path to the SQLite database used for logging sessions, hands and actions.  Defaults to `nlh_trainer_logs.db` in the current working directory. |
| `ENGINE`                | Name of the engine module to use (currently only `pokerkit` is supported).                       |
| `EVALUATOR`             | Name of the hand evaluator to use (future use).                                                 |
| `COACH_ENABLED`         | If set to `true`, enables the solver coach API (will remain `false` until M1 steps are complete). |
| `COACH_CACHE_MAX_ROWS`  | Maximum number of entries in the solver cache (M1 Step 7).                                       |
| `COACH_CACHE_TTL_DAYS`  | Time‑to‑live for solver cache entries (M1 Step 7).                                               |
| `TEXASSOLVER_PATH`      | Absolute path to the TexasSolver binary (needed when `COACH_ENABLED=true`).                       |

Environment variables can be loaded from a `.env` file if
`python‑dotenv` is installed.  See `backend/main.py` for details.

## Creating Sessions and Playing Hands

Use the API endpoints described in [API‑CONTRACT.md](API-CONTRACT.md)
to create a training session, start hands, query state and submit
actions.  A typical workflow is:

1. `POST /api/session` – configure the table (seats, blinds, stacks,
   base_seed, human_seat).
2. `POST /api/hand/start` – begin a new hand; bots will act until it
   is your turn.
3. `GET /api/hand/state` – inspect the public snapshot and the actor
   information.
4. `POST /api/hand/action` – submit your decision (`check`, `call`,
   `bet`, `raise`, `fold`).
5. Repeat steps 3–4 until the hand concludes (no actor returned).
6. Export the hand if desired (see below).

## Exporting and Replaying Hands

Completed hands and sessions can be exported for analysis:

- `GET /api/export/hand/{hand_id}.json` – export a single hand as JSON.
- `GET /api/export/hand/{hand_id}.csv` – export a single hand as CSV.
- `GET /api/export/session/{session_id}.json` – export all completed
  hands in a session as JSON.
- `GET /api/export/session/{session_id}.csv` – export all completed
  hands in a session as CSV.

The JSON export includes a serialised `GameState` and an `actions`
array.  To replay a hand, you can deserialize the `state` using
`nlh_trainer.backend.models.state.import_json`:

```python
from nlh_trainer.backend.models.state import import_json
import json

with open("hand_H1.json") as f:
    data = json.load(f)
game_state = import_json(json.dumps(data["state"]))
# Now you can inspect game_state.players, game_state.action_history, etc.
```

To reproduce the hand in the engine, ensure you create a session
with the same base seed and apply each action in order via the API.
Logging the RNG seed for each action guarantees that the shuffled
deck and action sequence are deterministic.

## Automated Play

A convenience script will be provided in later milestones
(`backend/scripts/autoplay.py`) to simulate matches against the bots or
the coach.  For now you can drive the API from a test client (e.g.
Python `requests` or `httpx`) to automate gameplay and collect
training data.

## Troubleshooting

- If the server fails to start, ensure that the `nlh-trainer`
  directory is on your `PYTHONPATH` and that all dependencies from
  `requirements.txt` are installed in your virtual environment.
- When exporting hands, ensure that the hand has completed (the engine
  must have reached a terminal street).  In M0 the stub engine only
  transitions from preflop to the flop; showdown handling will be
  added in later milestones.
- If environment variables are not being read, create a `.env` file in
  the repository root or set them before starting the server.
