
# State Schema

This document describes the shape of the `state` object returned by various API
endpoints. It includes the `allowed` subobject, enriched `last_action` fields,
and notes about how this state feeds the coach **decision context helper**.

## Top-level fields

| Field          | Type              | Description |
|---------------|-------------------|-------------|
| `table`       | Object            | Static table configuration (`seats`, `sb`, `bb`, `ante`, `button`, `sb_seat`, `bb_seat`). |
| `players`     | Array             | Array of player objects, each with a `seat` and `hole_cards` (masked as `"XX"` for hidden opponents), plus optional status in future extensions. |
| `street`      | String            | One of `"preflop"`, `"flop"`, `"turn"`, `"river"`, `"showdown"`. |
| `board`       | Object            | Contains `flop` (0–3 cards), `turn` (0–1 card) and `river` (0–1 card). |
| `deck_seed`   | String or null    | Deterministic seed used to reproduce the hand. |
| `pot_total`   | Integer           | Total size of the pot in chips. This value never decreases within a hand. |
| `to_act`      | Integer or null   | Seat index of the next actor, or `null` if the hand is terminal. |
| `allowed`     | Object or null    | Legal actions available to the player indicated by `to_act`. May be omitted or `null` when no actor is due. |
| `last_action` | Object or null    | Summary of the most recent engine action. |

The same `state` shape is returned:

- from `/api/hand/action` (post-human snapshot),
- from `/api/hand/auto` (post-bot snapshot),
- from `/api/hand/state`,
- and embedded in JSON exports under `state` for hands and sessions.

A subset of these fields is also used internally by the **coach decision
context helper** (see `backend/coach/decision_context.py` and
`docs/COACHING.md`) to build a normalized *decision context* for each
`(hand_id, idx)`.

---

## `allowed`

The `allowed` subobject describes what the current actor is allowed to do:

```json
"allowed": {
  "to_call": 50,
  "min_raise": 200,
  "allowed_buckets": ["fold", "call", "2.2x", "2.5x", "3.0x", "jam"]
}
•	to_call – amount the current actor must commit now to call the existing
bet. 0 means checking is allowed.
•	min_raise – total commitment required to meet the minimum raise rule. It is
computed as current_price + max(bb, last_raise_size).
•	allowed_buckets – list of legal bet or raise labels. When to_call is
0 (including the small blind opening heads-up), open buckets are typically
["2.2x","2.5x","3.0x","jam"]. When facing a bet or raise (to_call > 0),
raise buckets use an "R" suffix, e.g. ["2.5xR","3.0xR","jam"].
Labels are human-readable sizing classes; the engine resolves them to total
commitments for the current spot. It’s acceptable for callers to submit any
total and rely on snapping to the nearest legal bucket.
The coach decision context helper uses:
•	to_call → context.to_call
•	min_raise → context.min_raise
•	allowed_buckets → context.allowed_buckets
for pot-odds calculations and bucket validation.
________________________________________
last_action
The last_action object summarises the last action applied by the engine. It
is null when no actions have been taken.
Example:
"last_action": {
  "seat": 0,
  "type": "bet",
  "requested": 320,
  "committed": 320,
  "snapped": false,
  "bucket_label": "2.2x",
  "allowed_buckets": ["check", "2.2x", "2.5x", "3.0x", "jam"]
}
•	seat – index of the acting player.
•	type – normalised action verb: "fold", "check", "call", "bet", or
"raise". When the actor faced no bet (to_call was zero), raises are
recorded as "bet".
•	requested – total commitment target requested in the API call. Absent for
check/call/fold.
•	committed – actual total commitment applied after snapping to the nearest
bucket. Absent for check/call/fold.
•	snapped – boolean indicating whether the requested total was snapped to a
legal bucket.
•	bucket_label – human-friendly label of the bucket used. For check/call/fold
this is the same as the action verb.
•	allowed_buckets – list of legal buckets at the time of the action. Useful
for debugging and user feedback.
The decision context helper does not usually need last_action directly,
but it may be consulted by other subsystems for node classification and
debugging.
________________________________________
Nullability & terminal state
•	At the start of a hand (before any actions), last_action is null.
•	When the hand is terminal (street == "showdown"), to_act is null.
Implementations may omit allowed or return it empty in this state.
•	When to_act is not null but the engine cannot derive a legal action set
(e.g., due to an internal error), allowed may be omitted or set to a
conservative default.
________________________________________
Relationship to the coach decision context
The shared coach decision context (see backend/coach/decision_context.py)
derives its fields primarily from the engine’s internal state, but its public
semantics mirror this schema:
•	street ← state.street
•	board ← state.board (flattened flop / turn / river slices)
•	pot_total ← state.pot_total
•	hero_seat and n_players ← state.table and state.players (active seats)
•	to_call, min_raise, allowed_buckets ← state.allowed
•	hero hole cards / any revealed opponent cards ← state.players[*].hole_cards
•	deck_seed ← state.deck_seed (for reproducibility, when present)
This ensures that:
•	/api/coach/advice,
•	preflop advisor logic, and
•	any solver / equity-driven coach modules
all interpret a given decision (hand_id, idx) in a way that is consistent
with what the public /api/hand/* endpoints and exports expose.
