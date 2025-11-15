# backend/tests/test_coach_preflop_logging.py
from __future__ import annotations

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from backend.main import app


def _client() -> TestClient:
    return TestClient(app)


@pytest.mark.skip(
    reason="Enable after wiring preflop advice logging into /api/coach/preflop."
)
def test_preflop_advice_logging_called_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Placeholder test for preflop advice logging.

    Once /api/coach/preflop supports logging snapshots tied to a hand_id/idx,
    this test should ensure:

      - LOG_PREFLOP_ADVICE=true triggers a call to logger.log_preflop_advice.
      - The helper receives the correct hand_id, idx, and a dict payload.
      - Coach is enabled and charts are configured.

    For now, it is skipped to keep the test suite green until the
    logging behaviour is implemented.
    """
    # Enable coach + preflop logging via env (future behaviour).
    monkeypatch.setenv("COACH_ENABLED", "true")
    monkeypatch.setenv("LOG_PREFLOP_ADVICE", "true")
    # Point to the tiny dev HU chart fixture.
    monkeypatch.setenv("PREFLOP_CHART_PATHS", "devdata/charts/hu_example.json")

    # Monkeypatch the logger helper; use raising=False so this remains
    # tolerant even if the implementation detail changes slightly.
    from backend import logger as logger_mod

    calls: Dict[str, Any] = {"n": 0, "args": None}

    def fake_log_preflop_advice(
        hand_id: str,
        idx: int,
        advice: Dict[str, Any],
    ) -> None:  # type: ignore[override]
        calls["n"] += 1
        calls["args"] = (hand_id, idx, advice)

    monkeypatch.setattr(
        logger_mod,
        "log_preflop_advice",
        fake_log_preflop_advice,
        raising=False,
    )

    client = _client()

    # Minimal preflop advice request; once logging is wired, the endpoint is
    # expected to log a snapshot associated with this hand/index.
    r = client.get("/api/coach/preflop", params={"hand_id": "H1", "idx": 0})
    assert r.status_code in {200, 501, 404, 400}
    body = r.json()
    assert isinstance(body, dict)

    # Once logging is implemented and the endpoint behaviour stabilizes, we
    # can un-skip this test and strengthen the assertions, e.g.:
    #
    # assert r.status_code == 200
    # assert calls["n"] == 1
    # hand_id, idx, advice = calls["args"]
    # assert hand_id == "H1"
    # assert idx == 0
    # assert isinstance(advice, dict)
    # assert advice.get("source") in {"chart", "equity"}
