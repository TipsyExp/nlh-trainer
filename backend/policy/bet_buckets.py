from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Tuple

@dataclass(frozen=True)
class SizeBucket:
    label: str        # e.g. "2.5x", "66%", "jam"
    to_total: int     # target total commitment for the actor (chips)

@dataclass
class BucketContext:
    street: str                 # "preflop" | "flop" | "turn" | "river"
    to_call: int                # chips needed to call
    min_raise_to: Optional[int] # if raising, minimum legal total to commit
    pot: int                    # current pot (chips)
    bb: int                     # big blind size (chips)
    last_raise_to: Optional[int] = None  # previous raise-to total (if any)
    actor_stack: int = 0        # remaining stack
    already_committed: int = 0  # actor's current street total

def _round_to_chip(x: float) -> int:
    return max(0, int(round(x)))

def _within_stack(target: int, stack: int) -> int:
    return min(target, stack)

def allowed_sizes(ctx: BucketContext) -> List[SizeBucket]:
    """
    Returns discrete bet/raise-to totals for the actor, filtered by min-raise and stack.
    """
    buckets: List[SizeBucket] = []
    # All sizing expressed as "to_total" (actor's total commitment after this action).
    jam_total = ctx.actor_stack

    if ctx.street == "preflop":
        if ctx.to_call == 0:
            # Open sizes (raise-to): 2.2x / 2.5x / 3x BB
            candidates = [
                ("2.2x", _round_to_chip(2.2 * ctx.bb)),
                ("2.5x", _round_to_chip(2.5 * ctx.bb)),
                ("3x",   _round_to_chip(3.0 * ctx.bb)),
            ]
        else:
            # Facing raise: 3-bet ~3x IP / ~3.5x OOP of last raise size.
            # We don't have position here; use 3.25x midpoint.
            last = (ctx.last_raise_to or (ctx.to_call + ctx.already_committed))
            delta = last - ctx.already_committed
            candidates = [
                ("~3x",  _round_to_chip(ctx.to_call + 3.0  * delta)),
                ("~3.5x",_round_to_chip(ctx.to_call + 3.5  * delta)),
            ]
    else:
        # Postflop opening bets (to_call==0): 33% / 66% / 100% pot
        if ctx.to_call == 0:
            candidates = [
                ("33%", _round_to_chip(0.33 * ctx.pot + ctx.already_committed)),
                ("66%", _round_to_chip(0.66 * ctx.pot + ctx.already_committed)),
                ("100%",_round_to_chip(1.00 * ctx.pot + ctx.already_committed)),
            ]
        else:
            # Raises ~2.5–3x of the bet size (approx by to_call)
            candidates = [
                ("~2.5x", _round_to_chip(ctx.already_committed + 2.5 * ctx.to_call)),
                ("~3x",   _round_to_chip(ctx.already_committed + 3.0 * ctx.to_call)),
            ]

    # Apply min-raise (if provided) and stack cap
    for label, tgt in candidates:
        tgt = _within_stack(tgt, jam_total)
        if ctx.min_raise_to is not None and tgt < ctx.min_raise_to:
            continue
        if tgt > ctx.already_committed:  # must be a real bet/raise
            buckets.append(SizeBucket(label, tgt))

    # Always include jam if it increases commitment
    if jam_total > ctx.already_committed:
        buckets.append(SizeBucket("jam", jam_total))

    # Deduplicate by to_total, keep first label
    seen = set()
    uniq = []
    for b in sorted(buckets, key=lambda b: b.to_total):
        if b.to_total in seen:
            continue
        seen.add(b.to_total)
        uniq.append(b)
    return uniq

def snap_size(requested_to_total: int, ctx: BucketContext) -> Tuple[int, bool, Optional[str]]:
    """
    Returns (snapped_to_total, snapped_flag, bucket_label).
    Chooses nearest bucket by absolute diff; ties prefer the smaller bucket.
    """
    candidates = allowed_sizes(ctx)
    if not candidates:
        return requested_to_total, False, None

    # Choose nearest by distance (prefer smaller on ties)
    best = min(
        candidates,
        key=lambda b: (abs(b.to_total - requested_to_total), b.to_total)
    )
    snapped = (best.to_total != requested_to_total)
    return best.to_total, snapped, best.label
