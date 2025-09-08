"""
SQLite persistence layer for the NLH training simulator.

This module defines a simple logger that records hand and action
information to a SQLite database.  In milestone M0 the schema is
minimal: each hand is stored with its id, deck seed, engine and
evaluator.  Future milestones will extend this schema with per
decision logs and session tracking.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models.state import GameState


class SQLiteLogger:
    """A lightweight wrapper around sqlite3 for logging hands and actions."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        # Ensure parent directories exist
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        # Hands table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS hands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hand_id TEXT UNIQUE NOT NULL,
                deck_seed TEXT,
                engine TEXT,
                evaluator TEXT,
                created_at TEXT NOT NULL,
                state_json TEXT NOT NULL
            )
            """
        )
        # Actions table (minimal; may be extended in future tasks)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hand_id TEXT NOT NULL,
                idx INTEGER,
                street TEXT,
                actor_seat INTEGER,
                type TEXT,
                amount INTEGER,
                bucket TEXT,
                to_call_after INTEGER,
                pot_after INTEGER,
                time_ms INTEGER,
                rng_seed TEXT,
                snapped INTEGER,
                meta TEXT,
                FOREIGN KEY (hand_id) REFERENCES hands(hand_id)
            )
            """
        )
        self.conn.commit()

    def log_hand(self, state: GameState, engine: str, evaluator: str) -> None:
        """Persist a hand to the database.

        Args:
            state: The fully populated GameState.
            engine: Name of the engine used (e.g. 'PokerKit').
            evaluator: Name of the evaluator used (e.g. 'PokerKit' or 'HenryRLee').
        """
        state_json = state.model_dump_json()
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO hands (hand_id, deck_seed, engine, evaluator, created_at, state_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                state.hand_id,
                state.deck_seed,
                engine,
                evaluator,
                datetime.utcnow().isoformat(timespec="seconds"),
                state_json,
            ),
        )
        # Persist actions individually
        for action in state.action_history:
            cur.execute(
                """
                INSERT INTO actions (hand_id, idx, street, actor_seat, type, amount, bucket,
                                     to_call_after, pot_after, time_ms, rng_seed, snapped, meta)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.hand_id,
                    action.idx,
                    action.street.value,
                    action.actor_seat,
                    action.type.value,
                    action.amount,
                    action.bucket,
                    action.to_call_after,
                    action.pot_after,
                    action.time_ms,
                    action.rng_seed,
                    1 if action.snapped else 0 if action.snapped is not None else None,
                    json.dumps(action.meta) if action.meta is not None else None,
                ),
            )
        self.conn.commit()

    def fetch_hand_seed(self, hand_id: str) -> Optional[str]:
        """Retrieve the deck seed associated with a given hand id."""
        cur = self.conn.cursor()
        row = cur.execute(
            "SELECT deck_seed FROM hands WHERE hand_id = ?",
            (hand_id,),
        ).fetchone()
        return row["deck_seed"] if row else None

    def close(self) -> None:
        self.conn.close()