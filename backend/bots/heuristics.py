# backend/bots/heuristics.py
from __future__ import annotations

import random
import re
from typing import Any, List, Optional, Mapping

from .policy import BotPolicy, BotAction, validate_bot_action


_NUMX = re.compile(r"^(\d+(?:\.\d+)?)x$")


def _clamp_int(v: Any, default: int = 0) -> int:
    try:
        iv = int(v)
        return iv if iv >= 0 else default
    except Exception:
        return default


def _safe_validate(
    move: BotAction, *, to_call: int, allowed_buckets: List[str]
) -> None:
    # Be forgiving — if validation raises, swallow it and let the adapter snap/ignore.
    try:
        validate_bot_action(move, to_call=to_call, allowed_buckets=allowed_buckets)
    except Exception:
        pass


def _random_choice(
    rng: random.Random, items: List[Any], weights: Optional[List[float]] = None
):
    if not items:
        return None
    if weights is None:
        return rng.choice(items)
    total = sum(weights)
    if total <= 0:
        return rng.choice(items)
    # simple weighted choice
    x = rng.random() * total
    acc = 0.0
    for item, w in zip(items, weights):
        acc += w
        if x <= acc:
            return item
    return items[-1]


class RandomHuBot(BotPolicy):
    """
    Truly minimal random HU bot:

    - If to_call == 0:
        * 50% check
        * 50% bet: pick a random open bucket (2.2x/2.5x/3.0x) if present,
          otherwise bet ~2.2x BB (engine will snap).
    - If to_call > 0:
        * Random among fold / call / raise (weights configurable).
        * For raise: use min_raise, with a small chance to 'jam' if allowed.

    Validation errors are swallowed so the adapter can snap/ignore safely.
    """

    def __init__(
        self,
        *,
        p_check: float = 0.5,
        p_call: float = 0.45,
        p_fold: float = 0.25,
        p_raise: float = 0.30,
        p_jam_when_raise: float = 0.10,
        seed: Optional[int] = None,
    ) -> None:
        self.rng = random.Random(seed)
        # Normalize weights (defensively)
        s = max(1e-9, p_call + p_fold + p_raise)
        self.p_check = float(max(0.0, min(1.0, p_check)))
        self.p_call = float(p_call / s)
        self.p_fold = float(p_fold / s)
        self.p_raise = float(p_raise / s)
        self.p_jam_when_raise = float(max(0.0, min(1.0, p_jam_when_raise)))

    def act(self, state: Mapping[str, Any]) -> BotAction:
        table = state.get("table") or {}
        allowed = state.get("allowed") or {}

        bb = _clamp_int(table.get("bb"), 100)
        to_call = _clamp_int(allowed.get("to_call"), 0)
        min_raise = _clamp_int(allowed.get("min_raise"), 0)
        allowed_buckets: List[str] = list(allowed.get("allowed_buckets") or [])

        # --- No bet to face: choose between check / bet ---
        if to_call == 0:
            if self.rng.random() < self.p_check:
                move: BotAction = {"action": "check"}  # type: ignore[typeddict-item]
                _safe_validate(move, to_call=to_call, allowed_buckets=allowed_buckets)
                return move

            # Try to pick one of the provided open sizes if present
            open_labels = [b for b in allowed_buckets if _NUMX.match(b)]
            if open_labels:
                chosen = self.rng.choice(open_labels)
                m = _NUMX.match(chosen)
                mult = float(m.group(1)) if m else 2.2
                amount = max(bb, int(round(mult * bb)))
            else:
                amount = max(bb, int(round(2.2 * bb)))

            move = {"action": "bet", "amount": int(amount)}
            _safe_validate(move, to_call=to_call, allowed_buckets=allowed_buckets)
            return move

        # --- Facing a bet: random fold / call / raise ---
        # Build the menu based on what's legal
        choices: List[str] = []
        weights: List[float] = []

        # 'call' only if allowed shows it (the adapter exposes it explicitly)
        if "call" in allowed_buckets:
            choices.append("call")
            weights.append(self.p_call)

        # 'fold' is always a legal option when facing a bet
        choices.append("fold")
        weights.append(self.p_fold)

        # 'raise' is possible whenever we face a bet; adapter will enforce min-raise/snap
        choices.append("raise")
        weights.append(self.p_raise)

        action = _random_choice(self.rng, choices, weights)

        if action == "call":
            move = {"action": "call"}  # type: ignore[typeddict-item]
            _safe_validate(move, to_call=to_call, allowed_buckets=allowed_buckets)
            return move

        if action == "raise":
            # small chance to jam if offered
            if "jam" in allowed_buckets and self.rng.random() < self.p_jam_when_raise:
                move = {"action": "raise", "amount": 10**12}
                _safe_validate(move, to_call=to_call, allowed_buckets=allowed_buckets)
                return move

            # otherwise choose min_raise (engine will snap/accept)
            amount = min_raise if min_raise > 0 else to_call + max(1, bb)
            move = {"action": "raise", "amount": int(amount)}
            _safe_validate(move, to_call=to_call, allowed_buckets=allowed_buckets)
            return move

        # default: fold
        move = {"action": "fold"}  # type: ignore[typeddict-item]
        _safe_validate(move, to_call=to_call, allowed_buckets=allowed_buckets)
        return move


# Keep old import sites working: use the random bot as the default heuristic.
SimpleHuBot = RandomHuBot

__all__ = ["RandomHuBot", "SimpleHuBot"]
