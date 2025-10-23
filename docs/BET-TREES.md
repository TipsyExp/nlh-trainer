# Bet Trees

This document describes the bet sizing buckets, minimum raise rules and
snapping behaviour used by the NLH Trainer engine.  The engine uses a
coarse bucket model to simplify bet/raise decisions for the human
trainee while remaining consistent with common poker practice.

## Opening Buckets

When there is no pending bet (i.e. `to_call` is 0) or in heads‑up
preflop play when the small blind is first to act, the engine offers
a set of opening buckets.  Each bucket is defined by a label and a
**target** commitment amount (the total chips a player must be committed
to after taking the action).  The following buckets are presented in
ascending order:

| Label   | Target (HU preflop / multiway) | Meaning                                         |
|---------|--------------------------------|------------------------------------------------|
| `call`  | `to_call` (only if `to_call > 0`) | Match the current price without raising.        |
| `2.2x`  | `2.2 × BB`                       | Open to 2.2 times the big blind.               |
| `2.5x`  | `2.5 × BB`                       | Open to 2.5 times the big blind.               |
| `3.0x`  | `3.0 × BB`                       | Open to 3.0 times the big blind.               |
| `jam`   | `∞` (10¹² chips)                | All‑in; a sentinel bucket for very large bets. |

The engine computes each target as `round(mult × bb)` and ensures it is
at least equal to the big blind.  When a base raise size exists from
a previous street the appropriate formula is used (see facing buckets below).

## Facing Buckets

When a player is facing a bet (i.e. `to_call > 0`), the engine uses
the last raise size (or the big blind if no raise has occurred) to
construct facing buckets.  The buckets include:

| Label    | Target                           | Meaning                                       |
|----------|----------------------------------|-----------------------------------------------|
| `call`   | `to_call`                        | Call the outstanding bet.                    |
| `2.5xR`  | `to_call + 2.5 × max(bb, last_raise_size)` | Raise to 2.5× the last raise size.        |
| `3.0xR`  | `to_call + 3.0 × max(bb, last_raise_size)` | Raise to 3.0× the last raise size.        |
| `jam`    | `∞`                              | All‑in.                                        |

The `last_raise_size` is updated whenever a player raises and
influences subsequent facing buckets.  As with opening buckets, the
engine sorts the bucket list by target before presenting it.

## Minimum Raise Rule

In addition to bucket suggestions the engine enforces a *minimum
raise target*.  This value is returned via the `min_raise` field in
the `/api/hand/state` response.  It is computed as:

- **Opening** (`to_call ≤ 0`): `max(bb, last_raise_size)` – raising must
  be at least a full big blind (or the last raise size if larger).
- **Facing** (`to_call > 0`): `to_call + max(bb, last_raise_size)` –
  raising must add at least the size of the previous bet or the big
  blind to the amount needed to call.

Requests that fall below `min_raise` result in a `400` error from
the API.

## Snapping Behaviour

When a bet or raise request does not match exactly one of the
allowed bucket targets, the engine snaps the amount to the nearest
bucket.  The snapping process returns:

- `target` – the bucket’s target commitment (rounded integer).
- `snapped` – a boolean flag indicating whether the input was adjusted.
- `bucket_label` – the chosen bucket label.
- `allowed_buckets` – the list of all bucket labels available.

Extremely large requests trigger the special `jam` bucket.  The jam
“floor” is `max(bb × 100, max_non_jam_target × 20)` where
`max_non_jam_target` is the largest non‑jam bucket.  Requests
exceeding this floor are snapped directly to `jam`.

## Example

Suppose the big blind is 100 chips and no raise has occurred.  In a
multiway pot the allowed buckets are:

```
[{"label": "call", "target": 0},
 {"label": "2.2x", "target": 220},
 {"label": "2.5x", "target": 250},
 {"label": "3.0x", "target": 300},
 {"label": "jam", "target": 1000000000000}]
```

If a player requests to raise to 275 chips, the engine snaps the
amount to the nearest bucket (250 or 300).  Since 275 is closer to
250, the response includes `target=250`, `snapped=true`,
`bucket_label="2.5x"` and the full list of allowed buckets.
