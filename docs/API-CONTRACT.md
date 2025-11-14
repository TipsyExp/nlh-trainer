# API Contract

This document describes the HTTP API exposed by the trainer backend.  The contract has been updated to reflect recent behavioural changes, including total‑amount semantics for bet sizing, pre‑bot snapshots in responses, and unified gating via environment variables.

## POST `/api/hand/action`

Submits an action on behalf of the human player.  The request must specify the acting seat, the type of action, and—when betting or raising—the **total committed amount** (not the delta).  Off‑tree totals are snapped to the nearest legal bucket.

### Request

```json
{
  "seat": 0,
  "action": "bet",
  "amount": 320
}
```

* `seat` – seat index of the acting player.
* `action` – one of `"fold"`, `"check"`, `"call"`, `"bet"`, or `"raise"`.  When `to_call` is zero (including a true heads‑up small blind open preflop), a raise is normalised to a `"bet"`.
* `amount` – the **total** stack commitment target for `"bet"` or `"raise"`.  The backend will map the request to one of the allowed buckets, snapping off‑tree totals up or down.  Requests below the minimum raise total will trigger an HTTP `400` error.

An invalid amount yields a descriptive error:

```json
{ "detail": "min-raise not met: need ≥ 320, got 220" }
```

### Response

The response always reports the state *before* any bot actions are applied.  Subsequent bot moves are returned separately.

```json
{
  "ok": true,
  "bots_applied": [
    { "seat": 1, "action": "call", "amount": null }
  ],
  "state": {
    "table": { "seats": 2, "sb": 50, "bb": 100, "ante": 0, "button": 1, "sb_seat": 1, "bb_seat": 0 },
    "players": [
      { "seat": 0, "hole_cards": ["Ah", "Ad"] },
      { "seat": 1, "hole_cards": ["XX", "XX"] }
    ],
    "street": "flop",
    "board": { "flop": ["Jh", "Qs", "8h"], "turn": [], "river": [] },
    "deck_seed": "T08:4",
    "pot_total": 420,
    "to_act": 1,
    "allowed": {
      "to_call": 220,
      "min_raise": 540,
      "allowed_buckets": ["fold", "call", "2.5xR", "3.0xR", "jam"]
    },
    "last_action": {
      "seat": 0,
      "type": "bet",
      "requested": 320,
      "committed": 320,
      "snapped": false,
      "bucket_label": "2.2x",
      "allowed_buckets": ["check", "2.2x", "2.5x", "3.0x", "jam"]
    }
  }
}
```

* `bots_applied` – a list of auto-applied bot actions after the human move.  Each entry contains the bot seat, the normalised action, and its total amount (if applicable).
* `state` – the full game state, described in [State Schema](STATE-SCHEMA.md).
* `last_action` – a summary of the human action, including the requested total, the actual amount committed, whether snapping occurred, the bucket label, and the list of allowed buckets at the time.

**Important:** Bucket labels (e.g. `2.2x`, `2.5xR`) are **human-readable sizing classes**, not a literal “multiplier × big blind.” The exact numeric totals are **contextual** (street, current price, last raise size). Clients may compute a candidate total using the rules in [Bet Trees](BET-TREES.md), but it’s also fine to submit any total; the engine will **snap** it to the nearest legal bucket and indicate this with `last_action.snapped`.

## GET `/api/hand/state`

Returns the current game state and information about the actor whose turn it is.

```json
{
  "state": { /* same shape as above */ },
  "actor": {
    "seat": 1,
    "to_call": 220,
    "min_raise": 540,
    "allowed_buckets": ["fold", "call", "2.5xR", "3.0xR", "jam"]
  }
}
```

The `actor` object contains redundant information about the current actor; its fields mirror `state.to_act` and `state.allowed`.

## POST `/api/hand/start`

Starts a new hand.  If the session is configured with a bot mode other than `"none"`, the engine will automatically play out all bot actions until the first human decision.

## POST `/api/hand/auto`

Auto‑advances the engine by applying bot actions until it is the human player's turn again.  This endpoint is gated by the environment variable `HAND_AUTO_ENABLED`.  When disabled it returns HTTP `501` and should not be called.  When enabled, it returns the same structure as a normal action response:

```json
{
  "ok": true,
  "bots_applied": [...],
  "state": { ... }
}
```

## Conventions & Notes

* **Min‑raise formula** – The minimum raise total is computed as `current_price + max(bb, last_raise_size)`.  Attempting to raise below this threshold yields a `400`.
* **Buckets** – Allowed bet sizes are published as human‑readable labels.  When `to_call` is `0` or when opening heads‑up as the small blind, open buckets are [`"2.2x"`, `"2.5x"`, `"3.0x"`, `"jam"`].  When facing a bet or raise, the buckets acquire an `"R"` suffix, for example `"2.5xR"`.  All labels refer to **total** commitment targets.
* **Snapping** – Requests between buckets are snapped to the nearest bucket.  The response sets `snapped=true` when this occurs and reports the snapped `committed` amount.
* **Pre‑bot snapshot** – Both `/api/hand/action` and `/api/hand/auto` return the state *before* any bot actions.  Auto‑played moves are listed in the `bots_applied` array.
* **Gating** – `HAND_AUTO_ENABLED` controls exposure of `/api/hand/auto` and whether bots auto‑advance after human actions.  The initial auto‑advance on `/api/hand/start` always occurs when the session's `bot_mode` is not `"none"`.
* **Debugging** – When `ENGINE_DEBUG_HTTP` is `true`, structured debug events are emitted.  See [debugging](debugging.md) for details.

## Errors
 The API returns structured errors with descriptive messages:
 
 | Status | When | Example body |
 |-------:|------|--------------|
 | 400 | Minimum raise total not met | { "detail": "min-raise not met: need ≥ 540, got 500" } |
 | 409 | Action submitted when it isn’t the hero’s turn | { "detail": "not your turn" } |
 | 422 | Validation error (shape/verb) | Pydantic validation message |
 | 501 | /api/hand/auto disabled by gating | { "detail": "auto-advance is disabled" } |
 
 ### Worked example: minimum raise total
 
 Assume bb = 100, current price (total to call) is 320, previous raise size was 220.
 
 ```
 min_raise_total = current_price   max(bb, last_raise_size)

            = 320   max(100, 220)
            = 540

 ```
 
 Submitting "raise": 500 will return 400 with a descriptive message; submitting 520 may snap to the legal bucket (e.g. 540) and report snapped=true.

## “Equity helper (dev-only)” section

```md
## POST `/api/equity` (dev-only helper)

Computes hand/range equities using the configured backend policy. Intended for development/testing and coach research; not required by the core table flow.

### Request
```json
{
  "players": [
    { "hand": ["Ah", "Ad"] },
    { "hand": ["Kh", "Qh"] }
  ],
  "board": ["As", "Kd", "2c"],
  "dead": [],
  "iters": 20000,
  "exact": false
}

Ranges example (requires pbots_calc):
{
  "players": [
    { "range": "JJ+" },
    { "range": "random" }
  ],
  "iters": 50000
}

Response
{
  "ok": true,
  "backend": "pbots_calc",
  "mode": "hands",
  "n_players": 2,
  "board": ["As","Kd","2c"],
  "dead": [],
  "exact": false,
  "iters": 20000,
  "players": [
    { "win": 12345, "tie": 234, "equity": 0.8123 },
    { "win": 2765,  "tie": 234, "equity": 0.1877 }
  ],
  "raw": { "simulations": 20000 }
}

Errors
•	400 invalid input (bad/missing cards, conflicting hand/range, too many board cards).
•	400 backend unavailable for requested mode (e.g., ranges without pbots_calc when EQUITY_BACKEND_POLICY=pbots).
Backend selection
EQUITY_BACKEND_POLICY (default auto):
•	auto: first compatible backend (tries pbots_calc if installed; else Henry; else PokerKit).
•	pbots: force pbots_calc (supports ranges + hands, exact/MC).
•	henry: force Henry evaluator placeholder (hands only).
•	pokerkit: pure-Python fallback (hands only).
Note: This endpoint is a helper for analysis/dev. Production UI need not call it.

