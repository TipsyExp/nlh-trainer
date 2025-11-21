# backend/tests/test_coach_api.py
"""
Tests for the /api/coach/advice endpoint (AdviceV1 contract).

These tests focus on:

    * COACH_ENABLED gating.
    * Preflop path wiring (wraps preflop advisor into AdviceV1).
    * Postflop HU wiring (delegates to postflop coach v1).

The exact internals of preflop/postflop coaches are tested elsewhere; here
we mostly verify that /api/coach/advice returns a well-formed AdviceV1 and
routes to the correct helper based on the decision context.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from backend.coach.decision_context import DecisionContext
from backend.schemas.advice import (
    AdviceMeta,
    AdviceRecommendation,
    AdviceV1,
    StrategyPart,
)
from backend.main import app


def _make_ctx(**overrides: Any) -> DecisionContext:
    """Minimal helper for constructing a DecisionContext in tests."""
    base: Dict[str, Any] = {
        "hand_id": "H1",
        "idx": 0,
        "street": "preflop",
        "hero_seat": 0,
        "n_players": 2,
        "active_seats": [0, 1],
        "board": [],
        "pot_total": 150,
        "to_call": 50,
        "min_raise": 150,
        "allowed_buckets": ["fold", "call", "2.5x"],
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


def test_advice_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """When COACH_ENABLED=false, /coach/advice returns 501 + status='disabled'."""
    monkeypatch.setenv("COACH_ENABLED", "false")
    client = TestClient(app)

    r = client.get("/api/coach/advice", params={"hand_id": "H1", "idx": 0})
    assert r.status_code == 501

    body = r.json()
    assert body.get("status") == "disabled"
    assert "meta" in body


def test_preflop_unsupported_when_service_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    If preflop advisor is unavailable (no charts, etc.), the endpoint should
    still return AdviceV1 with status='unsupported' rather than erroring.
    """
    monkeypatch.setenv("COACH_ENABLED", "true")

    # Stub the decision-context builder to return a preflop context.
    pre_ctx = _make_ctx(street="preflop")

    def fake_build_decision_context(
        hand_id: str, idx: int
    ) -> DecisionContext:  # noqa: ANN001
        return pre_ctx

    monkeypatch.setattr(
        "backend.coach.decision_context.build_decision_context",
        fake_build_decision_context,
        raising=True,
    )

    # Force _get_preflop_service() to return None.
    monkeypatch.setattr(
        "backend.api.coach._get_preflop_service",
        lambda: None,
        raising=True,
    )

    client = TestClient(app)
    r = client.get("/api/coach/advice", params={"hand_id": "H1", "idx": 0})
    assert r.status_code == 200

    body = r.json()
    assert body["status"] == "unsupported"
    assert body["meta"]["street"] == "preflop"
    assert body["meta"]["n_players"] == 2
    assert body["meta"]["hero_seat"] == 0


def test_postflop_delegates_to_postflop_coach(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    For HU flop/turn/river, /coach/advice should delegate to the postflop
    coach and surface its AdviceV1 payload unchanged (except for JSON
    serialization).
    """
    monkeypatch.setenv("COACH_ENABLED", "true")

    flop_ctx = _make_ctx(
        street="flop",
        board=["Ah", "Kd", "3s"],
        pot_total=100,
        to_call=50,
    )

    def fake_build_decision_context(
        hand_id: str, idx: int
    ) -> DecisionContext:  # noqa: ANN001
        assert hand_id == "H1"
        assert idx == 0
        return flop_ctx

    monkeypatch.setattr(
        "backend.coach.decision_context.build_decision_context",
        fake_build_decision_context,
        raising=True,
    )

    # Prepare a stub AdviceV1 that the postflop coach will "return".
    stub_advice = AdviceV1(
        status="ok",
        meta=AdviceMeta(
            street="flop",
            n_players=2,
            hero_seat=0,
            source="equity",
        ),
        recommendation=AdviceRecommendation(
            bucket="call",
            strategy_bar=[StrategyPart(action="call", weight=1.0)],
        ),
        equity=None,
        thresholds=None,
        rationale="stub postflop advice",
    )

    def fake_get_postflop_advice(ctx: DecisionContext) -> AdviceV1:  # noqa: ANN001
        # Ensure we actually received the flop context.
        assert ctx.street == "flop"
        return stub_advice

    monkeypatch.setattr(
        "backend.coach.postflop.service.get_postflop_advice",
        fake_get_postflop_advice,
        raising=True,
    )

    client = TestClient(app)
    r = client.get("/api/coach/advice", params={"hand_id": "H1", "idx": 0})
    assert r.status_code == 200

    body = r.json()
    assert body["status"] == "ok"
    assert body["meta"]["street"] == "flop"
    assert body["recommendation"]["bucket"] == "call"
    assert body["rationale"] == "stub postflop advice"
