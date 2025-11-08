# backend/bots/heuristics.py
from __future__ import annotations

import random
from typing import Any, List, Optional, Mapping

from .policy import BotPolicy, BotAction, validate_bot_action


def _clamp_int(v: Any, default: int = 0) -> int:
    try:
        iv = int(v)
        return iv if iv >= 0 else default
    except Exception:
        return default


def _pick_open_size(bb: int) -> int:
    """Choose a small open size; engine will snap to the nearest allowed bucket."""
    # Favor 2.2x for a conservative default.
    return max(bb, int(round(2.2 * bb)))


def _pick_min_raise(min_raise: int, to_call: int, bb: int) -> int:
    """Pick a minimal raise target when facing a bet."""
    # min_raise provided by adapter is already a *target total* (call + raise).
    return max(min_raise, to_call + bb)


class SimpleHuBot(BotPolicy):
    """
    Very simple HU heuristic:

    - If not facing a bet (to_call == 0): mostly check; sometimes small stab.
    - If facing a bet (to_call > 0): mostly call small/medium sizes; rarely raise small.
    - Never uses 'fold' or 'jam' because adapter doesn't implement them.
      (Adapter supports: 'check', 'call', 'bet', 'raise'.)

    The engine clamps/snap amounts to its allowed buckets.
    """

    def __init__(
        self,
        *,
        stab_prob: float = 0.25,  # chance to stab when unchecked
        raise_prob: float = 0.08,  # chance to raise instead of call when facing a bet
        small_call_bb_mult: float = 2.0,  # call if to_call <= 2*bb considered "small"
        seed: Optional[int] = None,
    ) -> None:
        self._rng = random.Random(seed)
        self.stab_prob = float(max(0.0, min(1.0, stab_prob)))
        self.raise_prob = float(max(0.0, min(1.0, raise_prob)))
        self.small_call_bb_mult = float(max(0.5, small_call_bb_mult))

    def decide(self, ctx: Mapping[str, Any], rng: Any) -> BotAction:
        # Prefer the deterministic RNG provided for this decision; fall back to self._rng.
        prng: random.Random
        if isinstance(rng, random.Random):
            prng = rng
        else:
            prng = self._rng

        street = str(ctx.get("street", "preflop")).lower()
        bb = _clamp_int(ctx.get("bb"), 100)
        to_call = _clamp_int(ctx.get("to_call"), 0)
        min_raise = _clamp_int(ctx.get("min_raise"), to_call + bb)
        allowed_buckets: List[str] = list(ctx.get("allowed_buckets") or [])

        # ---------- Not facing a bet ----------
        if to_call == 0:
            # Try a small probing bet sometimes (esp. earlier streets).
            stab_p = self.stab_prob
            if street == "turn":
                stab_p *= 0.8
            elif street == "river":
                stab_p *= 0.65

            if prng.random() < stab_p:
                amt = _pick_open_size(bb)
                move: BotAction = {"action": "bet", "amount": int(amt)}
                validate_bot_action(
                    move, to_call=to_call, allowed_buckets=allowed_buckets
                )
                return move

            move = {"action": "check"}  # type: ignore[typeddict-item]
            validate_bot_action(move, to_call=to_call, allowed_buckets=allowed_buckets)
            return move

        # ---------- Facing a bet ----------
        small_call_thresh = int(round(self.small_call_bb_mult * bb))

        # Prefer calling small/medium bets.
        if to_call <= small_call_thresh:
            # Occasionally take a small raise.
            if prng.random() < self.raise_prob:
                amt = _pick_min_raise(min_raise, to_call, bb)
                move = {"action": "raise", "amount": int(amt)}
                validate_bot_action(
                    move, to_call=to_call, allowed_buckets=allowed_buckets
                )
                return move

            move = {"action": "call"}  # type: ignore[typeddict-item]
            validate_bot_action(move, to_call=to_call, allowed_buckets=allowed_buckets)
            return move

        # For larger bets, mostly call (we don't have 'fold' implemented in adapter).
        # Rarely raise small to keep pressure.
        if prng.random() < max(0.02, self.raise_prob * 0.6):
            amt = _pick_min_raise(min_raise, to_call, bb)
            move = {"action": "raise", "amount": int(amt)}
            validate_bot_action(move, to_call=to_call, allowed_buckets=allowed_buckets)
            return move

        move = {"action": "call"}  # type: ignore[typeddict-item]
        validate_bot_action(move, to_call=to_call, allowed_buckets=allowed_buckets)
        return move


__all__ = ["SimpleHuBot"]
