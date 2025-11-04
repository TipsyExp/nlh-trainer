from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import re
import random


@dataclass
class Decision:
    action: str                  # "check" | "call" | "bet" | "raise"
    amount: Optional[int] = None # total commitment when betting/raising


class BaseBotPolicy:
    """
    Bot policy interface. Implementations must return a dict (or Decision-like)
    with at least {"action": "..."} and optional "amount" for bet/raise.
    """

    def decide(self, ctx: Dict[str, Any], rng: random.Random) -> Dict[str, Any]:
        """
        Args:
            ctx: {
              seat:int, street:str, bb:int, to_call:int, min_raise:int,
              allowed_buckets: List[str], in_position:bool, first_action_this_street:bool,
              button:int, sb_seat:int, bb_seat:int
            }
            rng: seeded RNG, deterministic per decision
        """
        raise NotImplementedError


class CallCheckBot(BaseBotPolicy):
    """Default behavior: check when nothing to call; otherwise call."""

    def decide(self, ctx: Dict[str, Any], rng: random.Random) -> Dict[str, Any]:  # noqa: ARG002
        to_call = int(ctx.get("to_call", 0))
        if to_call <= 0:
            return {"action": "check"}
        return {"action": "call"}


# --------- TagBot helpers ---------

_NX_RE = re.compile(r"^(?P<n>\d+(?:\.\d+)?)x$")


def _parse_nx(label: str) -> Optional[float]:
    m = _NX_RE.match(label or "")
    if not m:
        return None
    try:
        return float(m.group("n"))
    except ValueError:
        return None


def _amount_from_nx(n: float, bb: int) -> int:
    return int(round(n * bb))


def _first_simple_nx(allowed: List[str]) -> Optional[str]:
    for lab in allowed:
        if _parse_nx(lab) is not None:
            return lab
    return None


def _snap_nx_down(requested_label: str, allowed: List[str]) -> Optional[str]:
    """
    Snap a requested Nx label to the nearest allowed simple Nx, preferring snapping DOWN.
    If none <= requested exist, choose the smallest allowed simple Nx.
    Returns the chosen allowed label or None if no simple Nx exists.
    """
    req_n = _parse_nx(requested_label or "")
    pairs = [(lab, _parse_nx(lab)) for lab in allowed]
    nx_pairs = [(lab, n) for (lab, n) in pairs if n is not None]
    if not nx_pairs:
        return None

    # Exact hit
    for lab, n in nx_pairs:
        if req_n is not None and abs(n - req_n) < 1e-9:
            return lab

    if req_n is None:
        # No numeric meaning in request → pick smallest allowed simple Nx
        smallest = min(nx_pairs, key=lambda t: t[1])
        return smallest[0]

    # Prefer max n <= req_n
    below_or_eq = [p for p in nx_pairs if p[1] <= req_n + 1e-9]
    if below_or_eq:
        best = max(below_or_eq, key=lambda t: t[1])
        return best[0]

    # Else choose the absolute smallest
    smallest = min(nx_pairs, key=lambda t: t[1])
    return smallest[0]


class TagBot(BaseBotPolicy):
    """
    Thin-slice TAG profile.

    Preflop:
      - Ask range_manager for a deterministic action (fold/call/raise + size label)
      - If raise: snap requested Nx to nearest allowed simple Nx (down on ties).
      - Compute amount = round(N * bb) total commitment.
      - Fallback safely to call/check if nothing legal.

    Postflop:
      - If in-position, first action this street, and to_call == 0:
          bet the smallest simple Nx bucket present (e.g., "2.2x").
      - Otherwise: check when to_call==0, call when facing action.
      - No raises/folds postflop in this slice.
    """

    def decide(self, ctx: Dict[str, Any], rng: random.Random) -> Dict[str, Any]:  # noqa: ARG002
        street = str(ctx.get("street", "preflop"))
        to_call = int(ctx.get("to_call", 0))
        bb = int(ctx.get("bb", 100))
        allowed: List[str] = list(ctx.get("allowed_buckets", []))

        if street == "preflop":
            return self._decide_preflop(ctx, allowed, bb, to_call, rng)

        # Postflop thin rule
        in_pos = bool(ctx.get("in_position", False))
        first_action = bool(ctx.get("first_action_this_street", False))

        if to_call == 0 and in_pos and first_action:
            stab = _first_simple_nx(allowed)
            if stab is not None:
                n = _parse_nx(stab)
                if n is not None:
                    return {"action": "bet", "amount": _amount_from_nx(n, bb)}
            # If no simple Nx present, just check
            return {"action": "check"}

        # Facing a bet → call (no raises in this slice)
        if to_call > 0:
            return {"action": "call"}

        # Otherwise check
        return {"action": "check"}

    # ---- internals ----

    def _decide_preflop(
        self,
        ctx: Dict[str, Any],
        allowed: List[str],
        bb: int,
        to_call: int,
        rng: random.Random,
    ) -> Dict[str, Any]:
        # Lazily import to avoid hard dep for default bot paths
        from backend.policy import range_manager as rm

        seat = int(ctx.get("seat", -1))
        button = int(ctx.get("button", -1))

        # Simple HU mapping for position & facing; tests monkeypatch the manager so params aren't critical
        position = "SB" if seat == button else "BB"
        facing = "no_raise" if to_call == 0 else "facing_raise"

        # Range manager API:
        mgr = rm.get_manager()

        choice = None
        if hasattr(mgr, "choose_preflop"):
            # Preferred modern API
            choice = mgr.choose_preflop(position=position, facing=facing, stack_bb=100, rng=rng)
        elif hasattr(mgr, "choose_action"):
            # Back-compat with older API variants (different signatures):
            # Try rng-based signature first
            try:
                choice = mgr.choose_action(seat_count=2, position=position, facing=facing, rng=rng)  # type: ignore[arg-type]
            except TypeError:
                # Try seed-based signature
                try:
                    choice = mgr.choose_action(seat_count=2, position=position, facing=facing, seed="compat")  # type: ignore[call-arg]
                except TypeError:
                    # Oldest signature without rng/seed
                    choice = mgr.choose_action(seat_count=2, position=position, facing=facing)  # type: ignore[call-arg]
        else:
            # Very old or custom — safe fallback
            class _Fallback:
                def __init__(self) -> None:
                    self.action = "call"
                    self.size_label = None
            choice = _Fallback()

        act = str(getattr(choice, "action", "call"))
        size_label = getattr(choice, "size_label", None)

        if act == "fold":
            # fold unsupported in this thin slice engine → safe fallback
            return {"action": "check" if to_call == 0 else "call"}

        if act == "call" or not size_label:
            return {"action": "check" if to_call == 0 else "call"}

        # act == "raise": snap requested Nx to a legal allowed bucket (simple Nx only)
        snapped = _snap_nx_down(size_label, allowed)
        if snapped is None:
            # No legal simple Nx in allowed → fallback to call/check
            return {"action": "check" if to_call == 0 else "call"}

        n = _parse_nx(snapped)
        if n is None:
            return {"action": "check" if to_call == 0 else "call"}

        amount = _amount_from_nx(n, bb)
        return {"action": "bet" if to_call == 0 else "raise", "amount": amount}
