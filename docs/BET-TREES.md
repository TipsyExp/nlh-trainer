# Bet Trees and Bucket Sizing

The trainer uses discrete bet buckets to simplify the decision space for automated policies and UI clients.  Each bucket label represents a **total** commitment to the pot.  The engine translates these labels into precise amounts based on the current blinds, pot and previous raises.

## Open and Stab Buckets

When the current actor faces no bet (`to_call = 0`) — including the small blind opening heads-up preflop — the legal bet buckets are:

```
["2.2x", "2.5x", "3.0x", "jam"]
```

**What the labels mean.** These labels are **human-readable sizing classes** that the engine resolves into **total commitment amounts** for the *current spot*. They are **not** always a literal `multiplier × bb`. The mapping depends on street, current price, and the previous raise size.

Clients have two safe options:
1) Compute a candidate total using the formulas below; or
2) Submit any total you wish; the engine will **snap** to the nearest legal bucket.

## Facing a Bet or Raise

When facing a bet or raise (`to_call > 0`), the sizing labels gain an `"R"` suffix to indicate **raise-relative** sizing:

```
["2.5xR", "3.0xR", "jam"]
```

In this context, `"2.5xR"` means the player commits a **total** amount equal to:

```
to_call + 2.5 × max(bb, last_raise_size)
```

where `last_raise_size` is the size of the previous raise. The backend resolves the exact totals for each bucket and will snap off-tree totals to the nearest bucket.

## Snapping and Jam

If a client requests a total amount that does not align exactly with a bucket, the engine snaps the value to the nearest legal bucket.  For example, a request for `305` when legal totals are `300` and `350` snaps to `300`. Requests above the largest bucket snap to `"jam"` (all-in).

## Minimum Raise

The minimum raise total is computed as:

```
min_raise_total = current_price + max(bb, last_raise_size)
```

A raise request below this total results in an HTTP `400` error with a descriptive message.
| Situation | Labels | Example resolved totals |
|---|---|---|
| Open (to_call = 0) | `["2.2x","2.5x","3.0x","jam"]` | e.g. `[320, 360, 420, jam]` |
| Facing bet/raise (`to_call > 0`) | `["2.5xR","3.0xR","jam"]` | e.g. if `to_call=220`, `last_raise_size=220` → `[540, 660, jam]` |