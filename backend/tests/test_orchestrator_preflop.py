# backend/tests/test_orchestrator_preflop.py
from __future__ import annotations

from typing import Any, Dict

import pytest

from backend.coach.decision_context import DecisionContext
from backend.coach import orchestrator
from backend.coach.policies import preflop_hu_chart_policy


# Resolve the main orchestrator entrypoint in a tolerant way
if hasattr(orchestrator, "get_advice_for_context"):
    get_advice = orchestrator.get_advice_for_context  # type: ignore[attr-defined]
elif hasattr(orchestrator, "get_advice"):
    get_advice = orchestrator.get_advice  # type: ignore[attr-defined]
elif hasattr(orchestrator, "get_coach_advice"):
    get_advice = orchestrator.get_coach_advice  # type: ignore[attr-defined]
else:
    # Last-resort generic name; this will fail loudly if nothing matches.
    get_advice = orchestrator.orchestrate  # type: ignore[attr-defined]


def _make_ctx(**overrides: object) -> DecisionContext:
    """
    Build a minimal HU preflop DecisionContext.

    Defaults model: hero BTN/SB (seat 0) vs BB (seat 1),
    preflop, AsKd (→ AKo canonical).
    """
    base: Dict[str, Any] = dict(
        hand_id="H1",
        idx=0,
        street="preflop",
        hero_seat=0,
        n_players=2,
        active_seats=[0, 1],
        board=[],
        pot_total=3,
        to_call=0,
        min_raise=5,
        allowed_buckets=["fold", "2.5x"],
        deck_seed=None,
        hero_hole_cards=["As", "Kd"],
        button=0,
        sb_seat=0,
        bb_seat=1,
        terminal=False,
        last_action=None,
        raw_state={},
        seat_stacks={0: 100, 1: 100},
        seat_committed={0: 0, 1: 1},
        hero_stack=100,
        hero_committed=0,
    )
    base.update(overrides)
    return DecisionContext(**base)  # type: ignore[arg-type]


class SentinelAdvice:
    """Simple marker object so we can verify the orchestrator returns this exact instance."""

    def __init__(self, label: str) -> None:
        self.label = label
        # Optional: provide some fields that advice objects might have
        self.primary_action = "2.5x"
        self.action_mix = {"2.5x": 0.7, "fold": 0.3}
        self.source = "preflop_chart"


def test_hu_preflop_delegates_to_preflop_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    HU preflop decisions should be delegated to the HU preflop chart policy.

    We stub preflop_hu_chart_policy.get_hu_preflop_advice and assert:
      * it is called exactly once
      * the same advice object is returned by the orchestrator
    """
    calls: Dict[str, Any] = {}

    def fake_get_hu_preflop_advice(ctx: DecisionContext, profile: str) -> Any:
        calls["ctx"] = ctx
        calls["profile"] = profile
        return SentinelAdvice("from_preflop_policy")

    monkeypatch.setattr(
        preflop_hu_chart_policy,
        "get_hu_preflop_advice",
        fake_get_hu_preflop_advice,
        raising=True,
    )

    # Also defensively stub any postflop / solver entrypoints so they would blow up if used
    # (we don't care what these are called yet; this is just a guard rail).
    if hasattr(orchestrator, "get_postflop_advice"):
        monkeypatch.setattr(
            orchestrator,
            "get_postflop_advice",
            lambda *a, **k: (_ for _ in ()).throw(
                AssertionError("postflop advice should not be called for preflop")
            ),
            raising=False,
        )

    ctx = _make_ctx()
    advice = get_advice(ctx)

    # Orchestrator should return something (not None) and it should be our sentinel.
    assert isinstance(advice, SentinelAdvice)
    assert advice.label == "from_preflop_policy"

    # Policy should have been called with the same context
    assert calls.get("ctx") is ctx
    # Profile name is determined by coach config; at minimum it should be a non-empty string.
    assert isinstance(calls.get("profile"), str)
    assert calls["profile"] != ""


def test_non_preflop_does_not_call_preflop_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    For non-preflop streets the HU preflop chart policy must NOT be used.
    We don't assert what happens instead (that’s covered by postflop tests),
    only that preflop policy is not touched.
    """

    def fake_get_hu_preflop_advice(ctx: DecisionContext, profile: str) -> Any:
        raise AssertionError(
            "HU preflop policy must not be called on non-preflop streets"
        )

    monkeypatch.setattr(
        preflop_hu_chart_policy,
        "get_hu_preflop_advice",
        fake_get_hu_preflop_advice,
        raising=True,
    )

    ctx = _make_ctx(street="flop")

    # Orchestrator may return None here or some other kind of advice,
    # depending on whether postflop coach is wired up; we only care that
    # it doesn't explode from our assertion in the monkeypatch.
    try:
        _ = get_advice(ctx)
    except AssertionError as e:
        pytest.fail(f"Preflop policy was incorrectly called on non-preflop street: {e}")


def test_multiway_preflop_does_not_use_hu_preflop_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    If the pot is not heads-up (n_players != 2), the HU preflop chart policy
    should not be invoked.
    """

    def fake_get_hu_preflop_advice(ctx: DecisionContext, profile: str) -> Any:
        raise AssertionError("HU preflop policy must not be called for multiway spots")

    monkeypatch.setattr(
        preflop_hu_chart_policy,
        "get_hu_preflop_advice",
        fake_get_hu_preflop_advice,
        raising=True,
    )

    ctx = _make_ctx(n_players=3, active_seats=[0, 1, 2])

    try:
        _ = get_advice(ctx)
    except AssertionError as e:
        pytest.fail(f"Preflop policy was incorrectly called for multiway: {e}")
