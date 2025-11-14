## backend/tests/test_coach_preflop_api.py
from __future__ import annotations

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from backend.main import app


def _client() -> TestClient:
    return TestClient(app)


def test_preflop_chart_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Happy-path: coach enabled + charts configured → chart-based advice.

    Uses the dev HU chart fixture, which contains an AJo/sb_open row.
    For the current MVP wiring, the advisor will simply pick the first
    available row, so we only assert on shape + source/bucket.
    """
    monkeypatch.setenv("COACH_ENABLED", "true")
    monkeypatch.setenv("PREFLOP_CHART_PATHS", "devdata/charts/hu_example.json")

    client = _client()
    r = client.get("/api/coach/preflop", params={"hand_id": "H1", "idx": 0})
    assert r.status_code == 200

    body: Dict[str, Any] = r.json()
    assert isinstance(body, dict)

    # Basic contract: chart advice payload
    assert body.get("source") == "chart"
    assert isinstance(body.get("bucket"), str)
    assert isinstance(body.get("rationale"), str)
    strategy_bar = body.get("strategy_bar") or {}
    assert isinstance(strategy_bar, dict)
    assert strategy_bar  # non-empty

    # Soft sanity: probabilities roughly sum to 1.0 when present
    total = sum(float(v) for v in strategy_bar.values())
    assert 0.9 <= total <= 1.1


def test_preflop_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    With COACH_ENABLED=false, /api/coach/preflop should be gated with 501.

    The response shape mirrors other coach endpoints: we prefer
    meta.status == "disabled", but remain tolerant of detail-only errors.
    """
    monkeypatch.setenv("COACH_ENABLED", "false")
    # Ensure charts don't matter in this mode
    monkeypatch.delenv("PREFLOP_CHART_PATHS", raising=False)

    client = _client()
    r = client.get("/api/coach/preflop", params={"hand_id": "H1", "idx": 0})
    assert r.status_code == 501

    body: Dict[str, Any] = r.json()
    assert isinstance(body, dict)

    meta = body.get("meta")
    if isinstance(meta, dict):
        assert meta.get("status") == "disabled"
    else:
        # Backwards-compatible tolerance if implementation uses detail instead
        detail = str(body.get("detail", "")).lower()
        assert "disabled" in detail


def test_preflop_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    With coach enabled but no charts configured, the preflop endpoint
    should return 501 to signal "charts not configured".
    """
    monkeypatch.setenv("COACH_ENABLED", "true")
    # Explicitly clear chart paths to simulate misconfiguration
    monkeypatch.delenv("PREFLOP_CHART_PATHS", raising=False)

    client = _client()
    r = client.get("/api/coach/preflop", params={"hand_id": "H1", "idx": 0})
    assert r.status_code == 501

    body: Dict[str, Any] = r.json()
    assert isinstance(body, dict)

    meta = body.get("meta")
    if isinstance(meta, dict):
        # Prefer a clear machine-readable status if present
        assert meta.get("status") in {"not_configured", "disabled"}
    else:
        detail = str(body.get("detail", "")).lower()
        assert "not configured" in detail or "charts" in detail


# ---------------------------------------------------------------------------
# Equity-fallback API tests (to be enabled once wired)
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason="Enable after wiring equity-based fallback into PreflopAdvisorService."
)
def test_preflop_equity_fallback_above_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Placeholder: when chart has no row but equity fallback is available and
    hero equity >= PREFLOP_EQ_DEFEND_THRESH, /api/coach/preflop should return
    source='equity' and a defend-type bucket (e.g. call).
    """
    ...


@pytest.mark.skip(
    reason="Enable after wiring equity-based fallback into PreflopAdvisorService."
)
def test_preflop_equity_fallback_below_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Placeholder: when chart has no row and hero equity < PREFLOP_EQ_DEFEND_THRESH,
    /api/coach/preflop should return source='equity' and a fold-type bucket.
    """
    ...
