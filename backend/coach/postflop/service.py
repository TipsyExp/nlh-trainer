# backend/coach/postflop/service.py
"""
Postflop coaching service (v1, equity-based).

This module implements a conservative postflop coach used by
`/api/coach/advice` for flop/turn/river spots. It started as HU-only and
now includes a simple multiway path when the equity backend supports it.

Current scope:

* Requires a known hero hand and board.
* Uses `EquityService` against default villain range profiles
  (see `backend.coach.postflop.ranges`).
* HU:
    - Uses `hero_vs_range_equity` vs a single villain range.
* Multiway (n_players > 2):
    - Uses range-based multiway equity with one generic villain range per
      active villain seat when the backend supports ranges + multiway.

Produces an `AdviceV1` payload with:

* meta.street / meta.n_players / meta.hero_seat / meta.source="equity"
* recommendation.bucket and a single-entry strategy_bar
* equity.hero populated with the computed equity
* equity.players populated for multiway when available
* thresholds.pot_odds populated for call/fold decisions

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
    AdviceEquityPlayer,
    AdviceMeta,
    AdviceRecommendation,
    AdviceThresholds,
    AdviceV1,
    StrategyPart,
)
from backend.services.equity.service import EquityService

StreetLiteral = Literal["preflop", "flop", "turn", "river", "showdown", "unknown"]
EquityModeLiteral = Literal["hands", "ranges"]


@dataclass
class PostflopCoachConfig:
    """
    Config for the postflop coach v1.

    These values are kept small and test-friendly; a later milestone may
    derive them from `backend.config`.
    """

    # Global postflop coach gate (HU + multiway).
    enabled: bool = True

    # HU equity settings.
    iters: int = 20000
    timeout_ms: int = 0
    # From the hero's perspective; we currently always treat villain as OOP.
    villain_role: str = "oop"
    # Margin over pot odds to classify "clear" folds/raises.
    min_equity_edge: float = 0.05

    # Multiway-specific settings.
    multiway_enabled: bool = True
    multiway_iters: int = 30000
    multiway_timeout_ms: int = 0


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


def _flatten_board_like(obj: object) -> List[str]:
    """
    Best-effort normalisation of a board-like object into a flat list of
    card strings.

    Handles:
      * Dicts like {"flop":[...], "turn":[...], "river":[...]}.
      * Engine-style objects with .flop / .turn / .river attributes.
      * Lists / tuples, including list-of-lists.
    """
    cards: List[str] = []
    if obj is None:
        return cards

    # Dict-like: {"flop":[...], "turn":[...], "river":[...]}
    if isinstance(obj, dict):
        for key in ("flop", "turn", "river"):
            seg = obj.get(key)
            if isinstance(seg, (list, tuple)):
                for c in seg:
                    if isinstance(c, str):
                        cards.append(c)
                    elif c is not None:
                        cards.append(str(c))
            elif isinstance(seg, str):
                cards.append(seg)
        if cards:
            return cards

    # Object with flop/turn/river attributes (engine board dataclass)
    has_attr = any(hasattr(obj, attr) for attr in ("flop", "turn", "river"))
    if has_attr:
        for attr in ("flop", "turn", "river"):
            seg = getattr(obj, attr, None)
            if isinstance(seg, (list, tuple)):
                for c in seg:
                    if isinstance(c, str):
                        cards.append(c)
                    elif c is not None:
                        cards.append(str(c))
            elif isinstance(seg, str):
                cards.append(seg)
        if cards:
            return cards

    # Generic sequence: flatten one level
    if isinstance(obj, (list, tuple)):
        for item in obj:
            if isinstance(item, (list, tuple)):
                for inner in item:
                    if isinstance(inner, str):
                        cards.append(inner)
                    elif inner is not None:
                        cards.append(str(inner))
            elif isinstance(item, str):
                cards.append(item)
            elif item is not None:
                cards.append(str(item))
        return cards

    return cards


def _resolve_board_for_equity(ctx: DecisionContext) -> List[str]:
    """
    Resolve a robust board representation suitable for the equity engine.

    Priority:
      1. ctx.board (already "public" form from DecisionContext).
      2. ctx.raw_state.board (engine-native shape) as a fallback.
      3. Empty board as a last resort.

    Guarantees that the returned board length is in {0, 3, 4, 5} so that
    backends like eval7 do not raise a "board must be 0, 3, 4, or 5 cards"
    error.
    """
    # First attempt: whatever the DecisionContext has.
    cards = _flatten_board_like(ctx.board)
    if len(cards) in (0, 3, 4, 5):
        return cards

    # Fallback: try the raw engine state.
    raw_state = getattr(ctx, "raw_state", None)
    board_attr = getattr(raw_state, "board", None)
    cards2 = _flatten_board_like(board_attr)
    if len(cards2) in (0, 3, 4, 5):
        return cards2

    # Last resort: treat as unknown board and use an empty board.
    return []


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


def _build_hu_advice(
    ctx: DecisionContext,
    meta: AdviceMeta,
    cfg: PostflopCoachConfig,
    equity_service: Optional[EquityService],
    street: StreetLiteral,
) -> AdviceV1:
    """
    Internal helper: HU (n_players == 2) equity-based advice.
    """
    hero_cards = list(ctx.hero_hole_cards or [])
    hero_hand = (hero_cards[0], hero_cards[1])

    villain_range = get_default_villain_range(street=street, role="oop")

    # Resolve board robustly for the equity engine.
    board_cards = _resolve_board_for_equity(ctx)

    svc = equity_service or EquityService()
    try:
        hero_equity = svc.hero_vs_range_equity(
            hero_hand=hero_hand,
            villain_range=villain_range,
            board=board_cards,
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


def _build_multiway_advice(
    ctx: DecisionContext,
    meta: AdviceMeta,
    cfg: PostflopCoachConfig,
    equity_service: Optional[EquityService],
    street: StreetLiteral,
) -> AdviceV1:
    """
    Internal helper: multiway (n_players > 2) equity-based advice.

    Uses a generic default villain range family for each active villain seat and
    a ranges-capable backend when available. If multiway equity is not
    available under the current backend policy, returns status="unsupported".
    """
    # Multiway gate.
    if not cfg.multiway_enabled:
        return AdviceV1(
            version=1,
            status="unsupported",
            meta=meta,
            recommendation=None,
            equity=None,
            thresholds=None,
            rationale="Postflop coach multiway path is disabled by configuration.",
        )

    active = list(ctx.active_seats or [])
    if ctx.n_players < 2 or not active:
        return AdviceV1(
            version=1,
            status="unsupported",
            meta=meta,
            recommendation=None,
            equity=None,
            thresholds=None,
            rationale="Postflop coach requires at least hero plus one villain.",
        )

    if ctx.hero_seat not in active:
        return AdviceV1(
            version=1,
            status="unsupported",
            meta=meta,
            recommendation=None,
            equity=None,
            thresholds=None,
            rationale="Postflop coach could not identify hero among active seats.",
        )

    hero_cards = list(ctx.hero_hole_cards or [])
    if len(hero_cards) != 2:
        return AdviceV1(
            version=1,
            status="unsupported",
            meta=meta,
            recommendation=None,
            equity=None,
            thresholds=None,
            rationale="Postflop coach requires a known hero hand for multiway.",
        )

    hero_hand = (hero_cards[0], hero_cards[1])

    svc = equity_service or EquityService()

    # Capability probing: tolerate stubs that don't implement `capabilities`.
    supports_ranges = False
    max_players = 2
    caps_func = getattr(svc, "capabilities", None)
    if callable(caps_func):
        try:
            caps = caps_func()
            supports_ranges = bool(caps.get("supports_ranges", False))
            max_players = int(caps.get("max_players", max_players) or max_players)
        except Exception:
            # Treat any failure as "no multiway support".
            supports_ranges = False
            max_players = 2

    if not supports_ranges or ctx.n_players > max_players:
        return AdviceV1(
            version=1,
            status="unsupported",
            meta=meta,
            recommendation=None,
            equity=None,
            thresholds=None,
            rationale=(
                "Postflop multiway equity is unavailable under the current "
                "equity backend policy."
            ),
        )

    # Build players: seat 0 -> hero hand, remaining active seats -> generic villain ranges.
    villain_range = get_default_villain_range(street=street, role="oop")

    from backend.services.equity.base import (
        PlayerSpec,
    )  # local import to avoid cycles in some tools

    players: List[PlayerSpec] = [PlayerSpec(hand=hero_hand)]
    villain_seats = [s for s in active if s != ctx.hero_seat]
    if not villain_seats:
        return AdviceV1(
            version=1,
            status="unsupported",
            meta=meta,
            recommendation=None,
            equity=None,
            thresholds=None,
            rationale="Postflop multiway coach could not identify villain seats.",
        )

    for _ in villain_seats:
        players.append(PlayerSpec(range=villain_range))

    # Resolve board robustly for the equity engine.
    board_cards = _resolve_board_for_equity(ctx)

    try:
        result = svc.calc_equity(
            players=players,
            board=board_cards,
            dead=(),
            iters=cfg.multiway_iters or cfg.iters,
            exact=False,
            timeout_ms=cfg.multiway_timeout_ms or cfg.timeout_ms,
        )
    except RuntimeError as e:
        # Treat backend limitations as "unsupported" rather than hard error.
        return AdviceV1(
            version=1,
            status="unsupported",
            meta=meta,
            recommendation=None,
            equity=None,
            thresholds=None,
            rationale=f"Postflop multiway equity unavailable: {e}",
        )
    except Exception as e:  # pragma: no cover - defensive
        return AdviceV1(
            version=1,
            status="error",
            meta=meta,
            recommendation=None,
            equity=None,
            thresholds=None,
            rationale=f"Postflop multiway equity evaluation failed: {e}",
        )

    per_player = list(result.per_player or [])
    if not per_player:
        return AdviceV1(
            version=1,
            status="error",
            meta=meta,
            recommendation=None,
            equity=None,
            thresholds=None,
            rationale="Postflop multiway equity result contained no players.",
        )

    # By construction hero is seat 0 in the equity call.
    hero_equity = float(per_player[0].get("equity", 0.0) or 0.0)

    # Build typed players_equity list.
    players_equity: List[AdviceEquityPlayer] = []
    for idx, p in enumerate(per_player):
        raw_seat = p.get("seat", idx)
        try:
            seat = int(raw_seat)
        except Exception:
            seat = idx
        eq_val = float(p.get("equity", 0.0) or 0.0)
        players_equity.append(AdviceEquityPlayer(seat=seat, equity=eq_val))

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

    # Normalise backend mode to the expected literal type.
    mode_raw = getattr(result, "mode", None)
    if isinstance(mode_raw, str) and mode_raw in ("hands", "ranges"):
        mode: Optional[EquityModeLiteral] = cast(EquityModeLiteral, mode_raw)
    else:
        mode = None

    equity = AdviceEquity(
        backend=getattr(result, "backend", None),
        mode=mode,
        hero=hero_equity,
        players=players_equity,
        vs_field=hero_equity,  # In standard equity definitions this is vs the field.
        exact=getattr(result, "exact", None),
        iters=getattr(result, "iters", None),
    )

    thresholds = AdviceThresholds(
        pot_odds=pot_odds,
        spr=None,
    )

    rationale_parts: List[str] = []
    rationale_parts.append(
        f"Hero equity ≈ {hero_equity:.3f} in a {ctx.n_players}-way pot "
        "versus default villain ranges."
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


def build_postflop_advice(
    ctx: DecisionContext,
    equity_service: Optional[EquityService] = None,
    config: Optional[PostflopCoachConfig] = None,
) -> AdviceV1:
    """
    Build an AdviceV1 object for a postflop decision.

    The caller is expected to pass a DecisionContext describing the spot.
    Unsupported contexts (non-postflop streets, unknown hero hand, terminal
    spots, disabled config) return AdviceV1 with status="disabled" or
    status="unsupported".

    Behaviour:
      * If config.enabled is false:
          - Returns status="disabled".
      * For flop/turn/river with a known hero hand and n_players >= 2:
          - n_players == 2 -> HU equity-based coach.
          - n_players  > 2 -> multiway equity-based coach (when available).
      * All other spots:
          - Returns status="unsupported".
    """
    cfg = config or PostflopCoachConfig()

    street = _normalize_street(ctx.street)

    meta = AdviceMeta(
        street=street,
        n_players=ctx.n_players,
        hero_seat=ctx.hero_seat,
        source="equity",
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
            rationale=(
                "Postflop coach v1 is disabled by configuration for this environment."
            ),
        )

    # Basic gating: postflop only, known hero hand, non-terminal.
    if street not in ("flop", "turn", "river") or ctx.terminal:
        return AdviceV1(
            version=1,
            status="unsupported",
            meta=meta,
            recommendation=None,
            equity=None,
            thresholds=None,
            rationale=(
                "Postflop coach v1 currently supports only non-terminal "
                "flop/turn/river spots."
            ),
        )

    if ctx.hero_hole_cards is None or len(ctx.hero_hole_cards) != 2:
        return AdviceV1(
            version=1,
            status="unsupported",
            meta=meta,
            recommendation=None,
            equity=None,
            thresholds=None,
            rationale="Postflop coach v1 requires a known hero hand.",
        )

    if ctx.n_players < 2:
        return AdviceV1(
            version=1,
            status="unsupported",
            meta=meta,
            recommendation=None,
            equity=None,
            thresholds=None,
            rationale="Postflop coach v1 requires at least two active players.",
        )

    # HU: preserve existing behaviour (used heavily in tests).
    if ctx.n_players == 2:
        return _build_hu_advice(
            ctx=ctx,
            meta=meta,
            cfg=cfg,
            equity_service=equity_service,
            street=street,
        )

    # Multiway path (n_players > 2).
    return _build_multiway_advice(
        ctx=ctx,
        meta=meta,
        cfg=cfg,
        equity_service=equity_service,
        street=street,
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
