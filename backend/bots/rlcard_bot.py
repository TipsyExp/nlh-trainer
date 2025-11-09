# backend/bots/rlcard_bot.py
from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple, Mapping

from backend.bots.policy import BotPolicy, BotAction

_NUMX_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)x\s*$", re.IGNORECASE)


def _parse_x(label: str) -> Optional[float]:
    m = _NUMX_RE.match(str(label))
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _bucket_preference_order(to_call: int) -> List[str]:
    if to_call == 0:
        return ["2.2x", "2.5x", "3.0x", "jam"]
    return ["2.2x", "2.5x", "3.0x", "jam"]


def _find_first_present(allowed: List[str], prefs: List[str]) -> Optional[str]:
    s = {str(a).lower() for a in allowed}
    for p in prefs:
        if p.lower() in s:
            return p
    return None


def _smallest_numeric_label(allowed: List[str]) -> Optional[str]:
    best: Tuple[float, str] | None = None
    for lab in allowed:
        x = _parse_x(lab)
        if x is None:
            continue
        if best is None or x < best[0]:
            best = (x, lab)
    return best[1] if best else None


def _amount_for_label(
    label: str,
    *,
    to_call: int,
    bb: int,
    min_raise: int,
    is_raise: bool,
) -> int:
    label_l = str(label).lower().strip()
    if label_l in ("jam", "allin", "all-in"):
        base = to_call if is_raise else 0
        return max(min_raise or 0, base + 1_000_000_000)

    x = _parse_x(label_l)
    if x is not None:
        base = int(round(x * max(1, bb)))
        if is_raise:
            return max(min_raise or 0, int(to_call) + base)
        return max(min_raise or max(1, bb), base)

    if label_l == "call":
        return max(0, int(to_call))
    return max(min_raise or max(1, bb), int(to_call))


class RLCardBot(BotPolicy):
    """Placeholder RLCard bridge: discrete mapping to our engine actions.

    Mapping:
      - to_call == 0 : check | bet-small | bet-mid | jam
      - to_call > 0  : fold | call | raise-small | jam
    """

    def decide(self, ctx: Mapping[str, Any], rng: Any) -> BotAction:
        to_call = int(ctx.get("to_call") or 0)
        bb = int(ctx.get("bb") or 0)
        min_raise = int(ctx.get("min_raise") or 0)
        allowed_buckets = list(ctx.get("allowed_buckets") or [])
        first_action_this_street = bool(ctx.get("first_action_this_street"))

        if to_call == 0:
            if first_action_this_street and allowed_buckets:
                chosen = _smallest_numeric_label(
                    allowed_buckets
                ) or _find_first_present(
                    allowed_buckets, _bucket_preference_order(to_call)
                )
                if chosen:
                    amt = _amount_for_label(
                        chosen, to_call=0, bb=bb, min_raise=min_raise, is_raise=False
                    )
                    return {"action": "bet", "amount": amt}
            return {"action": "check"}

        raise_label = _smallest_numeric_label(allowed_buckets) or _find_first_present(
            allowed_buckets, _bucket_preference_order(to_call)
        )

        if raise_label and raise_label.lower() != "call":
            amt = _amount_for_label(
                raise_label, to_call=to_call, bb=bb, min_raise=min_raise, is_raise=True
            )
            return {"action": "raise", "amount": amt}

        return {"action": "call", "amount": to_call}


__all__ = ["RLCardBot"]
