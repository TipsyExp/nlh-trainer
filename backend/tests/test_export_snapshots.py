# backend/tests/test_export_snapshots.py
from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.api.export import CSV_FIELDS as EXPORT_CSV_FIELDS
from backend.api import export as export_mod


def _client() -> TestClient:
    return TestClient(app)


class _StubLogger:
    """
    Minimal stub logger that mimics the parts of SQLiteLogger used by the
    export routes. It returns a single hand with a single action row that
    includes both snapshot JSON columns.
    """

    def __init__(self) -> None:
        self._state_json = json.dumps({"hand_id": "H1", "foo": "bar"})
        self._equity_snapshot = {"backend": "pbots", "mode": "ranges"}
        self._preflop_advice = {"source": "equity", "bucket": "call"}

    # --- Hand-level helpers ---

    def fetch_hand_state_json(self, hand_id: str) -> str | None:
        if hand_id != "H1":
            return None
        return self._state_json

    def fetch_hand_actions(self, hand_id: str) -> Iterable[Dict[str, Any]]:
        if hand_id != "H1":
            return []
        # Dict-like row with all the columns export.py expects.
        yield {
            "idx": 0,
            "street": "preflop",
            "actor_seat": 0,
            "type": "bet",
            "amount": 100,
            "bucket": "2.5x",
            "to_call_after": 0,
            "pot_after": 150,
            "time_ms": 123,
            "rng_seed": "seed",
            "snapped": 0,
            "meta": None,
            "engine": "PokerKit",
            "evaluator": "PokerKit",
            "created_at": "2024-01-01T00:00:00Z",
            # New snapshot columns the export code will decode
            "equity_snapshot_json": json.dumps(self._equity_snapshot),
            "preflop_advice_json": json.dumps(self._preflop_advice),
        }

    # --- Session-level helpers ---

    def fetch_hands_for_session(self, session_id: int) -> Iterable[Dict[str, Any]]:
        # Only a single session (id=1) containing hand H1.
        if session_id != 1:
            return []
        return [
            {
                "hand_id": "H1",
                "state_json": self._state_json,
            }
        ]


def test_export_hand_includes_snapshots(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    JSON hand export should include decoded equity_snapshot and preflop_advice
    when the underlying rows expose equity_snapshot_json / preflop_advice_json.

    CSV export should remain backward-compatible and ignore snapshot fields.
    """
    stub_logger = _StubLogger()

    # Patch the export module's get_logger symbol to return our stub.
    monkeypatch.setattr(export_mod, "get_logger", lambda: stub_logger, raising=False)

    client = _client()

    # ---- JSON export ----
    resp = client.get("/api/export/hand/H1.json")
    assert resp.status_code == 200

    body: Dict[str, Any] = resp.json()
    assert body["hand_id"] == "H1"
    assert isinstance(body["state"], dict)
    assert "actions" in body
    assert isinstance(body["actions"], list)
    assert len(body["actions"]) == 1

    action = body["actions"][0]
    # Core fields still present
    assert action["idx"] == 0
    assert action["street"] == "preflop"
    assert action["action"] == "bet"

    # Snapshot fields should be present and decoded from JSON.
    assert "equity_snapshot" in action
    assert "preflop_advice" in action

    assert action["equity_snapshot"] == stub_logger._equity_snapshot
    assert action["preflop_advice"] == stub_logger._preflop_advice

    # ---- CSV export ----
    csv_resp = client.get("/api/export/hand/H1.csv")
    assert csv_resp.status_code == 200
    text = csv_resp.text.strip().splitlines()
    # First row is the header; it must match the stable CSV_FIELDS contract.
    header = text[0].split(",")
    assert header == EXPORT_CSV_FIELDS
    # Snapshot fields are intentionally not present in CSV.


def test_export_session_includes_snapshots(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Session JSON export should surface snapshots for all hands' actions via the
    same decoded equity_snapshot / preflop_advice fields.
    """
    stub_logger = _StubLogger()
    monkeypatch.setattr(export_mod, "get_logger", lambda: stub_logger, raising=False)

    client = _client()

    resp = client.get("/api/export/session/1.json")
    assert resp.status_code == 200
    body = resp.json()

    assert body["session_id"] == 1
    assert "hands" in body
    assert isinstance(body["hands"], list)
    assert len(body["hands"]) == 1

    hand = body["hands"][0]
    assert hand["hand_id"] == "H1"
    assert isinstance(hand["state"], dict)

    actions: List[Dict[str, Any]] = hand["actions"]
    assert len(actions) == 1
    action = actions[0]

    assert action["equity_snapshot"] == stub_logger._equity_snapshot
    assert action["preflop_advice"] == stub_logger._preflop_advice

    # CSV variant should still work and keep the header contract.
    csv_resp = client.get("/api/export/session/1.csv")
    assert csv_resp.status_code == 200
    text = csv_resp.text.strip().splitlines()
    header = text[0].split(",")
    assert header == EXPORT_CSV_FIELDS
