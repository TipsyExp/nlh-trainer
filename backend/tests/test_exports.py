"""
Tests for hand export helpers and API endpoints.

These tests verify that the SQLite logger can export logged hands back to
JSON and CSV formats, and that the FastAPI routes surface these exports
correctly.  They also provide a deterministic round‑trip check to
ensure that exported JSON can be imported back into an identical
``GameState``.
"""

import csv
import os
import tempfile

from fastapi.testclient import TestClient

from backend.main import app
from backend.database import SQLiteLogger
from backend.models.state import (
    GameState,
    TableState,
    PlayerState,
    SeatType,
    PlayerStatus,
    ActionRecord,
    Street,
    ActionType,
    export_json,
    import_json,
)


def _sample_state(with_actions: bool = False) -> GameState:
    """Create a GameState instance with optional sample actions."""
    table = TableState(seat_count=2, sb=50, bb=100, ante=0)
    players = [
        PlayerState(seat=0, type=SeatType.human, alias="Hero", stack=10000, status=PlayerStatus.active),
        PlayerState(seat=1, type=SeatType.bot, alias="Bot", stack=10000, status=PlayerStatus.active),
    ]
    gs = GameState(
        hand_id="hand_export",
        deck_seed="seed_export",
        table=table,
        dealer_seat=0,
        sb_seat=1,
        bb_seat=0,
        street=Street.preflop,
        players=players,
    )
    if with_actions:
        # Add a trivial blind posting action to ensure CSV output
        gs.action_history.append(
            ActionRecord(
                idx=0,
                street=Street.preflop,
                actor_seat=0,
                type=ActionType.post_blind,
                amount=50,
                bucket=None,
                to_call_after=50,
                pot_after=150,
                time_ms=10,
                rng_seed="blind_seed",
                snapped=True,
                meta={"note": "SB posted"},
            )
        )
    return gs


def test_export_json_round_trip_and_endpoint():
    """Ensure logged JSON can be exported and imported deterministically and via API."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.sqlite")
        # Set environment so the API picks up our temp DB
        os.environ["LOG_DB_PATH"] = db_path
        logger = SQLiteLogger(db_path)
        state = _sample_state(with_actions=True)
        logger.log_hand(state, engine="TestEngine", evaluator="TestEval")
        # Export directly from logger
        json_str = logger.get_hand_json(state.hand_id)
        assert json_str is not None
        # Import back into GameState and compare
        restored = import_json(json_str)
        assert restored.model_dump() == state.model_dump()
        logger.close()
        # Use API to export JSON
        client = TestClient(app)
        resp = client.get(f"/api/export/hand/{state.hand_id}/json")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        # The response body should match the direct export (ignoring whitespace)
        assert resp.text.strip() == json_str.strip()


def test_export_csv_and_endpoint():
    """Ensure action history can be exported to CSV both directly and via API."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.sqlite")
        os.environ["LOG_DB_PATH"] = db_path
        logger = SQLiteLogger(db_path)
        # Sample state with one action
        state = _sample_state(with_actions=True)
        logger.log_hand(state, engine="TestEngine", evaluator="TestEval")
        csv_data = logger.export_actions_csv(state.hand_id)
        assert csv_data is not None
        # Parse CSV and verify header + row count
        reader = csv.reader(csv_data.splitlines())
        rows = list(reader)
        # Expect header + one action row
        assert len(rows) == 2
        header = rows[0]
        # Basic sanity check: header contains expected columns
        assert header[0] == "idx" and header[1] == "street"
        data_row = rows[1]
        # idx should be string "0"
        assert data_row[0] == "0"
        logger.close()
        # Via API
        client = TestClient(app)
        resp = client.get(f"/api/export/hand/{state.hand_id}/csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        # Response should match direct export
        assert resp.text == csv_data