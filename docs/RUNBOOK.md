# Runbook

This runbook provides a high‑level overview of how to run and interact with the trainer backend.  It reflects the latest API semantics.

## Starting the backend

Install dependencies and launch the server with [`uvicorn`](https://www.uvicorn.org/):

```bash
python -m pip install -r requirements.txt
uvicorn backend.main:app
```

Configure behaviour via environment variables.  See [Configuration](CONFIGURATION.md) for details.

## Creating a session

Use the `/api/session` endpoint to create a new session. Include table params to match your environment. For example:

```bash
curl -X POST http://localhost:8000/api/session \
  -H "Content-Type: application/json" \
  -d '{"seats": 2, "sb": 50, "bb": 100, "stacks": [10000,10000], "bot_mode": "heuristic", "bot_profile": "TAG"}'
```

The response contains a `session_id` which must be supplied to subsequent hand and action calls.

## Starting a hand

```bash
curl -X POST http://localhost:8000/api/hand/start \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "seat": 0}'
```

If bots are enabled (`BOT_MODE != "none"`), the engine will automatically apply all bot actions until it is the human's turn.  The response contains the full state and the actor information.

## Posting an action

```bash
curl -X POST http://localhost:8000/api/hand/action \
  -H "Content-Type: application/json" \
  -d '{"session_id": "...", "seat": 0, "action": "bet", "amount": 320}'
```

The `amount` is a **total** commitment target; the engine will snap off‑tree totals to the nearest bucket.  The response includes a pre‑bot snapshot of the state and an array of bot actions applied in response (`bots_applied`).

Tip: include an `X-Request-ID` header (any unique string) on API calls. This value is echoed in debug events and helps correlate requests with engine transitions.

## Auto‑stepping bots

For development convenience, bots can be auto‑advanced via `/api/hand/auto`.  Ensure `HAND_AUTO_ENABLED=true` and call:

```bash
curl -X POST http://localhost:8000/api/hand/auto \
  -H "Content-Type: application/json" \
  -d '{"session_id": "..."}'
```

When `HAND_AUTO_ENABLED=false`, this endpoint returns HTTP `501 Not Implemented`.

## Debugging

Set `ENGINE_DEBUG_HTTP=true` to enable structured debug events.  Subscribe to them via Server‑Sent Events at `/api/debug/engine/events`.  Use the `X-Request-ID` header on API calls to correlate client requests with engine transitions.

To capture a complete hand for analysis, call `/api/debug/engine/bundle` to download a ZIP archive of events and state.