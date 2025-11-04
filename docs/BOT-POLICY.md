# Bot Policy

The NLH Trainer ships with a deterministic bot system used for automated opponent
actions in tests and examples. The default behavior remains **check/call only** for
stability, and an optional **TAG** profile can be enabled via an environment
variable for a slightly richer, still deterministic flow.

---

## Profiles

| Profile       | Enabled by                      | Preflop                         | Postflop                                                   | Notes |
| ---           | ---                             | ---                             | ---                                                        | --- |
| `CALLCHECK`   | Default (no env needed)         | Check if `to_call == 0`, else call | Check if `to_call == 0`, else call                         | Never folds/raises. Used for docs/examples and baseline tests. |
| `TAG` (opt-in)| `BOT_PROFILE=TAG`               | Uses `range_manager` to pick fold/call/**raise bucket** | IP + first action on street + `to_call == 0` → **stab** with the **smallest simple Nx** bucket (e.g. `2.2x`); otherwise **check/call** | Deterministic via seeded RNG. Never raises postflop in this thin slice. |

> Determinism: bot decisions are driven by a seeded RNG constructed from
> `[base_seed, session_id, hand_id, decision_idx, bot_seat, "bot"]`. With the same
> path and seed, the bot produces identical actions across runs.

---

## Decision Details

### Default `CALLCHECK`
- **If `to_call == 0`** → `check`
- **Else** → `call`
- Applies **preflop and postflop**.
- Used by default to keep existing docs/examples stable.

### `TAG` (thin slice)

**Preflop**
- Uses the `range_manager` to obtain a structured choice:
{"action": "fold"|"call"|"raise", "bucket": "2.2x"|"2.5x"|..., "freq": float}

- If `action == "raise"` and the suggested bucket is **not** present in `allowed_buckets`,
snap **down** to the nearest allowed simple `Nx` size (down on ties).  
If nothing legal remains, **fall back to call**.
- Raise amounts are computed from bucket labels:
- For simple `Nx`: `amount = round(N * bb)` (total commitment).
- Missing charts fall back safely (prefer `call` over inventing raises).

**Postflop**
- If **in position (IP)**, **first action on the street**, and **`to_call == 0`**:
- **Bet (stab)** using the **smallest simple `Nx`** bucket in `allowed_buckets`
  (e.g., `2.2x`). *(Today the engine exposes `Nx`/`NxR` buckets, not %pot labels
  like `33`. When %pot labels appear, the policy can be updated to prefer those.)*
- Otherwise:
- **If facing a bet** → `call`
- **Else** → `check`
- No raises/folds postflop in this slice.

---

## Enabling the `TAG` Profile

**bash/zsh**
```bash
export BOT_PROFILE=TAG
uvicorn backend.main:app --reload

PowerShell
$env:BOT_PROFILE = "TAG"
uvicorn backend.main:app --reload

With BOT_PROFILE unset, the default CALLCHECK profile is used.
Logging & Exports

Each action (human or bot) is logged with:

idx (per-hand decision index), street, actor_seat, type, amount

bucket (as emitted by the engine), snapped (if engine auto-adjusts),

to_call_after, pot_after, and rng_seed (for replay/debugging).

Snapshots are upserted into hands after every action, so JSON/CSV exports
reflect mid-hand state.

Notes & Gotchas

Never invent labels. Bots only emit bucket labels that appear in the current
allowed_buckets.

Determinism: Avoid global random.* calls. All bot randomness must come
from the seeded RNG passed into the policy.

Docs/examples stability: The default profile remains CALLCHECK, so existing
example outputs don’t change.