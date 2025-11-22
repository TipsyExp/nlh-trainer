# backend/tests/test_coach_api.py
"""
Tests for the /api/coach/advice endpoint (AdviceV1 contract).

These tests focus on:

    * COACH_ENABLED gating.
    * Preflop path wiring (wraps preflop advisor into AdviceV1).
    * Postflop HU wiring (delegates to postflop coach v1).
    * Basic logging hook for unified coach advice snapshots.

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


def test_postflop_delegates_to_postflop_coach(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        version=1,
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


def test_preflop_logs_unified_advice_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Successful preflop advice should be logged via log_coach_advice with the
    same AdviceV1 payload that is returned to the client.
    """
    monkeypatch.setenv("COACH_ENABLED", "true")

    # Preflop decision context.
    pre_ctx = _make_ctx(street="preflop")

    def fake_build_decision_context(
        hand_id: str, idx: int
    ) -> DecisionContext:  # noqa: ANN001
        assert hand_id == "H1"
        assert idx == 0
        return pre_ctx

    monkeypatch.setattr(
        "backend.coach.decision_context.build_decision_context",
        fake_build_decision_context,
        raising=True,
    )

    # Stub preflop service + advice.
    class StubPreflopAdvice:
        def __init__(self) -> None:
            self.source = "chart"
            self.bucket = "2.5x"
            self.rationale = "stub preflop advice"
            self.strategy_bar = {"2.5x": 1.0}

    class StubPreflopService:
        has_charts = True

        def get_advice(
            self, hand_id: str, idx: int
        ) -> StubPreflopAdvice:  # noqa: ANN001
            assert hand_id == "H1"
            assert idx == 0
            return StubPreflopAdvice()

    monkeypatch.setattr(
        "backend.api.coach._get_preflop_service",
        lambda: StubPreflopService(),
        raising=True,
    )

    # Capture log_coach_advice calls.
    captured: Dict[str, Any] = {}

    def fake_log_coach_advice(
        hand_id: str, idx: int, advice: Dict[str, Any]
    ) -> None:  # noqa: ANN001
        captured["hand_id"] = hand_id
        captured["idx"] = idx
        captured["advice"] = advice

    monkeypatch.setattr(
        "backend.api.coach.log_coach_advice",
        fake_log_coach_advice,
        raising=True,
    )

    client = TestClient(app)
    r = client.get("/api/coach/advice", params={"hand_id": "H1", "idx": 0})
    assert r.status_code == 200

    body = r.json()
    # Sanity-check AdviceV1 shape.
    assert body["status"] == "ok"
    assert body["meta"]["street"] == "preflop"
    assert body["meta"]["hero_seat"] == 0
    assert body["recommendation"]["bucket"] == "2.5x"
    assert body["rationale"] == "stub preflop advice"

    # Logging side effects: we logged the same payload we returned.
    assert captured["hand_id"] == "H1"
    assert captured["idx"] == 0
    assert isinstance(captured["advice"], dict)
    # Logged advice should match the JSON payload (unified snapshot).
    assert captured["advice"] == body
