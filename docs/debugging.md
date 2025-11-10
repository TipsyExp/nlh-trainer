# Debugging the NLH Trainer Engine

This document describes how to enable and use the backend debug tooling to
inspect the internal state machine of the NLH trainer.  These capabilities
are intended for developers and are **not** enabled in production.  All
debug routes live under `/api/debug/engine` and are guarded behind the
`ENGINE_DEBUG_HTTP` environment flag.

## Enabling debug endpoints

Set the `ENGINE_DEBUG_HTTP` environment variable to one of `1`, `true`,
`yes` or `on` before starting the backend.  When enabled, the adapter
emits a structured event for every state transition.  Each event includes:

- `ts_ms` – monotonic wall‑clock timestamp (milliseconds).
- `seq` – strictly increasing sequence number.
- `hand_id` – current hand identifier.
- `street` – current street (preflop/flop/turn/river/showdown).
- `kind` – event type (start_hand, action, advance_street, etc.).
- `pot` and `price` – total pot and current price to call.
- `actor_before` / `actor_after` – seat index whose turn it was before
  and after the event.
- `state_hash` – short hash of key state fields (street, price, pot,
  committed chips and actor).
- `delta` – a diff of fields that changed since the previous event.
- `req_id` – request ID attached by middleware (correlates to HTTP
  requests).
- `invariants` – boolean flags for common consistency checks (pot monotonicity,
  to_call consistency, actor validity, last action semantics).
- Optional latency metrics (`latency_ms`) when the event originates from
  `apply_action`.

## API reference

```
GET /api/debug/engine/events?since={seq}&limit={n}&hand_id={hid}&street={street}
  Return the most recent debug events filtered by sequence number, hand ID
  or street.  The `since` parameter returns events with `seq > since`.

GET /api/debug/engine/snapshot
  Return the full internal engine state, including committed amounts,
  current price, next actor and last action metadata.  This is useful
  for verifying that the UI matches the backend truth.

GET /api/debug/engine/diff?from_seq={a}&to_seq={b}
  Compute a compact diff between two events.  Only fields that differ
  between the two events are returned.

GET /api/debug/engine/config
  Inspect the effective debug configuration: environment toggles, ring
  buffer size and sampling flags.

POST /api/debug/engine/export?sanitize={true|false}
  Export a ZIP bundle containing `events.json`, `snapshot.json`,
  `config.json` and `seeds.json`.  Sanitization masks hole cards for
  non‑human seats and removes request bodies.
```

## Examples

The `docs/examples/debug` directory contains a few scripts to help you
fetch and inspect debug data from the command line.

- **events-basic.sh / .ps1** – follow the debug event stream with `curl`.
- **snapshot.sh / .ps1** – print the current engine snapshot as JSON.

Below is a minimal example using `curl`:

```bash
#!/bin/bash
# Fetch the last 50 events since sequence 0
curl -s 'http://localhost:8000/api/debug/engine/events?since=0&limit=50' | jq .
```

On Windows PowerShell:

```powershell
# Fetch a snapshot of the engine
Invoke-RestMethod 'http://localhost:8000/api/debug/engine/snapshot' | ConvertTo-Json -Depth 4
```

Interpret the `delta` field as the difference between consecutive events.  A
non‑empty `invariants` object with any `false` flags indicates a potential
bug or mismatch between expected and actual state transitions.