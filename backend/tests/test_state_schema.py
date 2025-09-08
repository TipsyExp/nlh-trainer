"""
Tests for the state schema models and persistence.

These tests ensure that the Pydantic models mirror the expected
structure from the documentation and that exporting and importing
JSON round‑trips without data loss.  They also verify that the
SQLite logger stores the deck seed for each hand.
"""

import json
import os
import tempfile

from backend.models.state import GameState, TableState, Street, PlayerState, SeatType, PlayerStatus, export_json, import_json
from backend.database import SQLiteLogger


def _sample_game_state() -> GameState:
    """Create a minimal but nontrivial GameState instance for testing."""
    table = TableState(seat_count=2, sb=50, bb=100, ante=0)
    players = [
        PlayerState(seat=0, type=SeatType.human, alias="Hero", stack=10000, status=PlayerStatus.active),
        PlayerState(seat=1, type=SeatType.bot, alias="Bot", stack=10000, status=PlayerStatus.active),
    ]
    return GameState(
        hand_id="hand_1",
        deck_seed="seed123",
        table=table,
        dealer_seat=0,
        sb_seat=1,
        bb_seat=0,
        street=Street.preflop,
        players=players,
    )


def test_round_trip_json():
    """Verify that exporting then importing a GameState returns an identical structure."""
    state = _sample_game_state()
    json_str = export_json(state)
    # ensure JSON is valid
    parsed = json.loads(json_str)
    # import back into a GameState
    restored = import_json(json_str)
    assert restored.model_dump() == state.model_dump()


def test_sqlite_logger_stores_seed():
    """Ensure that the SQLiteLogger stores and retrieves the deck seed for a hand."""
    state = _sample_game_state()
    # Use a temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.sqlite")
        logger = SQLiteLogger(db_path)
        logger.log_hand(state, engine="PokerKit", evaluator="PokerKit")
        seed = logger.fetch_hand_seed(state.hand_id)
        assert seed == state.deck_seed
        logger.close()