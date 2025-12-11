# backend/tests/test_postflop_coach_hu.py
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from backend.coach.decision_context import DecisionContext
from backend.coach.postflop.service import build_postflop_advice


# Make sure these tests never hit TexasSolver; they are testing equity logic.
@pytest.fixture(autouse=True)
def disable_texas_solver_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Force the postflop coach to skip the TexasSolver path in this module.

    We want to exercise the equity-based fallback only, regardless of whether
    the solver binary / adapter is installed locally.
    """
    monkeypatch.setenv("TEXASSOLVER_ENABLED", "0")


class StubEquityService:
    """Test double for EquityService.hero_vs_range_equity."""

    def __init__(self, hero_equity: float) -> None:
        self.hero_equity = hero_equity
        self.calls: List[Dict[str, Any]] = []

    def hero_vs_range_equity(self, **kwargs: Any) -> float:  # type: ignore[override]
        self.calls.append(kwargs)
        return self.hero_equity


def make_ctx(**overrides: Any) -> DecisionContext:
    """Construct a minimal HU flop DecisionContext for tests."""
    base: Dict[str, Any] = {
        "hand_id": "H1",
        "idx": 0,
        "street": "flop",
        "hero_seat": 0,
        "n_players": 2,
        "active_seats": [0, 1],
        "board": ["Ah", "Kd", "3s"],
        "pot_total": 100,
        "to_call": 50,
        "min_raise": 200,
        "allowed_buckets": ["fold", "call"],
        "deck_seed": None,
        "hero_hole_cards": ["As", "Kh"],
        "button": 0,
        "sb_seat": 0,
        "bb_seat": 1,
        "terminal": False,
        "last_action": None,
        "raw_state": {},
    }
    base.update(overrides)
    return DecisionContext(**base)


def test_fold_when_equity_well_below_pot_odds() -> None:
    # pot_total=100, to_call=50 -> pot_odds ≈ 0.333
    ctx = make_ctx(to_call=50, allowed_buckets=["fold", "call"])
    svc = StubEquityService(hero_equity=0.10)  # clearly below price

    advice = build_postflop_advice(ctx, equity_service=svc)

    assert advice.status == "ok"
    assert advice.recommendation is not None
    assert advice.recommendation.bucket == "fold"
    assert advice.equity is not None
    assert advice.equity.hero == pytest.approx(0.10, rel=1e-6)
    assert advice.thresholds is not None
    assert advice.thresholds.pot_odds is not None
    assert advice.thresholds.pot_odds > 0.0


def test_call_near_threshold() -> None:
    # Equity slightly above pot odds but not by a huge margin -> call.
    ctx = make_ctx(to_call=50, allowed_buckets=["fold", "call"])
    svc = StubEquityService(hero_equity=0.36)

    advice = build_postflop_advice(ctx, equity_service=svc)

    assert advice.status == "ok"
    assert advice.recommendation is not None
    assert advice.recommendation.bucket == "call"


def test_raise_when_strong_and_raises_allowed() -> None:
    ctx = make_ctx(
        to_call=50,
        allowed_buckets=["fold", "call", "2.5xR"],
    )
    svc = StubEquityService(hero_equity=0.70)

    advice = build_postflop_advice(ctx, equity_service=svc)

    assert advice.status == "ok"
    assert advice.recommendation is not None
    assert advice.recommendation.bucket == "2.5xR"


def test_check_vs_bet_when_to_call_zero() -> None:
    # When to_call == 0, strong hands should prefer a bet bucket over check.
    ctx_strong = make_ctx(
        to_call=0,
        allowed_buckets=["check", "50%"],
    )
    svc_strong = StubEquityService(hero_equity=0.70)

    advice_strong = build_postflop_advice(ctx_strong, equity_service=svc_strong)
    assert advice_strong.status == "ok"
    assert advice_strong.recommendation is not None
    assert advice_strong.recommendation.bucket == "50%"

    ctx_weak = make_ctx(
        to_call=0,
        allowed_buckets=["check", "50%"],
    )
    svc_weak = StubEquityService(hero_equity=0.40)

    advice_weak = build_postflop_advice(ctx_weak, equity_service=svc_weak)
    assert advice_weak.status == "ok"
    assert advice_weak.recommendation is not None
    assert advice_weak.recommendation.bucket == "check"


def test_unsupported_when_not_hu() -> None:
    ctx = make_ctx(
        n_players=3,
        active_seats=[0, 1, 2],
    )
    svc = StubEquityService(hero_equity=0.50)

    advice = build_postflop_advice(ctx, equity_service=svc)

    assert advice.status == "unsupported"
    assert advice.recommendation is None
