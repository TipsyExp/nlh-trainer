# backend/tests/test_preflop_hu_chart_policy.py
from __future__ import annotations

from typing import Dict, Optional, Any

import pytest

from backend.coach.decision_context import DecisionContext
from backend.coach.policies import preflop_hu_chart_policy as policy


# Resolve the main entrypoint once, but be tolerant of slight naming differences.
if hasattr(policy, "get_hu_preflop_advice"):
    get_hu_preflop_advice = policy.get_hu_preflop_advice  # type: ignore[attr-defined]
else:
    # Fallback if we happened to name it a bit differently
    get_hu_preflop_advice = policy.get_hu_preflop_recommendation  # type: ignore[attr-defined]


class DummyChart:
    """
    Very loose fake chart object.

    It’s intentionally tolerant of different chart APIs:
      * If the policy calls .lookup(node, hand_key) and expects a row object
        with .strategy_bar, we return one.
      * If it calls .lookup_mix(...) / .get_mix(...) etc., we return a dict.
    """

    def __init__(self) -> None:
        self.last_node: Optional[str] = None
        self.last_hand_key: Optional[str] = None
        self.last_method: Optional[str] = None

    def _record(self, node: str, hand_key: str, method: str) -> None:
        self.last_node = node
        self.last_hand_key = hand_key
        self.last_method = method

    def _row(self, node: str, hand_key: str) -> Any:
        self._record(node, hand_key, "row")

        class Row:
            def __init__(self) -> None:
                self.node = node
                self.hand_key = hand_key
                self.bucket = "2.5x"
                self.strategy_bar: Dict[str, float] = {"2.5x": 0.7, "fold": 0.3}

        return Row()

    # Common possible APIs on the real chart
    def lookup(self, node: str, hand_key: str, *args: Any, **kwargs: Any) -> Any:
        return self._row(node, hand_key)

    def lookup_mix(
        self, node: str, hand_key: str, *args: Any, **kwargs: Any
    ) -> Dict[str, float]:
        self._record(node, hand_key, "lookup_mix")
        return {"2.5x": 0.7, "fold": 0.3}

    # Safety net: if the policy uses some slightly different method name,
    # route anything with "mix" in the name to lookup_mix, otherwise to _row.
    def __getattr__(self, name: str):
        if "mix" in name:

            def f(
                node: str, hand_key: str, *args: Any, **kwargs: Any
            ) -> Dict[str, float]:
                return self.lookup_mix(node, hand_key, *args, **kwargs)

            return f

        def f(node: str, hand_key: str, *args: Any, **kwargs: Any) -> Any:
            return self._row(node, hand_key)

        return f


def _make_ctx(**overrides: object) -> DecisionContext:
    """
    Build a minimal but valid HU preflop DecisionContext.

    Defaults:
      - Hero is BTN/SB at seat 0.
      - Villain is BB at seat 1.
      - Street is preflop, HU (2 players).
      - Hero hole cards: AsKd (→ canonical "AKo").
    """
    base = dict(
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


def test_btn_open_uses_chart_and_canonicalizes_hand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    For a simple HU BTN open spot, the policy should:

      * detect HU + preflop,
      * canonicalize AsKd → "AKo",
      * call load_hu_chart(profile),
      * query the chart for that hand key,
      * and surface the bucket mix the chart gives it.
    """
    dummy_holder: Dict[str, DummyChart] = {}

    def fake_load_hu_chart(profile: str) -> DummyChart:
        assert isinstance(profile, str)
        chart = DummyChart()
        dummy_holder["chart"] = chart
        return chart

    # Policy module is responsible for importing / defining load_hu_chart
    monkeypatch.setattr(
        policy,
        "load_hu_chart",
        fake_load_hu_chart,
        raising=True,
    )

    ctx = _make_ctx()  # default preflop BTN open, AsKd

    advice = get_hu_preflop_advice(ctx, profile="default_100bb_2.5x")
    assert advice is not None

    chart = dummy_holder["chart"]
    # We don't care about the exact node string here, only the hand key.
    assert chart.last_hand_key == "AKo"

    # Try to extract a bucket/action mix in a tolerant way
    mix = getattr(advice, "bucket_mix", None)
    if mix is None:
        mix = getattr(advice, "action_mix", None)
    assert isinstance(mix, dict)

    # It should reflect the dummy chart's mix
    assert pytest.approx(mix.get("2.5x", 0.0)) == 0.7
    assert pytest.approx(mix.get("fold", 0.0)) == 0.3


def test_returns_none_if_not_preflop(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Non-preflop streets should be ignored by the HU preflop chart policy.
    """

    def fake_load_hu_chart(profile: str) -> DummyChart:
        raise AssertionError(
            "load_hu_chart should not be called on non-preflop streets"
        )

    monkeypatch.setattr(
        policy,
        "load_hu_chart",
        fake_load_hu_chart,
        raising=True,
    )

    ctx = _make_ctx(street="flop")
    advice = get_hu_preflop_advice(ctx, profile="default_100bb_2.5x")
    assert advice is None


def test_returns_none_if_not_hu(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Multiway pots (n_players != 2) should be ignored by the HU preflop chart policy.
    """

    def fake_load_hu_chart(profile: str) -> DummyChart:
        raise AssertionError("load_hu_chart should not be called for multiway spots")

    monkeypatch.setattr(
        policy,
        "load_hu_chart",
        fake_load_hu_chart,
        raising=True,
    )

    ctx = _make_ctx(n_players=3, active_seats=[0, 1, 2])
    advice = get_hu_preflop_advice(ctx, profile="default_100bb_2.5x")
    assert advice is None


def test_returns_none_if_hero_has_no_hole_cards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    If hero_hole_cards are missing, the policy can't look up a hand key and
    should return None without calling the chart loader.
    """

    def fake_load_hu_chart(profile: str) -> DummyChart:
        raise AssertionError("load_hu_chart should not be called without hole cards")

    monkeypatch.setattr(
        policy,
        "load_hu_chart",
        fake_load_hu_chart,
        raising=True,
    )

    ctx = _make_ctx(hero_hole_cards=None)
    advice = get_hu_preflop_advice(ctx, profile="default_100bb_2.5x")
    assert advice is None
