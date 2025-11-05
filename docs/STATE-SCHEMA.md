# State Schema

This document describes the **actual** JSON shapes the backend returns today (M1).  
There are two closely related snapshots you’ll see:

1) **Live state** – returned by `/api/hand/state` and `/api/hand/action` (under `state`).  
2) **Exported state** – embedded as `state` inside `/api/export/hand/{id}.json` and `/api/export/session/{id}.json`.

They differ slightly (e.g., where seat positions live, which fields are summarized).  
When behavior changes, re-run `docs/scripts/capture_examples.py` and update this document to match the captured examples.

---

## 1) Live State (for `/api/hand/state` and `/api/hand/action`)

Top-level object:

| Field        | Type                         | Description |
|-------------|------------------------------|-------------|
| `deck_seed` | string                        | Seed used to initialize the deck (e.g., `"DOCS-EXAMPLE-SEED-1:1"`). |
| `street`    | string                        | One of `"preflop"`, `"flop"`, `"turn"`, `"river"`. |
| `players`   | array of **PlayerLive**       | Minimal per-seat info for the UI (hero cards shown; opponents masked). |
| `table`     | **TableLive**                 | Table configuration + seat positions **nested under `table`**. |

> **Derived fields:** `pot_total` and `last_action` are not stored in the authoritative schema.  They are computed client‑side from the action history and may appear in live responses for convenience.

### 1.1 PlayerLive

Represents minimal seat/card visibility at the table.

| Field         | Type            | Description |
|---------------|-----------------|-------------|
| `seat`        | integer         | Seat index. |
| `hole_cards`  | array of string | Hero shows two cards (e.g., `["5s","4s"]`); opponents masked as `["XX","XX"]` until showdown. |

> Note: In live responses today, fields like `alias`, `type`, `stack`, and `status` are **not** included (they appear in exported state instead).

### 1.2 TableLive

| Field      | Type    | Description |
|------------|---------|-------------|
| `seats`    | integer | Number of seats (e.g. `2` for heads-up). |
| `sb`       | integer | Small blind amount. |
| `bb`       | integer | Big blind amount. |
| `ante`     | integer | Per-player ante (often `0` HU). |
| `button`   | integer | Dealer/button seat index. |
| `sb_seat`  | integer | Small blind seat index. |
| `bb_seat`  | integer | Big blind seat index. |

> Positions (`button`, `sb_seat`, `bb_seat`) are nested inside `table` in live responses.

### 1.3 LastActionSummary

A compact, UI-facing description of the most recent action. Present after `/api/hand/action` and `null` initially.

| Field             | Type                 | Description |
|-------------------|----------------------|-------------|
| `type`            | string               | `"fold"`, `"check"`, `"call"`, `"bet"`, `"raise"`, etc. |
| `seat`            | integer              | Acting seat for this last action. |
| `bucket_label`    | string \| null       | Bucket label if applicable (see BET-TREES.md); otherwise `null`. |
| `snapped`         | boolean \| null      | `true/false` if a bet/raise was snapped to a bucket; `null` when N/A. |
| `requested`       | integer \| null      | Raw user-entered size when present. |
| `committed`       | integer \| null      | Effective committed amount when present. |
| `allowed_buckets` | array \| null        | Usually `null` in this summary; present when relevant UI context exists. |

> This is **not** the full action record used in exports; it’s a concise summary for the table UI.

> In live responses, `actor.allowed_buckets` lists the bet/raise buckets available for the player who is about to act.  The `allowed_buckets` field inside `last_action` summarises the completed action and is usually `null` because it describes what has just happened rather than what is allowed next.

### 1.4 Live Example (excerpt)

From `docs/examples/hand_state.json` and `docs/examples/hand_action.json`:

```json
{
  "deck_seed": "DOCS-EXAMPLE-SEED-1:1",
  "street": "flop",
  "players": [
    {"seat": 0, "hole_cards": ["5s","4s"]},
    {"seat": 1, "hole_cards": ["XX","XX"]}
  ],
  "pot_total": 0,
  "table": {
    "ante": 0,
    "bb": 100,
    "bb_seat": 1,
    "button": 0,
    "sb": 50,
    "sb_seat": 0,
    "seats": 2
  },
  "last_action": {
    "type": "check",
    "seat": 1,
    "bucket_label": null,
    "snapped": null,
    "requested": null,
    "committed": null,
    "allowed_buckets": null
  }
}
```

## 2) Exported State (embedded under state in export payloads)

When you call:

GET /api/export/hand/{hand_id}.json

GET /api/export/session/{session_id}.json

…the state object inside each hand export looks slightly different from the live state:

| Field            | Type                          | Description                                                  |
| ---------------- | ----------------------------- | ------------------------------------------------------------ |
| `hand_id`        | string                        | Hand identifier (e.g., `"H1"`).                              |
| `deck_seed`      | string                        | Same seed used during the hand.                              |
| `table`          | **TableExport**               | Table configuration **with seat count** (no positions here). |
| `dealer_seat`    | integer                       | Dealer/button seat index (top-level in export).              |
| `sb_seat`        | integer                       | Small blind seat index (top-level in export).                |
| `bb_seat`        | integer                       | Big blind seat index (top-level in export).                  |
| `street`         | string                        | Final (or current at export time) street.                    |
| `players`        | array of **PlayerExport**     | Rich per-seat info (alias, type, stack, status).             |
| `action_history` | array of **ActionRecordLite** | Chronological list of actions so far (compact form).         |

Note: In exported state, positions are top-level (dealer_seat, sb_seat, bb_seat), and pot_total is not included.  
The total pot and timing metadata live with the per-action rows in the export actions list (see section 3).

### 2.1 PlayerExport
| Field    | Type    | Description                                    |
| -------- | ------- | ---------------------------------------------- |
| `seat`   | integer | Seat index.                                    |
| `type`   | string  | `"human"` or `"bot"`.                          |
| `alias`  | string  | Nickname.                                      |
| `stack`  | integer | Remaining stack at snapshot time.              |
| `status` | string  | `"active"`, `"allin"`, `"folded"`, or `"out"`. |

Opponent hole cards are not included here in current exports; visibility rules apply at showdown.

### 2.2 TableExport
| Field        | Type    | Description                   |
| ------------ | ------- | ----------------------------- |
| `seat_count` | integer | Number of seats at the table. |
| `sb`         | integer | Small blind.                  |
| `bb`         | integer | Big blind.                    |
| `ante`       | integer | Per-player ante.              |

### 2.3 ActionRecordLite (for state.action_history)

This list is a compact mirror of what happened, used for quick replay context inside the exported state.  
It is not the same as the richer per-action rows found under the top-level actions array in the export.

| Field           | Type           | Description                                             |
| --------------- | -------------- | ------------------------------------------------------- |
| `idx`           | integer        | Zero-based decision index.                              |
| `street`        | string         | Street on which the action occurred.                    |
| `actor_seat`    | integer        | Acting seat.                                            |
| `type`          | string         | `"fold"`, `"check"`, `"call"`, `"bet"`, `"raise"`, etc. |
| `amount`        | integer \| null | Chips bet/raised; `null` for check/fold.                |
| `bucket`        | string \| null  | Bucket label if applicable (see BET-TREES.md).             |
| `to_call_after` | integer        | To-call after the action resolves.                      |
| `pot_after`     | integer        | Pot size right after the action.                        |
| `snapped`       | boolean \| null | `true/false` when snapping applied; `null` when N/A.    |

Notice there is no engine, evaluator, time_ms, rng_seed, or created_at in action_history.  
Those appear with the top-level export actions (see below).

### 2.4 Exported State Example (excerpt)

From `docs/examples/export_hand.json`:

```json
{
  "hand_id": "H1",
  "deck_seed": "DOCS-EXAMPLE-SEED-1:1",
  "dealer_seat": 0,
  "sb_seat": 0,
  "bb_seat": 1,
  "street": "flop",
  "players": [
    {"seat": 0, "type": "human", "alias": "Hero", "stack": 10000, "status": "active"},
    {"seat": 1, "type": "bot", "alias": "Bot1", "stack": 10000, "status": "active"}
  ],
  "table": {"seat_count": 2, "sb": 50, "bb": 100, "ante": 0},
  "action_history": [
    {"idx": 0, "street": "preflop", "actor_seat": 0, "type": "call",  "amount": null, "bucket": null, "to_call_after": 0, "pot_after": 0, "snapped": null},
    {"idx": 1, "street": "flop",    "actor_seat": 1, "type": "check", "amount": null, "bucket": null, "to_call_after": 0, "pot_after": 0, "snapped": null}
  ]
}
```

## 3) Export Actions (top-level actions in export payloads)

In export_hand.json and export_session.json, each exported hand includes `actions: [...]`.  
These rows match the CSV columns and carry the richer metadata:

Stable CSV header (M1):

hand_id,idx,street,actor_seat,action,amount,bucket,to_call_after,pot_after,snapped,engine,evaluator

*The CSV header and JSON field set above are considered stable for M1; future versions will be versioned in docs and capture outputs.*

ExportAction fields (JSON):
| Field           | Type           | Description                                             |
| --------------- | -------------- | ------------------------------------------------------- |
| `idx`           | integer        | Zero-based decision index.                              |
| `street`        | string         | Street.                                                 |
| `actor_seat`    | integer        | Acting seat.                                            |
| `action`        | string         | `"fold"`, `"check"`, `"call"`, `"bet"`, `"raise"`, etc. |
| `amount`        | integer \| null | Chips bet/raised; `null` for check/fold.                |
| `bucket`        | string \| null  | Bucket label when applicable.                           |
| `to_call_after` | integer        | To-call after resolution.                               |
| `pot_after`     | integer        | Pot right after the action.                             |
| `snapped`       | boolean \| null | `true/false` if snapping occurred; `null` when N/A.     |
| `engine`        | string         | Engine identifier (e.g., `"PokerKit"`).                 |
| `evaluator`     | string \| null  | Evaluator identifier (e.g., `"PokerKit"`), or `null`.   |

Not present in current exports: time_ms, rng_seed, meta, created_at.  
If those get added later, update this schema and the CSV header accordingly.

ExportAction example (from `docs/examples/export_hand.json`):

```json
{
  "idx": 0,
  "street": "preflop",
  "actor_seat": 0,
  "action": "call",
  "amount": null,
  "bucket": null,
  "to_call_after": 0,
  "pot_after": 0,
  "snapped": null,
  "engine": "PokerKit",
  "evaluator": "PokerKit"
}
```

4) Notes & Invariants

Masking: Opponent hole cards are `"XX"` in live state until showdown.

Buckets: Labels and semantics are defined in BET-TREES.md. Off-tree sizes may be snapped; when snapping is not applicable, `snapped` is null.

Shape differences:

Live state nests positions inside `table`.  Some fields such as `pot_total` and `last_action` are computed client‑side from the action history and may appear in responses for convenience.

Exported state moves positions to top-level, omits `pot_total`, and includes a compact `action_history`.

Rich per-action metadata appears only in the top-level export actions array (and CSV).

Stability: The CSV header and JSON field set above are considered stable for M1.  If runtime fields change, regenerate examples and update this schema and the CSV header accordingly.