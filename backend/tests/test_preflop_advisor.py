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
