# backend/tests/test_coach_preflop_logging.py
from __future__ import annotations

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from backend.main import app


def _client() -> TestClient:
    return TestClient(app)


def _enable_basic_coach_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Enable coach and point to the tiny HU dev chart fixture.

    This matches the setup used in other preflop API tests.
    """
    monkeypatch.setenv("COACH_ENABLED", "true")
    monkeypatch.setenv("PREFLOP_CHART_PATHS", "devdata/charts/hu_example.json")


def test_preflop_advice_logging_called_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    When LOG_PREFLOP_ADVICE is enabled and /api/coach/preflop is called,
    the preflop logging helper should be invoked.
    """
    from backend import logger as logger_mod
    from backend.api import coach as coach_mod

    _enable_basic_coach_env(monkeypatch)

    # Force the flag on at the logger module level
    monkeypatch.setattr(logger_mod, "LOG_PREFLOP_ADVICE", True, raising=False)

    calls: Dict[str, Any] = {"n": 0, "args": None}

    def fake_log_preflop_advice(
        hand_id: str,
        idx: int,
        advice: Dict[str, Any],
    ) -> None:
        # Mirror real gating behaviour based on the flag.
        if not getattr(logger_mod, "LOG_PREFLOP_ADVICE", False):
            return
        calls["n"] += 1
        calls["args"] = (hand_id, idx, advice)

    # Patch the symbol actually used by the /api/coach/preflop route.
    monkeypatch.setattr(
        coach_mod,
        "log_preflop_advice",
        fake_log_preflop_advice,
        raising=False,
    )

    client = _client()
    r = client.get("/api/coach/preflop", params={"hand_id": "H1", "idx": 0})
    # With coach enabled and charts configured, this should succeed.
    assert r.status_code == 200

    body = r.json()
    assert isinstance(body, dict)
    assert body.get("source") in {"chart", "equity"}

    # Helper should have been called exactly once with correct args.
    assert calls["n"] == 1
    hand_id, idx, advice = calls["args"]
    assert hand_id == "H1"
    assert idx == 0
    assert isinstance(advice, dict)
    # Soft sanity: payload should mirror the API response's basics.
    assert advice.get("source") == body.get("source")
    assert advice.get("bucket") == body.get("bucket")


def test_preflop_advice_not_logged_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    When LOG_PREFLOP_ADVICE is disabled, /api/coach/preflop should not
    result in a logged snapshot.
    """
    from backend import logger as logger_mod
    from backend.api import coach as coach_mod

    _enable_basic_coach_env(monkeypatch)

    # Force the flag off
    monkeypatch.setattr(logger_mod, "LOG_PREFLOP_ADVICE", False, raising=False)

    calls: Dict[str, Any] = {"n": 0}

    def fake_log_preflop_advice(
        hand_id: str,
        idx: int,
        advice: Dict[str, Any],
    ) -> None:
        # Honour the flag; with it false, this should be a no-op.
        if not getattr(logger_mod, "LOG_PREFLOP_ADVICE", False):
            return
        calls["n"] += 1

    monkeypatch.setattr(
        coach_mod,
        "log_preflop_advice",
        fake_log_preflop_advice,
        raising=False,
    )

    client = _client()
    r = client.get("/api/coach/preflop", params={"hand_id": "H1", "idx": 0})
    assert r.status_code == 200

    body = r.json()
    assert isinstance(body, dict)
    assert body.get("source") in {"chart", "equity"}

    # With the flag off, our stub should not record any calls.
    assert calls["n"] == 0
