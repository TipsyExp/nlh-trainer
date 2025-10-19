from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple
import random

from .range_manager import get_manager, RangeChoice

@dataclass(frozen=True)
class BotProfile:
    name: str
    # Multipliers over chart weights
    fold_mult: float = 1.0
    call_mult: float = 1.0
    raise_mult: float = 1.0

# Stock profiles (tune as desired)
NIT      = BotProfile(name="NIT",      fold_mult=1.25, call_mult=0.9,  raise_mult=0.75)
TAG      = BotProfile(name="TAG",      fold_mult=1.0,  call_mult=1.0,  raise_mult=1.0)
LAG      = BotProfile(name="LAG",      fold_mult=0.85, call_mult=0.95, raise_mult=1.25)
STATION  = BotProfile(name="STATION",  fold_mult=0.8,  call_mult=1.3,  raise_mult=0.9)

@dataclass(frozen=True)
class BotContext:
    seat_count: int
    position: str             # e.g. "SB", "BB", "UTG", ...
    facing: str               # e.g. "no_raise", "vs_open_2.5x", "vs_open_3.0x"
    seed: Optional[str]       # usually the hand’s deck seed, e.g. "A:1"

def _adjust_distribution(base: Dict[str, Any], profile: BotProfile) -> Dict[str, Any]:
    """Apply profile multipliers to a base range distribution."""
    fold_w = max(0, int(round((base.get("fold", 0) or 0) * profile.fold_mult)))
    call_w = max(0, int(round((base.get("call", 0) or 0) * profile.call_mult)))
    raise_map = {}
    for lab, w in (base.get("raise") or {}).items():
        w2 = max(0, int(round((w or 0) * profile.raise_mult)))
        if w2 > 0:
            raise_map[str(lab)] = w2
    return {"fold": fold_w, "call": call_w, "raise": raise_map}

def _sample_weighted_pairs(rng: random.Random, pairs: Dict[Tuple[str, Optional[str]], int]) -> Tuple[str, Optional[str]]:
    total = sum(pairs.values())
    if total <= 0:
        return ("fold", None)
    x = rng.uniform(0, total)
    acc = 0.0
    for (act, lab), w in pairs.items():
        acc += w
        if x <= acc:
            return act, lab
    return ("fold", None)

def choose_preflop_action(ctx: BotContext, profile: BotProfile) -> RangeChoice:
    """
    Returns a RangeChoice(action, size_label, source).
    Deterministic for a given (ctx, profile) via seeded RNG.
    """
    rm = get_manager()
    dist = rm.lookup_distribution(ctx.seat_count, ctx.position, ctx.facing)

    if dist is None:
        # Same safe fallback policy as RangeManager.choose_action()
        if ctx.facing == "no_raise":
            return RangeChoice(action="fold", size_label=None, source="fallback")
        return RangeChoice(action="call", size_label=None, source="fallback")

    adj = _adjust_distribution(dist, profile)

    # Build (action,label)->weight
    pairs: Dict[Tuple[str, Optional[str]], int] = {}
    if adj.get("fold", 0) > 0:
        pairs[("fold", None)] = adj["fold"]
    if adj.get("call", 0) > 0:
        pairs[("call", None)] = adj["call"]
    for lab, w in (adj.get("raise") or {}).items():
        if w > 0:
            pairs[("raise", lab)] = w

    rng = random.Random()
    rng.seed(f"bot:{profile.name}:{ctx.seat_count}:{ctx.position}:{ctx.facing}:{ctx.seed}")
    act, lab = _sample_weighted_pairs(rng, pairs)
    return RangeChoice(action=act, size_label=lab, source="chart")
