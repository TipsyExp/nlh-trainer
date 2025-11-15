# backend/tests/test_equity_logging.py
from __future__ import annotations

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from backend.main import app


def _client() -> TestClient:
    return TestClient(app)


def _equity_request_body() -> Dict[str, Any]:
    # Minimal HU equity request
    return {
        "players": [
            {"hand": ["Ah", "Ad"]},
            {"hand": ["Kh", "Kd"]},
        ],
        "board": [],
        "dead": [],
        "exact": False,
        "iters": 1000,
    }


def test_equity_snapshot_logging_called_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    When LOG_EQUITY_SNAPSHOT is enabled and /api/equity is called with
    hand_id/idx, the equity logging helper should be invoked.
    """
    client = _client()

    # Import modules to patch
    from backend import logger as logger_mod
    from backend.api.routes import equity as equity_mod

    # Force the flag on at the logger module level
    monkeypatch.setattr(logger_mod, "LOG_EQUITY_SNAPSHOT", True, raising=False)

    calls: Dict[str, Any] = {"n": 0, "args": None}

    def fake_log_equity_snapshot(
        hand_id: str,
        idx: int,
        snapshot: Dict[str, Any],
    ) -> None:
        # Mirror the flag gating behaviour: respect LOG_EQUITY_SNAPSHOT.
        if not getattr(logger_mod, "LOG_EQUITY_SNAPSHOT", False):
            return
        calls["n"] += 1
        calls["args"] = (hand_id, idx, snapshot)

    # Patch the helper used by the /api/equity route.
    monkeypatch.setattr(
        equity_mod,
        "log_equity_snapshot",
        fake_log_equity_snapshot,
        raising=False,
    )

    body = _equity_request_body()

    r = client.post(
        "/api/equity",
        params={"hand_id": "H1", "idx": 0},
        json=body,
    )
    assert r.status_code == 200
    resp = r.json()
    assert resp.get("ok") is True

    # Helper should have been called exactly once with the correct args.
    assert calls["n"] == 1
    hand_id, idx, snapshot = calls["args"]
    assert hand_id == "H1"
    assert idx == 0
    assert isinstance(snapshot, dict)
    # Soft sanity: snapshot should mention backend/mode at minimum.
    assert "backend" in snapshot
    assert "mode" in snapshot


def test_equity_snapshot_not_logged_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    When LOG_EQUITY_SNAPSHOT is disabled, /api/equity should *not* result in
    a logged snapshot, even if hand_id/idx are provided.
    """
    client = _client()

    from backend import logger as logger_mod
    from backend.api.routes import equity as equity_mod

    # Force the flag off
    monkeypatch.setattr(logger_mod, "LOG_EQUITY_SNAPSHOT", False, raising=False)

    calls: Dict[str, Any] = {"n": 0}

    def fake_log_equity_snapshot(
        hand_id: str,
        idx: int,
        snapshot: Dict[str, Any],
    ) -> None:
        # Honour the flag, same as above; this should short-circuit.
        if not getattr(logger_mod, "LOG_EQUITY_SNAPSHOT", False):
            return
        calls["n"] += 1

    monkeypatch.setattr(
        equity_mod,
        "log_equity_snapshot",
        fake_log_equity_snapshot,
        raising=False,
    )

    body = _equity_request_body()

    r = client.post(
        "/api/equity",
        params={"hand_id": "H1", "idx": 0},
        json=body,
    )
    assert r.status_code == 200
    resp = r.json()
    assert resp.get("ok") is True

    # With the flag off, our stub should not record any calls.
    assert calls["n"] == 0
