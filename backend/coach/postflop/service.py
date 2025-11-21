# backend/coach/postflop/service.py
"""
Heads-up postflop coaching service (v1, equity-based).

This module implements a very small, conservative postflop coach used by
`/api/coach/advice` for HU flop/turn/river spots. It is intentionally simple:

* Only supports heads-up (n_players == 2).
* Requires a known hero hand and board.
* Uses `EquityService.hero_vs_range_equity` against a fixed villain range
  profile (see `backend.coach.postflop.ranges`).
* Produces an `AdviceV1` payload with:
    - meta.street / meta.n_players / meta.hero_seat / meta.source="equity"
    - recommendation.bucket and a single-entry strategy_bar
    - equity.hero populated with the computed equity
    - thresholds.pot_odds populated for call/fold decisions

The heuristics are deliberately lightweight and deterministic so they can be
easily tested and iterated on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional, cast

from backend.coach.decision_context import DecisionContext
from backend.coach.postflop.ranges import get_default_villain_range
from backend.schemas.advice import (
    AdviceEquity,
    AdviceMeta,
    AdviceRecommendation,
    AdviceThresholds,
    AdviceV1,
    StrategyPart,
)
from backend.services.equity.service import EquityService

StreetLiteral = Literal["preflop", "flop", "turn", "river", "showdown", "unknown"]


@dataclass
class PostflopCoachConfig:
    """
    Config for the HU postflop coach v1.

    These values are kept small and test-friendly; a later milestone may
    derive them from `backend.config`.
    """

    enabled: bool = True
    iters: int = 20000
    timeout_ms: int = 0
    # From the hero's perspective; we currently always treat villain as OOP.
    villain_role: str = "oop"
    # Margin over pot odds to classify "clear" folds/raises.
    min_equity_edge: float = 0.05


def _normalize_street(value: str) -> StreetLiteral:
    """
    Normalize arbitrary street strings into the AdviceMeta street literal set.
    """
    s = value.lower()
    if s in ("preflop", "flop", "turn", "river", "showdown", "unknown"):
        return cast(StreetLiteral, s)
    return "unknown"


def _compute_pot_odds(ctx: DecisionContext) -> Optional[float]:
    """
    Return required equity to continue given current price, or None.

    Using the convention:

        pot_odds = to_call / (pot_total + to_call)

    where pot_total is the pot size *before* hero acts.
    """
    if ctx.to_call <= 0:
        return None
    price = float(ctx.to_call)
    pot = float(ctx.pot_total)
    if price <= 0 or pot < 0:
        return None
    return price / (pot + price)


def _pick_bucket(
    ctx: DecisionContext,
    hero_equity: float,
    pot_odds: Optional[float],
    cfg: PostflopCoachConfig,
) -> str:
    """
    Simple heuristic for selecting a bucket given equity and price.

    Behaviour:
      * Facing a bet (to_call > 0):
          - Prefer fold if equity is clearly below pot odds.
          - Prefer a raise bucket if equity is clearly above pot odds.
          - Otherwise fall back to call.
      * No cost to continue (to_call == 0):
          - If 'check' + any bet bucket exist:
              - Bet when equity is clearly strong.
              - Otherwise check.
          - If no explicit 'check', just take the first bucket.
    """
    buckets = list(ctx.allowed_buckets or [])
    if not buckets:
        # Degenerate fallback; callers should ensure allowed_buckets is populated.
        return "check"

    if ctx.to_call <= 0:
        # Check / bet node.
        has_check = "check" in buckets
        bet_buckets = [b for b in buckets if b != "check"]

        if not has_check:
            # No explicit check; just take the first legal bucket.
            return buckets[0]

        # With a strong hand we choose the first bet-like bucket, otherwise check.
        if hero_equity >= 0.60 and bet_buckets:
            return bet_buckets[0]
        return "check"

    # Facing a bet/raise: fold/call/raise decision.
    has_call = "call" in buckets
    has_fold = "fold" in buckets
    raise_buckets = [b for b in buckets if b not in ("fold", "call", "check")]

    if pot_odds is None or not has_call:
        # No meaningful pricing; default to call when possible.
        return "call" if has_call else buckets[0]

    # Clear fold if equity is well below the required threshold.
    if has_fold and (hero_equity + cfg.min_equity_edge) < pot_odds:
        return "fold"

    # Clear raise if equity is well above the required threshold and raises exist.
    if raise_buckets and (hero_equity - cfg.min_equity_edge) > pot_odds:
        return raise_buckets[0]

    # Otherwise, call.
    return "call"


def build_postflop_advice(
    ctx: DecisionContext,
    equity_service: Optional[EquityService] = None,
    config: Optional[PostflopCoachConfig] = None,
) -> AdviceV1:
    """
    Build an AdviceV1 object for a HU postflop decision.

    The caller is expected to pass a DecisionContext describing the spot.
    Unsupported contexts (non-HU, unknown hero hand, non-postflop streets)
    return AdviceV1 with status="unsupported" (or "disabled" when the coach
    is turned off via config).
    """
    cfg = config or PostflopCoachConfig()

    street = _normalize_street(ctx.street)

    meta = AdviceMeta(
        street=street,
        n_players=ctx.n_players,
        hero_seat=ctx.hero_seat,
        source="equity",
    )

    rationale_common = (
        "Postflop coach v1 supports only enabled HU flop/turn/river "
        "spots with a known hero hand."
    )

    # Global gate: if coach is disabled, report that explicitly.
    if not cfg.enabled:
        return AdviceV1(
            version=1,
            status="disabled",
            meta=meta,
            recommendation=None,
            equity=None,
            thresholds=None,
            rationale=rationale_common,
        )

    # Basic gating: HU only, postflop only, known hero hand, non-terminal.
    if (
        ctx.n_players != 2
        or street not in ("flop", "turn", "river")
        or ctx.hero_hole_cards is None
        or len(ctx.hero_hole_cards) != 2
        or ctx.terminal
    ):
        return AdviceV1(
            version=1,
            status="unsupported",
            meta=meta,
            recommendation=None,
            equity=None,
            thresholds=None,
            rationale=rationale_common,
        )

    hero_cards = list(ctx.hero_hole_cards)
    hero_hand = (hero_cards[0], hero_cards[1])

    villain_range = get_default_villain_range(street=street, role="oop")

    svc = equity_service or EquityService()
    try:
        hero_equity = svc.hero_vs_range_equity(
            hero_hand=hero_hand,
            villain_range=villain_range,
            board=list(ctx.board),
            dead=(),
            iters=cfg.iters,
            exact=False,
            timeout_ms=cfg.timeout_ms,
        )
    except Exception as e:  # pragma: no cover - defensive, mapped to error
        return AdviceV1(
            version=1,
            status="error",
            meta=meta,
            recommendation=None,
            equity=None,
            thresholds=None,
            rationale=f"Postflop equity evaluation failed: {e}",
        )

    pot_odds = _compute_pot_odds(ctx)
    bucket = _pick_bucket(
        ctx,
        hero_equity=hero_equity,
        pot_odds=pot_odds,
        cfg=cfg,
    )

    recommendation = AdviceRecommendation(
        bucket=bucket,
        strategy_bar=[StrategyPart(action=bucket, weight=1.0)],
    )

    equity = AdviceEquity(
        backend=None,
        mode=None,
        hero=hero_equity,
        players=None,
        vs_field=None,
        exact=None,
        iters=None,
    )

    thresholds = AdviceThresholds(
        pot_odds=pot_odds,
        spr=None,
    )

    rationale_parts: List[str] = []
    rationale_parts.append(
        f"Hero equity ≈ {hero_equity:.3f} versus default villain range."
    )
    if pot_odds is not None:
        rationale_parts.append(f"Pot odds threshold ≈ {pot_odds:.3f}.")
    rationale_parts.append(f"Recommend {bucket} based on equity vs price.")

    return AdviceV1(
        version=1,
        status="ok",
        meta=meta,
        recommendation=recommendation,
        equity=equity,
        thresholds=thresholds,
        rationale=" ".join(rationale_parts),
    )


def get_postflop_advice(
    ctx: DecisionContext,
    equity_service: Optional[EquityService] = None,
    config: Optional[PostflopCoachConfig] = None,
) -> AdviceV1:
    """
    Backwards-friendly alias for the main postflop coach entrypoint.

    Existing callers may import `get_postflop_advice`; new code should prefer
    `build_postflop_advice`.
    """
    return build_postflop_advice(ctx, equity_service=equity_service, config=config)
