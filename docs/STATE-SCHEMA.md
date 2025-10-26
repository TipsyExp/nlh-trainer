# State Schema

This document describes the structure of the game state objects returned by the NLH Trainer API.  These objects are serialised to JSON using Pydantic models in `backend/models/state.py`.  The schema below is authoritative for milestone M1.

## GameState

The top‑level state structure returned by `/api/hand/state` and included in the `state` object in export payloads.  All fields are required unless otherwise noted.

| Field | Type | Description |
|------|------|-------------|
| `hand_id` | string | Unique identifier for the hand. |
| `deck_seed` | string | Seed used to initialise the deck.  Allows deterministic replay. |
| `table` | object | Table configuration (see below). |
| `dealer_seat` | integer | Index of the dealer (button) seat. |
| `sb_seat` | integer | Index of the small blind seat. |
| `bb_seat` | integer | Index of the big blind seat. |
| `street` | string | Current street: one of `"preflop"`, `"flop"`, `"turn"`, `"river"`, or `"showdown"`. |
| `players` | array of PlayerState | Snapshot of each player’s status.  See PlayerState below. |
| `pot_total` | integer | Total chips in the pot, including blinds and antes. |
| `last_action` | object or null | The most recent action, with fields `idx`, `actor_seat`, `action`, and `amount`.  Null before any action has occurred. |
| `action_history` | array of ActionRecord | Chronological list of every action taken so far.  See ActionRecord below. |

### PlayerState

Represents a single seat at the table.

| Field | Type | Description |
|------|------|-------------|
| `seat` | integer | Seat index. |
| `type` | string | Either `"human"` or `"bot"`. |
| `alias` | string | Nickname of the player. |
| `stack` | integer | Number of chips remaining. |
| `status` | string | One of `"active"`, `"allin"`, `"folded"`, or `"out"`. |
| `hole_cards` | array of strings | Two card strings for the hero; bots show `?` until showdown. |

### Table

| Field | Type | Description |
|------|------|-------------|
| `seat_count` | integer | Number of seats at the table (e.g. 2 for heads‑up). |
| `sb` | integer | Size of the small blind. |
| `bb` | integer | Size of the big blind. |
| `ante` | integer | Ante posted by each player (zero in heads‑up examples). |

### ActionRecord

Each entry in `action_history` has the following fields:

| Field | Type | Description |
|------|------|-------------|
| `idx` | integer | Zero‑based index of the decision within the hand. |
| `street` | string | Street on which the action was taken. |
| `actor_seat` | integer | Seat index of the acting player. |
| `type` | string | Action type: `"fold"`, `"check"`, `"call"`, `"bet"`, `"raise"`, or `"allin"`. |
| `amount` | integer or null | Amount of chips bet or raised.  Null for folds and checks. |
| `bucket` | string or null | Bucket label chosen, if applicable (see [BET‑TREES](BET-TREES.md)). |
| `to_call_after` | integer | Chips needed to call after the action resolves. |
| `pot_after` | integer | Pot size immediately after the action. |
| `time_ms` | integer or null | Duration of the action in milliseconds, if measured. |
| `rng_seed` | integer or null | RNG seed used for randomised decisions (currently unused for the bot). |
| `snapped` | boolean | Whether the bet size was snapped to the nearest bucket. |
| `meta` | object or null | Reserved for solver metadata. |
| `engine` | string | Engine identifier (e.g. `"rlcard"`). |
| `evaluator` | string or null | Evaluator identifier, if used. |
| `created_at` | string | ISO‑8601 timestamp when the action was recorded. |

## Full Example

The following condensed example shows the structure of a GameState at the end of a hand.  It is derived from `docs/examples/export_hand.json`.  For brevity, only two actions are included in the `action_history`.

```json
{
  "hand_id": "H1",
  "deck_seed": "DOCS-EXAMPLES",
  "table": {"seat_count": 2, "sb": 5, "bb": 10, "ante": 0},
  "dealer_seat": 0,
  "sb_seat": 0,
  "bb_seat": 1,
  "street": "showdown",
  "players": [
    {"seat": 0, "type": "human", "alias": "Hero", "stack": 0, "status": "allin", "hole_cards": ["Td", "2s"]},
    {"seat": 1, "type": "bot", "alias": "Bot",  "stack": 0, "status": "allin", "hole_cards": ["?", "?"]}
  ],
  "pot_total": 1000,
  "last_action": {"idx": 39, "actor_seat": 1, "action": "call", "amount": 100, "street": "river"},
  "action_history": [
    {"idx": 0, "street": "preflop", "actor_seat": 0, "type": "call",  "amount": 10, "bucket": null, "to_call_after": 10, "pot_after": 25, "time_ms": null, "rng_seed": null, "snapped": false, "meta": null, "engine": "rlcard", "evaluator": null, "created_at": "2025-10-24T12:34:56Z"},
    {"idx": 1, "street": "preflop", "actor_seat": 1, "type": "raise", "amount": 30, "bucket": "3.0x", "to_call_after": 20, "pot_after": 55, "time_ms": null, "rng_seed": null, "snapped": false, "meta": null, "engine": "rlcard", "evaluator": null, "created_at": "2025-10-24T12:34:57Z"}
    // ...remaining actions omitted for brevity
  ]
}
```

Refer to `docs/examples/export_hand.json` for the full list of actions and the exact final state.
