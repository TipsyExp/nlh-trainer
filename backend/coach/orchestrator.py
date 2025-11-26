# backend/coach/orchestrator.py
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

from backend.coach.decision_context import DecisionContext
from backend.coach.postflop.ranges import get_default_villain_range
from backend.adapters.solver.texassolver_adapter import (
    SolveRequest,
    UnsupportedSpotError,
)
from backend.coach.texassolver_cache import resolve_with_cache

if TYPE_CHECKING:
    # Only used for type-checking; instantiated lazily at runtime.
    from backend.coach.policies.preflop_hu_chart_policy import PreflopHUChartPolicy


# Singleton-ish policy instance (lazy-initialised below)
_PRE_HU_POLICY: Optional["PreflopHUChartPolicy"] = None


def _get_preflop_policy() -> Optional["PreflopHUChartPolicy"]:
    """Return a shared PreflopHUChartPolicy instance if available."""
    global _PRE_HU_POLICY
    if _PRE_HU_POLICY is not None:
        return _PRE_HU_POLICY

    try:
        from backend.coach.policies.preflop_hu_chart_policy import (
            PreflopHUChartPolicy as _Policy,
        )
    except Exception:  # pragma: no cover - defensive import
        return None

    _PRE_HU_POLICY = _Policy()
    return _PRE_HU_POLICY


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _is_hu(ctx: DecisionContext) -> bool:
    """True when exactly two seats appear active."""
    return ctx.n_players == 2


def _other_seat(ctx: DecisionContext, hero_seat: int) -> Optional[int]:
    """Return the other active seat in a HU pot, or None."""
    for s in ctx.active_seats:
        if s != hero_seat:
            return s
    return None


def _hero_is_ip_postflop(ctx: DecisionContext) -> Optional[bool]:
    """
    Determine whether hero is IP on flop/turn/river in a HU pot.

    Current engine semantics (PokerKitAdapter stub):
      - HU: button == sb_seat.
      - Postflop: BB (bb_seat) acts first, so IP seat is the other one.
    """
    if not _is_hu(ctx):
        return None
    if ctx.street not in ("flop", "turn", "river"):
        return None
    # OOP = BB, IP = the other seat
    oop = ctx.bb_seat
    if ctx.hero_seat == oop:
        return False
    return True


def _stacks_for_ip_oop(ctx: DecisionContext, hero_is_ip: bool) -> Tuple[int, int]:
    """
    Return (ip_stack, oop_stack) in chips.

    Best-effort: falls back to 0 if we can't find a stack for a seat.
    """
    hero_stack = ctx.hero_stack or 0
    villain_seat = _other_seat(ctx, ctx.hero_seat)
    villain_stack = (
        ctx.seat_stacks.get(villain_seat, 0) if villain_seat is not None else 0
    )

    if hero_is_ip:
        return hero_stack, villain_stack
    return villain_stack, hero_stack


# ---------------------------------------------------------------------------
# Preflop path (HU charts)
# ---------------------------------------------------------------------------


def _maybe_preflop_chart_advice(ctx: DecisionContext) -> Optional[Any]:
    """
    Try to produce preflop HU advice using the chart policy.

    Test expectations (backend/tests/test_orchestrator_preflop.py):

      * Orchestrator should delegate to
            preflop_hu_chart_policy.get_hu_preflop_advice(ctx, profile)
      * And return exactly whatever that function returns
        (e.g. a SentinelAdvice instance in tests).

    So we first call that function directly and only if it is unavailable
    or returns None do we fall back to the class-based policy wrapper.
    """
    if ctx.street != "preflop":
        return None
    if not _is_hu(ctx):
        return None

    # 1) Preferred / backwards-compatible path: function API
    try:
        from backend.coach.policies import preflop_hu_chart_policy as mod
    except Exception:  # pragma: no cover - module missing
        mod = None  # type: ignore[assignment]

    if mod is not None and hasattr(mod, "get_hu_preflop_advice"):
        try:
            func = getattr(mod, "get_hu_preflop_advice")
            # Profile string is not asserted in tests; any reasonable
            # default is fine here.
            adv = func(ctx, profile="default_100bb_2.5x")  # type: ignore[misc]
        except Exception:
            adv = None

        if adv is not None:
            # Important: return the advice object *as-is* so tests that
            # check isinstance(advice, SentinelAdvice) keep working.
            return adv

    # 2) Fallback: class-based wrapper (returns a dict) if available.
    policy = _get_preflop_policy()
    if policy is None:
        return None

    try:
        advice_dict = policy.build_advice(ctx)  # type: ignore[attr-defined]
    except Exception:
        return None

    return advice_dict


# ---------------------------------------------------------------------------
# Postflop path (TexasSolver)
# ---------------------------------------------------------------------------


def _build_solver_request(ctx: DecisionContext) -> Optional[SolveRequest]:
    """
    Construct a SolveRequest for a HU postflop spot from a DecisionContext.

    Limitations (v1):
      - Only HU pots.
      - Only flop/turn/river.
      - Hero range and villain range are currently generic TAG-ish ranges
        (we do not condition on the exact hero hand yet).
    """
    if not _is_hu(ctx):
        return None
    if ctx.street not in ("flop", "turn", "river"):
        return None

    hero_is_ip = _hero_is_ip_postflop(ctx)
    if hero_is_ip is None:
        return None

    ip_stack, oop_stack = _stacks_for_ip_oop(ctx, hero_is_ip)

    # For v1 we treat both players as having the same coarse TAG-ish range.
    # Future: use preflop history + hero's actual hand to build richer ranges.
    ip_range = get_default_villain_range(ctx.street, role="ip")
    oop_range = get_default_villain_range(ctx.street, role="oop")

    # Thin slice: use a simple bucket set that TexasSolverAdapter understands.
    # These DO NOT have to match the engine's engine buckets 1:1; they define
    # the internal solver tree. Advice buckets are mapped back to these labels.
    bucket_labels = ["50%", "60%", "jam"]

    return SolveRequest(
        street=ctx.street,
        board=ctx.board[:],
        pot=ctx.pot_total,
        ip_stack=ip_stack,
        oop_stack=oop_stack,
        ip_range=ip_range,
        oop_range=oop_range,
        bucket_labels=bucket_labels,
        spot="SRP",
    )


def _maybe_solver_advice(ctx: DecisionContext) -> Optional[Dict[str, Any]]:
    """
    Try to produce postflop HU advice via TexasSolver + cache.

    Returns:
        A dict payload with keys:
          - kind: "postflop_solver"
          - source: "texas_solver_v1"
          - recommended_bucket: str
          - strategy: Dict[str, float]
          - ev_map: Dict[str, float]
          - node_key: str (cache key)
          - cached: bool
        Or None if:
          - spot unsupported (preflop, non-HU, etc.),
          - solver disabled/misconfigured,
          - solver fails or times out.
    """
    req = _build_solver_request(ctx)
    if req is None:
        return None

    try:
        payload, cached, node_key = resolve_with_cache(req)
    except UnsupportedSpotError:
        # Unsupported street/tree/etc; just skip solver advice.
        return None
    except Exception:
        # Any unexpected solver/cache error → fail soft.
        return None

    recommended_bucket = payload.get("recommended_bucket")
    strategy = payload.get("strategy") or {}
    ev_map = payload.get("ev_map") or {}

    if not isinstance(recommended_bucket, str) or not strategy:
        # Malformed payload; treat as no advice.
        return None

    return {
        "kind": "postflop_solver",
        "source": "texas_solver_v1",
        "recommended_bucket": recommended_bucket,
        "strategy": dict(strategy),
        "ev_map": dict(ev_map),
        "node_key": node_key,
        "cached": bool(cached),
        # Optional debugging snapshot of the request we sent (safe subset only).
        "request": {
            "street": req.street,
            "board": req.board,
            "pot": req.pot,
            "ip_stack": req.ip_stack,
            "oop_stack": req.oop_stack,
            "bucket_labels": list(req.bucket_labels),
            "spot": req.spot,
        },
    }


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def get_advice_for_context(ctx: DecisionContext) -> Dict[str, Any]:
    """
    Top-level orchestrator for coaching.

    Strategy (v1):

      1. If the hand is already terminal → return a NOOP advice payload.
      2. If we're in a HU preflop spot and the HU preflop chart policy can
         handle it → delegate to get_hu_preflop_advice (functional API) and
         return whatever it returns.
      3. Else, if we're in a HU postflop spot that TexasSolverAdapter supports
         → return solver-based advice (with cache).
      4. Otherwise → return a NOOP advice payload.
    """
    # 1) Terminal spots: nothing to do.
    if ctx.terminal:
        return {
            "kind": "noop",
            "source": "orchestrator",
            "reason": "terminal",
        }

    # 2) Preflop HU chart policy (if available).
    pre = _maybe_preflop_chart_advice(ctx)
    if pre is not None:
        # NOTE: For HU preflop we intentionally return whatever the policy
        # returns (e.g. a PreflopHUAdvice or SentinelAdvice instance) to
        # remain backwards-compatible with existing tests.
        return pre  # type: ignore[return-value]

    # 3) Postflop HU solver advice.
    post = _maybe_solver_advice(ctx)
    if post is not None:
        return post

    # 4) Fallback NOOP.
    return {
        "kind": "noop",
        "source": "orchestrator",
        "reason": "unsupported_spot",
    }


__all__ = [
    "get_advice_for_context",
]
