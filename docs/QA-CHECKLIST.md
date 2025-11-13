# QA Checklist

Use this checklist to verify that the trainer backend and frontend behave correctly with the updated API semantics.

## Hand flow

* [ ] A new hand can be started via `/api/hand/start` and returns a state with `to_act` equal to the hero seat.
* [ ] If `BOT_MODE != "none"`, bots are auto‑advanced to the first human decision on hand start.
* [ ] `/api/hand/auto` returns HTTP `501` when `HAND_AUTO_ENABLED=false`.

## Action submission

* [ ] `amount` represents the **total** commitment when betting or raising; the engine snaps off‑tree totals to the nearest bucket.
* [ ] Minimum raise rule enforcement: a raise below `min_raise` returns HTTP `400` with a message like `"min-raise not met: need ≥ X, got Y"`.
* [ ] When `to_call=0` (including heads‑up SB open preflop), raise actions are normalised to `"bet"` and open buckets are `["2.2x","2.5x","3.0x","jam"]`.
* [ ] When facing a bet or raise (`to_call>0`), actions are normalised to `"raise"` and buckets have an `"R"` suffix: `["2.5xR","3.0xR","jam"]`.
* [ ] Off-tree requests set `last_action.snapped=true` and `last_action.committed` equals the snapped bucket total.
* [ ] CSV exports use **total** in the `amount` column (matches JSON), volatile columns are omitted (`created_at`, `time_ms`, `rng_seed`, `meta`), and EOLs are LF to avoid platform drift.

docs/BOT-POLICY.md — nudge about labels & snapping

@@

## Allowed actions

* [ ] `state.allowed` and the `actor` object correctly report `to_call`, `min_raise` and `allowed_buckets` for the current actor.
* [ ] After each action, `to_act` and `actor.seat` advance to the next seat, or become `null` when the hand ends.

## Debugging

* [ ] With `ENGINE_DEBUG_HTTP=true`, subscribe to `/api/debug/engine/events` and verify that an event is emitted for every transition (start, action, advance street, terminal).
* [ ] Invariants (`pot_non_decreasing`, `to_call_consistent`, `actor_valid`, `last_action_consistent`, `no_check_carryover`) are always `true`.
* [ ] Filtering events by street is case‑insensitive.

## Buckets

* [ ] Open buckets (`to_call=0`) are `["2.2x","2.5x","3.0x","jam"]`.
* [ ] Facing a bet or raise, buckets are `["2.5xR","3.0xR","jam"]`.
* [ ] `allowed.allowed_buckets` and `actor.allowed_buckets` match and reflect the correct list.