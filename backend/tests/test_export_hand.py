# backend/tests/test_export_hand.py
"""
Tests for /api/export/hand/{hand_id}.json

Focus:

    * Baseline export shape (no *snapshot* fields like equity_snapshot /
      coach_advice when logging is disabled).
    * coach_advice snapshot wiring:
        - log_coach_advice() updates the log DB for a given (hand_id, idx)
        - /api/export/hand/{hand_id}.json surfaces that payload as
          actions[*].coach_advice for the matching idx.

These tests deliberately avoid depending on preflop/postflop coach internals:
they exercise only the interaction between the logger and the export API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple

import pytest
from fastapi.testclient import TestClient

from backend.main import app


def _create_session_and_hand(client: TestClient) -> Tuple[str, str]:
    """
    Helper: create a minimal 2-seat session and start a hand.

    Returns:
        (session_id, hand_id)
    """
    # Create session
    resp = client.post(
        "/api/session",
        json={
            "seats": 2,
            "sb": 50,
            "bb": 100,
            "stacks": [10000, 10000],
            "bot_mode": "heuristic",
            "bot_profile": "CALLCHECK",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    session_id = str(data["session_id"])

    # Start hand for hero seat 0
    resp = client.post(
        "/api/hand/start",
        json={"session_id": session_id, "seat": 0},
    )
    assert resp.status_code == 200
    start_body = resp.json()
    # API-CONTRACT.md specifies { "hand_id": "H1" } as the response shape.
    hand_id = str(start_body["hand_id"])
    return session_id, hand_id


def test_export_hand_no_snapshots_when_logging_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    With snapshot logging flags disabled, the hand export should not include
    equity_snapshot or coach_advice on actions for the current hand.

    Note: preflop_advice may be present due to legacy / non-snapshot flows and
    is not asserted on here.
    """
    # Ensure logging flags are off at both env and module level for this test.
    monkeypatch.setenv("LOG_EQUITY_SNAPSHOT", "false")
    monkeypatch.setenv("LOG_PREFLOP_ADVICE", "false")
    monkeypatch.setenv("LOG_COACH_ADVICE", "false")

    from backend import logger as logger_mod

    monkeypatch.setattr(logger_mod, "LOG_EQUITY_SNAPSHOT", False, raising=False)
    monkeypatch.setattr(logger_mod, "LOG_PREFLOP_ADVICE", False, raising=False)
    monkeypatch.setattr(logger_mod, "LOG_COACH_ADVICE", False, raising=False)

    client = TestClient(app)
    _, hand_id = _create_session_and_hand(client)

    r = client.get(f"/api/export/hand/{hand_id}.json")
    assert r.status_code == 200

    body = r.json()
    assert body.get("hand_id") == hand_id

    actions = body.get("actions", [])
    assert isinstance(actions, list)

    # If there are no actions (unlikely but possible in edge cases), this test
    # degenerates to checking the absence of snapshot fields structurally.
    for action in actions:
        # Equity snapshots and unified coach advice snapshots are purely
        # opt-in; when logging is disabled they should not appear.
        assert "equity_snapshot" not in action
        assert "coach_advice" not in action
        # preflop_advice may be present via legacy flows; we do not assert on it.


def test_export_hand_includes_coach_advice_when_logged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    When log_coach_advice() is called for a given (hand_id, idx), the JSON
    hand export should surface that payload under actions[*].coach_advice
    for the matching idx.

    This exercises the DB column + export wiring without depending on the
    runtime /api/coach/advice route.
    """
    from backend import (
        logger as logger_mod,
    )  # import here so monkeypatched env is visible

    # Use an isolated log DB for this test.
    db_path = tmp_path / "export_hand.sqlite"
    monkeypatch.setenv("LOG_DB_PATH", str(db_path))

    # Force the logger singleton to reinitialise against our temp DB.
    logger_mod.reset_logger()

    # Enable only coach-advice logging (equity/preflop flags are irrelevant here).
    # We patch the module-level flags directly so behaviour does not depend on
    # how config/env were initialised earlier in the test run.
    monkeypatch.setattr(logger_mod, "LOG_COACH_ADVICE", True, raising=False)
    monkeypatch.setattr(logger_mod, "LOG_EQUITY_SNAPSHOT", False, raising=False)
    monkeypatch.setattr(logger_mod, "LOG_PREFLOP_ADVICE", False, raising=False)

    client = TestClient(app)
    _, hand_id = _create_session_and_hand(client)

    # First export: there should be no coach_advice yet.
    r1 = client.get(f"/api/export/hand/{hand_id}.json")
    assert r1.status_code == 200
    body1 = r1.json()
    actions1 = body1.get("actions", [])
    assert isinstance(actions1, list)

    if not actions1:
        # If no actions are present for this hand, we cannot meaningfully test
        # per-action snapshots; treat as a skipped test rather than hard-failing.
        pytest.skip(
            "No actions recorded for exported hand; cannot test coach_advice snapshot wiring"
        )

    # Pick the first action as our target index.
    target_action = actions1[0]
    target_idx = int(target_action["idx"])
    assert "coach_advice" not in target_action

    # Build a minimal AdviceV1-like payload for logging. The export code should
    # round-trip this blob as-is under actions[*].coach_advice.
    sample_advice: Dict[str, Any] = {
        "version": 1,
        "status": "ok",
        "meta": {
            "street": "preflop",
            "n_players": 2,
            "hero_seat": 0,
            "source": "chart",
        },
        "recommendation": {
            "bucket": "2.5x",
            "strategy_bar": [
                {"action": "2.5x", "weight": 1.0},
            ],
        },
        "equity": None,
        "thresholds": None,
        "rationale": "stub coach advice for export wiring test",
    }

    # Attach the advice snapshot directly via the logger helper.
    logger_mod.log_coach_advice(
        hand_id=str(hand_id), idx=target_idx, advice=sample_advice
    )

    # Second export: the same hand should now surface coach_advice for that idx.
    r2 = client.get(f"/api/export/hand/{hand_id}.json")
    assert r2.status_code == 200
    body2 = r2.json()
    actions2 = body2.get("actions", [])
    assert isinstance(actions2, list)
    assert actions2, "Expected at least one action in exported hand"

    # Find the action with matching idx.
    matching = None
    for action in actions2:
        if int(action.get("idx", -1)) == target_idx:
            matching = action
            break

    assert (
        matching is not None
    ), "Expected to find an action with the logged idx in export"
    assert (
        "coach_advice" in matching
    ), "coach_advice field should be present after logging snapshot"
    assert matching["coach_advice"] == sample_advice
