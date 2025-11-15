# backend/tests/test_export_snapshots.py
from __future__ import annotations

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from backend.main import app


def _client() -> TestClient:
    return TestClient(app)


@pytest.mark.skip(
    reason=(
        "Enable after wiring equity_snapshot_json / preflop_advice_json "
        "into SQLiteLogger schema and export routes."
    )
)
def test_export_hand_includes_snapshots(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Placeholder: once snapshot logging is implemented, this test should verify
    that JSON exports surface equity / preflop advice snapshots.

    Target contract (for future implementation):

      1. Seed the logger DB with:
           - one hand row (state_json)
           - at least one action row with:
               equity_snapshot_json = '{"backend":"pbots","mode":"ranges",...}'
               preflop_advice_json = '{"source":"equity","bucket":"call",...}'

      2. Call:
           GET /api/export/hand/{hand_id}.json

      3. Assert:
           - Response status_code == 200.
           - actions[i] contains:
               - "equity_snapshot" as a deserialized object (dict),
               - "preflop_advice" as a deserialized object (dict),
             or equivalent stable field names decided for the export contract.

    Notes:
      - Keep CSV export optional for snapshots (JSON is the primary consumer).
      - Make fields optional for backward compatibility; tests should
        tolerate their absence when logging is disabled.
    """
    client = _client()

    # Once wired, this test will explicitly seed the database via get_logger()
    # and then assert on the export JSON. For now we only ensure the endpoint
    # shape is stable and the test remains a no-op via @skip.
    resp = client.get("/api/export/hand/H1.json")
    # When enabled, tighten these assertions to match the real contract.
    assert resp.status_code in {200, 404}
    body: Dict[str, Any] = resp.json()
    assert isinstance(body, dict)


@pytest.mark.skip(
    reason=(
        "Enable after wiring snapshot fields into session export and ensuring "
        "multiple hands/decisions surface equity/preflop advice snapshots."
    )
)
def test_export_session_includes_snapshots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Placeholder: ensure that /api/export/session/{session_id}.json surfaces
    snapshot data for all hands in the session once implemented.

    Future behaviour to assert:

      - For a session with at least one hand containing actions with
        equity_snapshot_json / preflop_advice_json in the DB, the JSON
        export should include those decoded as:
            hand["actions"][i]["equity_snapshot"]
            hand["actions"][i]["preflop_advice"]
        where present.

      - Snapshots remain optional and are omitted or null when logging
        is disabled.
    """
    client = _client()
    resp = client.get("/api/export/session/1.json")
    assert resp.status_code in {200, 404}
    body = resp.json()
    assert isinstance(body, dict)
    # When enabled:
    #   - assert "hands" in body
    #   - assert any(action.get("equity_snapshot") for action in actions)
