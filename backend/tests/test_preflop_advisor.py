## backend/tests/test_preflop_advisor.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.coach.preflop.charts import load_charts_from_paths
from backend.coach.preflop.models import PreflopContext
from backend.coach.preflop.service import PreflopAdvisorService


def _write_example_chart(tmp_path: Path) -> Path:
    """
    Create a tiny HU chart fixture on disk and return its path.

    This mirrors the devdata/charts/hu_example.json format we plan to add,
    but keeps the tests self-contained.
    """
    data = {
        "meta": {
            "format_version": 1,
            "name": "HU 25bb SRP vSB",
            "game_type": "NLH",
            "stack_bb": 25,
            "rake": "0",
            "positions": ["SB", "BB"],
        },
        "rows": [
            {
                "hand": "AJo",
                "node": "sb_open",
                "bucket": "2.5x",
                "strategy_bar": {"fold": 0.0, "call": 0.2, "2.5x": 0.8},
            }
        ],
    }
    path = tmp_path / "hu_example.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_charts_from_paths(tmp_path: Path) -> None:
    chart_path = _write_example_chart(tmp_path)

    charts = load_charts_from_paths([str(chart_path)])

    assert len(charts) == 1
    chart = charts[0]

    assert chart.meta.name == "HU 25bb SRP vSB"
    assert chart.meta.game_type == "NLH"
    assert chart.meta.stack_bb == 25
    assert chart.meta.positions == ["SB", "BB"]

    assert len(chart.rows) == 1
    row = chart.rows[0]
    assert row.hand_key == "AJo"
    assert row.node == "sb_open"
    assert row.bucket == "2.5x"
    assert (
        pytest.approx(sum(row.strategy_bar.values()), rel=1e-6) == 1.0
    )  # 0.0 + 0.2 + 0.8


def test_get_advice_chart_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    PreflopAdvisorService returns chart-based advice for a known spot.

    We monkeypatch `_build_context` so we don't depend on real engine state:
    it simply maps (hand_id, idx) -> (node="sb_open", hand_key="AJo").
    """
    chart_path = _write_example_chart(tmp_path)

    # Monkeypatch context builder to use our known node/hand_key.
    def fake_build_context(
        self: PreflopAdvisorService,
        hand_id: str,
        idx: int,
    ) -> PreflopContext:
        return PreflopContext(
            hand_key="AJo",
            node="sb_open",
            stack_bb=25,
            hero_position="SB",
            villain_position="BB",
        )

    monkeypatch.setattr(
        PreflopAdvisorService, "_build_context", fake_build_context, raising=False
    )

    svc = PreflopAdvisorService(chart_paths=[str(chart_path)])

    assert svc.has_charts is True

    advice = svc.get_advice(hand_id="H1", idx=0)

    assert advice.source == "chart"
    assert advice.bucket == "2.5x"
    assert "fold" in advice.strategy_bar
    assert "call" in advice.strategy_bar
    assert "2.5x" in advice.strategy_bar
    # Strategy bar should roughly sum to 1.0
    assert pytest.approx(sum(advice.strategy_bar.values()), rel=1e-6) == 1.0
    # Rationale should mention chart and hand_id/idx.
    assert "chart:" in advice.rationale
    assert "hand_id=H1" in advice.rationale
    assert "idx=0" in advice.rationale


def test_get_advice_no_charts_configured_raises() -> None:
    """
    When no charts are configured, get_advice should fail with a clear error.
    """
    svc = PreflopAdvisorService(chart_paths=[])

    assert svc.has_charts is False

    with pytest.raises(RuntimeError) as excinfo:
        svc.get_advice(hand_id="H1", idx=0)

    msg = str(excinfo.value)
    assert "preflop coach charts not configured" in msg


# ---------------------------------------------------------------------------
# Equity fallback tests (chart miss → equity-based decision)
# ---------------------------------------------------------------------------


class _StubEquityService:
    """
    Tiny stub for EquityService used to test fallback behaviour.

    It exposes hero_vs_range_equity and always returns a fixed equity value.
    """

    def __init__(self, eq: float) -> None:
        self._eq = eq
        self.calls = 0

    def hero_vs_range_equity(self, *args, **kwargs) -> float:  # type: ignore[override]
        self.calls += 1
        return self._eq


def _make_fallback_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    eq: float,
) -> tuple[PreflopAdvisorService, _StubEquityService]:
    """
    Helper to build a PreflopAdvisorService wired for equity fallback:

    - Loads a tiny chart (content doesn't matter since we force a chart miss).
    - Monkeypatches _build_context to describe a bb_vs_sb_open defend spot.
    - Monkeypatches _select_row to simulate "no chart row" (forces fallback).
    - Injects a stub EquityService that returns `eq`.
    """
    chart_path = _write_example_chart(tmp_path)

    # Context: BB defending vs SB open with a specific hand_key.
    def fake_build_context(
        self: PreflopAdvisorService,
        hand_id: str,
        idx: int,
    ) -> PreflopContext:
        return PreflopContext(
            hand_key="AJo",
            node="bb_vs_sb_open",
            stack_bb=25,
            hero_position="BB",
            villain_position="SB",
        )

    # Force chart miss so the service is compelled to use fallback.
    def fake_select_row(self: PreflopAdvisorService, ctx: PreflopContext, chart):
        raise LookupError("no chart row for fallback test")

    monkeypatch.setattr(
        PreflopAdvisorService, "_build_context", fake_build_context, raising=False
    )
    monkeypatch.setattr(
        PreflopAdvisorService, "_select_row", fake_select_row, raising=False
    )

    # Threshold: 0.5 so we can test above/below behaviour.
    monkeypatch.setenv("PREFLOP_EQ_DEFEND_THRESH", "0.5")

    stub_equity = _StubEquityService(eq=eq)
    svc = PreflopAdvisorService(
        chart_paths=[str(chart_path)],
        equity_service=stub_equity,
    )
    return svc, stub_equity


def test_equity_fallback_call_above_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    When equity is above PREFLOP_EQ_DEFEND_THRESH, fallback should recommend a defend.

    Expected:
      - source == "equity"
      - bucket == "call" (for bb_vs_sb_open)
    """
    svc, stub = _make_fallback_service(tmp_path, monkeypatch, eq=0.60)

    advice = svc.get_advice(hand_id="H1", idx=0)

    assert advice.source == "equity"
    assert advice.bucket == "call"
    assert stub.calls >= 1


def test_equity_fallback_fold_below_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    When equity is below PREFLOP_EQ_DEFEND_THRESH, fallback should recommend a fold.

    Expected:
      - source == "equity"
      - bucket == "fold"
    """
    svc, stub = _make_fallback_service(tmp_path, monkeypatch, eq=0.30)

    advice = svc.get_advice(hand_id="H1", idx=0)

    assert advice.source == "equity"
    assert advice.bucket == "fold"
    assert stub.calls >= 1
