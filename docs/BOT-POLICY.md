# Bot Policy

Bot policies determine how automated opponents act when it's their turn.  A policy is a callable that receives a decision context and returns an action with an optional total commit amount.

## Decision context

Before each bot action, the engine builds a context object containing the information necessary to make a decision.  The following example illustrates its shape:

```json
{
  "seat": 0,
  "street": "flop",
  "bb": 100,
  "to_call": 0,
  "min_raise": 320,
  "allowed_buckets": ["check", "2.2x", "2.5x", "3.0x", "jam"],
  "in_position": false,
  "first_action_this_street": true,
  "button": 1,
  "sb_seat": 1,
  "bb_seat": 0
}
```

Policies must choose an action from the allowed buckets.  They should return an object of the form:

```json
{
  "action": "bet",
  "amount": 320
}
```

* `action` – one of `"fold"`, `"check"`, `"call"`, `"bet"`, or `"raise"`.  When `to_call` is zero the policy should use `"bet"` rather than `"raise"`.
* `amount` – the **total** commitment target when betting or raising. Policies should aim for the legal buckets implied by `allowed_buckets`. If the requested total is off-bucket, the engine will **snap** to the nearest legal total.

## Profiles and timeouts

Policies may implement different strategic profiles.  Two built‑in profiles are:

* `TAG` – tight‑aggressive: builds a range and chooses between calling, raising or folding based on hand strength.
* `CALLCHECK` – always checks or calls; never bets or raises.

The environment variables `BOT_TIME_BUDGET_MS` and `BOT_MAX_STEPS` control how long and how deep bot decisions may run.  Policies must honour these limits and return a safe fallback action when they expire.