# backend/tests/test_postflop_coach_multiway.py
from __future__ import annotations

from typing import Any, Dict, List

from backend.coach.decision_context import DecisionContext
from backend.coach.postflop.service import build_postflop_advice


class StubEquityService:
    """
    Test double for EquityService.

    For current multiway behaviour this stub should never actually be called,
    because the postflop coach v1 only supports HU and returns
    status="unsupported" for n_players != 2.
    """

    def __init__(self, hero_equity: float) -> None:
        self.hero_equity = hero_equity
        self.calls: List[Dict[str, Any]] = []

    def hero_vs_range_equity(self, **kwargs: Any) -> float:  # type: ignore[override]
        # Record calls in case future multiway logic starts using this helper.
        self.calls.append(kwargs)
        return self.hero_equity


def make_ctx(**overrides: Any) -> DecisionContext:
    """
    Minimal helper for constructing a multiway DecisionContext for tests.

    The base context is HU; individual tests override n_players / active_seats
    (and any other fields) as needed.
    """
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


def test_multiway_currently_unsupported() -> None:
    """
    For n_players > 2, the current postflop coach v1 should *gracefully*
    report status='unsupported' and not attempt any equity work.

    This is the expected behaviour until a true multiway coach is implemented.
    """
    ctx = make_ctx(
        n_players=3,
        active_seats=[0, 1, 2],
    )
    svc = StubEquityService(hero_equity=0.50)

    advice = build_postflop_advice(ctx, equity_service=svc)

    assert advice.status == "unsupported"
    assert advice.recommendation is None
    assert advice.equity is None
    assert advice.thresholds is None
