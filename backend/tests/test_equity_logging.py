# backend/tests/test_equity_logging.py
from __future__ import annotations

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from backend.main import app


def _client() -> TestClient:
    return TestClient(app)


@pytest.mark.skip(
    reason="Enable after wiring equity snapshot logging into /api/equity."
)
def test_equity_snapshot_logging_called_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Placeholder test for equity snapshot logging.

    Once /api/equity supports logging snapshots tied to a hand_id/idx,
    this test should ensure:

      - LOG_EQUITY_SNAPSHOT=true triggers a call to logger.log_equity_snapshot.
      - The helper receives the correct hand_id, idx, and a dict payload.

    For now, it is skipped to keep the test suite green until the
    logging behaviour is implemented.
    """
    # Enable snapshot logging via env (future behaviour).
    monkeypatch.setenv("LOG_EQUITY_SNAPSHOT", "true")

    # Monkeypatch the logger helper; use raising=False so this remains
    # tolerant even before the helper is implemented.
    from backend import logger as logger_mod

    calls: Dict[str, Any] = {"n": 0, "args": None}

    def fake_log_equity_snapshot(hand_id: str, idx: int, snapshot: Dict[str, Any]) -> None:  # type: ignore[override]
        calls["n"] += 1
        calls["args"] = (hand_id, idx, snapshot)

    monkeypatch.setattr(
        logger_mod,
        "log_equity_snapshot",
        fake_log_equity_snapshot,
        raising=False,
    )

    client = _client()

    # Minimal HU equity request; once logging is wired, the endpoint is
    # expected to honour hand_id/idx for snapshot association.
    body = {
        "players": [
            {"hand": ["Ah", "Ad"]},
            {"hand": ["Kh", "Kd"]},
        ],
        "board": [],
        "dead": [],
        "exact": False,
        "iters": 1000,
    }

    r = client.post(
        "/api/equity",
        params={"hand_id": "H1", "idx": 0},
        json=body,
    )
    assert r.status_code == 200
    resp = r.json()
    assert resp.get("ok") is True

    # Once logging is implemented, un-skip this test and assert:
    # assert calls["n"] == 1
    # hand_id, idx, snapshot = calls["args"]
    # assert hand_id == "H1"
    # assert idx == 0
    # assert isinstance(snapshot, dict)
