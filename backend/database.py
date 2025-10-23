"""
SQLite persistence layer for the NLH training simulator.

This module defines a simple logger that records hand and action
information to a SQLite database.  In milestone M0 the schema is
minimal: each hand is stored with its id, deck seed, engine and
evaluator.  Future milestones will extend this schema with per
decision logs and session tracking.

This file is copied from the upstream repository and slightly
modified to expose a `log_action` helper for incremental writes.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .models.state import GameState


class SQLiteLogger:
    """A lightweight wrapper around sqlite3 for logging hands and actions."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        # Ensure parent directories exist
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Disable thread checking so that the connection can be used by FastAPI
        # handlers across worker threads.  Without this parameter SQLite
        # raises ``ProgrammingError: SQLite objects created in a thread can only be
        # used in that same thread`` when the logger is accessed from multiple
        # threads in the test client.  The connection remains safe because
        # FastAPI uses a single event loop and requests are served
        # synchronously.
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        # Sessions table: groups multiple hands under a single session
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL
            )
            """
        )
        # Hands table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS hands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hand_id TEXT UNIQUE NOT NULL,
                session_id INTEGER,
                deck_seed TEXT,
                engine TEXT,
                evaluator TEXT,
                created_at TEXT NOT NULL,
                state_json TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
            """
        )
        # Actions table (extended to include more metadata)
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

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    def new_session(self) -> int:
        """Create a new session and return its id."""
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO sessions (created_at) VALUES (?)",
            (datetime.utcnow().isoformat(timespec="seconds"),),
        )
        self.conn.commit()
        return cur.lastrowid

    # ------------------------------------------------------------------
    # Hand logging
    # ------------------------------------------------------------------

    def log_hand(
        self, state: GameState, engine: str, evaluator: str, session_id: Optional[int] = None
    ) -> None:
        """Persist a complete hand to the database.

        This method stores the serialised state as JSON along with metadata
        about the engine and evaluator used.  It also logs each action
        contained in ``state.action_history``.  If ``session_id`` is
        provided, the hand is associated with that session.
        """
        state_json = state.model_dump_json()
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO hands (hand_id, session_id, deck_seed, engine, evaluator, created_at, state_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                state.hand_id,
                session_id,
                state.deck_seed,
                engine,
                evaluator,
                datetime.utcnow().isoformat(timespec="seconds"),
                state_json,
            ),
        )
        # Persist actions individually
        for action in state.action_history:
            self.log_action(
                hand_id=state.hand_id,
                idx=action.idx,
                street=str(action.street),
                actor_seat=action.actor_seat,
                type=str(action.type),
                amount=action.amount,
                bucket=action.bucket,
                to_call_after=action.to_call_after,
                pot_after=action.pot_after,
                time_ms=action.time_ms,
                rng_seed=action.rng_seed,
                snapped=1 if action.snapped else 0 if action.snapped is not None else None,
                meta=json.dumps(action.meta) if action.meta is not None else None,
            )
        self.conn.commit()

    def log_action(
        self,
        *,
        hand_id: str,
        idx: int,
        street: str,
        actor_seat: int,
        type: str,
        amount: Optional[int] = None,
        bucket: Optional[str] = None,
        to_call_after: Optional[int] = None,
        pot_after: Optional[int] = None,
        time_ms: Optional[int] = None,
        rng_seed: Optional[str] = None,
        snapped: Optional[int] = None,
        meta: Optional[str] = None,
    ) -> None:
        """Record a single action for a hand.

        This helper inserts a row into the actions table.  It is safe to
        call repeatedly during a hand; the caller must manage the
        ``idx`` sequence.
        """
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO actions (
                hand_id, idx, street, actor_seat, type, amount, bucket,
                to_call_after, pot_after, time_ms, rng_seed, snapped, meta
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hand_id,
                idx,
                street,
                actor_seat,
                type,
                amount,
                bucket,
                to_call_after,
                pot_after,
                time_ms,
                rng_seed,
                snapped,
                meta,
            ),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Fetching helpers
    # ------------------------------------------------------------------

    def fetch_hand_seed(self, hand_id: str) -> Optional[str]:
        """Retrieve the deck seed associated with a given hand id."""
        cur = self.conn.cursor()
        row = cur.execute(
            "SELECT deck_seed FROM hands WHERE hand_id = ?",
            (hand_id,),
        ).fetchone()
        return row["deck_seed"] if row else None

    def fetch_hand_state_json(self, hand_id: str) -> Optional[str]:
        """Return the stored state JSON for a given hand id."""
        cur = self.conn.cursor()
        row = cur.execute(
            "SELECT state_json FROM hands WHERE hand_id = ?",
            (hand_id,),
        ).fetchone()
        return row["state_json"] if row else None

    def fetch_hand_actions(self, hand_id: str) -> Iterable[sqlite3.Row]:
        """Yield all action rows for a given hand id in order."""
        cur = self.conn.cursor()
        for row in cur.execute(
            "SELECT idx, street, actor_seat, type, amount, bucket, to_call_after, pot_after, time_ms, rng_seed, snapped, meta FROM actions WHERE hand_id = ? ORDER BY idx",
            (hand_id,),
        ):
            yield row

    def fetch_hands_for_session(self, session_id: int) -> Iterable[sqlite3.Row]:
        """Yield all hand rows belonging to a session."""
        cur = self.conn.cursor()
        for row in cur.execute(
            "SELECT hand_id, state_json FROM hands WHERE session_id = ? ORDER BY id",
            (session_id,),
        ):
            yield row

    def close(self) -> None:
        self.conn.close()