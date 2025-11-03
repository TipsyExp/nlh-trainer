API Contract

This document defines the public API for the NLH-Trainer backend. Each route lists its method, path, parameters, and example responses captured from live runs. The examples referenced are stored under docs/examples/ and should be regenerated via docs/scripts/capture_examples.py whenever behavior changes.

Base URL

All endpoints are served under /api by the FastAPI app in backend/main.py. Responses are JSON unless otherwise noted.

Health

GET /api/health

Returns a simple heartbeat.

Response
{"ok": true}

Session

A session configures table parameters and groups hands.

Create/Reset Session

POST /api/session

Request body (typical)
{
  "seats": 2,
  "sb": 50,
  "bb": 100,
  "ante": 0,
  "stacks": [10000, 10000],
  "base_seed": "DOCS-EXAMPLE-SEED-1",
  "human_seat": 0
}
Notes

The server maintains a single active session in-process; no query params are required.

Fields shown reflect typical usage from the UI. Additional fields may be ignored or defaulted by the server.

Response
Taken from docs/examples/session_create.json:
{
  "detail": "session created/reset",
  "ok": true,
  "session_id": 1
}

Hand

Hands must be started before you can fetch state or act.

Start Hand

POST /api/hand/start

Starts a new hand in the active session.

Response
Taken from docs/examples/hand_start.json:
{"hand_id": "H1"}

Get Current Hand State

GET /api/hand/state

Returns the acting player context and a snapshot of public state for the current hand.

Response (excerpt)
From docs/examples/hand_state.json:
{
  "actor": {
    "allowed_buckets": ["call","2.2x","2.5x","3.0x","jam"],
    "min_raise": 150,
    "seat": 0,
    "to_call": 50
  },
  "state": {
    "deck_seed": "DOCS-EXAMPLE-SEED-1:1",
    "last_action": null,
    "players": [
      {"hole_cards": ["5s","4s"], "seat": 0},
      {"hole_cards": ["XX","XX"], "seat": 1}
    ],
    "pot_total": 0,
    "street": "preflop",
    "table": {
      "ante": 0,
      "bb": 100,
      "bb_seat": 1,
      "button": 0,
      "sb": 50,
      "sb_seat": 0,
      "seats": 2
    }
  }
}

Notes

Hole cards for non-hero seats are masked as "XX".

Bucket labels are defined in BET-TREES.md
{
  "action": "check" | "call" | "bet" | "raise" | "fold",
  "bucket": "2.5x" | "3.0x" | "jam" | null   // optional; required when betting/raising
}
On success, the server applies automatic bot responses (if any) and returns the updated state.

Response (excerpt)
From docs/examples/hand_action.json:
{
  "bots_applied": [
    {"action": "check", "amount": null, "seat": 1},
    {"action": "check", "amount": null, "seat": 1}
  ],
  "ok": true,
  "state": {
    "deck_seed": "DOCS-EXAMPLE-SEED-1:1",
    "last_action": {
      "allowed_buckets": null,
      "bucket_label": null,
      "committed": null,
      "requested": null,
      "seat": 1,
      "snapped": null,
      "type": "check"
    },
    "players": [
      {"hole_cards": ["5s","4s"], "seat": 0},
      {"hole_cards": ["XX","XX"], "seat": 1}
    ],
    "pot_total": 0,
    "street": "flop",
    "table": {
      "ante": 0, "bb": 100, "bb_seat": 1, "button": 0, "sb": 50, "sb_seat": 0, "seats": 2
    }
  }
}

Export

Completed hands/sessions can be exported in JSON or CSV. The JSON contains a final state snapshot and an actions array. The CSV has one row per action.

Stable CSV header (current format)
hand_id,idx,street,actor_seat,action,amount,bucket,to_call_after,pot_after,snapped,engine,evaluator

Export Hand (JSON)

GET /api/export/hand/{hand_id}.json

Shape
{
  "hand_id": "H1",
  "actions": [
    {
      "action": "call" | "check" | "bet" | "raise" | "fold",
      "actor_seat": 0,
      "amount": null | number,
      "bucket": null | "2.2x" | "2.5x" | "3.0x" | "jam",
      "engine": "PokerKit",
      "evaluator": "PokerKit",
      "idx": 0,
      "pot_after": 0,
      "snapped": null | true | false,
      "street": "preflop" | "flop" | "turn" | "river",
      "to_call_after": 0
    }
  ],
  "state": { /* final state snapshot */ }
}

See docs/examples/export_hand.json for a full example.

Export Hand (CSV)

GET /api/export/hand/{hand_id}.csv

Header and sample rows are shown in docs/examples/export_hand.csv.

Export Session (JSON)

GET /api/export/session/{session_id}.json

Returns an object with hands: [...], where each element has the same structure as a hand export.

See docs/examples/export_session.json.

Export Session (CSV)

GET /api/export/session/{session_id}.csv

Header is identical to hand CSV. Example: docs/examples/export_session.csv.

Conventions & Notes

Nullability: Some fields (e.g., amount, bucket, snapped) may be null depending on the action or phase.

Buckets: See BET-TREES.md
State shape: The state object in responses reflects the live implementation and may include derived fields such as pot_total and a summarized last_action.

Single-session model: This server operates a single in-memory session by default; /hand/* endpoints act on the active session/hand without requiring query parameters.

If you change response shapes or add/remove fields, regenerate examples with docs/scripts/capture_examples.py and update this document to match.
