# Betting Trees and Bucket Definitions

This document defines the discrete bet sizes (“buckets”) supported by the NLH Trainer and explains the rules for determining minimum raises and snapping bets to the nearest bucket.  These definitions ensure that both the engine and the solver (when enabled) agree on allowed actions.

## Bucket Labels

Buckets are shorthand labels for common bet sizes.  They are relative to the size of the pot or last raise, and may differ between opening and response situations.

| Label | Meaning | When Used |
|------|---------|----------|
| `2.2x` | Open to 2.2× the big blind | Pre‑flop opening raises |
| `2.5x` | Open to 2.5× the big blind | Pre‑flop opening raises |
| `3.0x` | Open to 3.0× the big blind | Pre‑flop opening raises |
| `2.5xR` | Raise to 2.5× the previous bet size | Facing a prior bet or raise |
| `3.0xR` | Raise to 3.0× the previous bet size | Facing a prior bet or raise |
| `jam` | All‑in (jam) | Any time an all‑in is permitted |

Not all buckets are legal in every spot.  The engine returns the list of `allowed_buckets` for the acting player via the `/api/hand/state` endpoint.

## Minimum Raise Rules

The big blind (BB) is the fundamental unit used for determining minimum raises.

* **Opening action**: When no bet has been made, a raise must be at least the size of the big blind above the current bet.  For example, if blinds are 5/10, the smallest raise is to 20 (i.e. a raise of 10 chips on top of the big blind).
* **Facing action**: If a bet or raise has been made, a further raise must add **at least** the maximum of the big blind and the size of the previous raise.  For instance, if player A raised to 30 (a raise of 20 over the big blind), player B must raise to at least 50 (call to 30 plus a minimum raise of 20).

These rules mirror standard No‑Limit Hold’em regulations and prevent trivial min‑click raises.

## Snapping Policy

Because humans may not choose exactly one of the discrete bucket sizes (e.g. they might click a slider), the engine snaps arbitrary bet amounts to the nearest allowed bucket.  The snapping algorithm works as follows:

1. Compute the target raise size implied by each bucket based on the current pot or previous raise.
2. Find the allowed bucket whose implied amount is **closest** to the user’s requested amount.
3. On ties, snap to the **smaller** bucket (i.e. the one that yields a smaller raise).
4. If an all‑in (jam) floor heuristic applies (e.g. stack sizes are short), the `jam` bucket may override smaller raises.

### Examples

* **Pre‑flop opening**: Blinds are 5/10.  The `2.2x` bucket opens to 22 chips, `2.5x` opens to 25, and `3.0x` opens to 30.  A player attempting to open to 24 will be snapped down to `2.2x` (22) because it is closer than `2.5x` (25).
* **Facing a 30‑chip raise**: Allowed buckets might be `2.5xR` and `3.0xR`.  `2.5xR` raises to 2.5×30 = 75 chips, `3.0xR` raises to 90 chips.  A player clicking 80 chips will snap to `2.5xR` because 75 is closer than 90.
* **Jam floor**: If stack sizes are small relative to the pot, the engine may snap any raise above a certain threshold directly to `jam` to reflect typical all‑in decisions.

These rules ensure that autoplayer logic, the coach, and the solver operate on a shared discrete action space.
