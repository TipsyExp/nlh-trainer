"""
SQLite persistence layer for the NLH training simulator.

This module defines a simple logger that records hand and action
information to a SQLite database. M0/M1 design prefers *incremental*
per-decision writes via log_action; we also upsert the hand snapshot
(state_json) as needed so exports work mid-hand.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .models.state import GameState


DEFAULT_ENGINE = "PokerKit"
DEFAULT_EVALUATOR = "PokerKit"


class SQLiteLogger:
    """A lightweight wrapper around sqlite3 for logging hands and actions."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # Keep FK behavior sane
        self.conn.execute("PRAGMA foreign_keys = ON;")
        # Reasonable default for concurrent readers
        try:
            self.conn.execute("PRAGMA journal_mode = WAL;")
        except sqlite3.DatabaseError:
            pass
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema (create + minimal migrations)
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        cur = self.conn.cursor()

        # Sessions table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL
            )
            """
        )

        # Hands table (hand_id is UNIQUE so /export can always fetch "latest" by id)
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

        # Actions table. NOTE: No unique constraint on (hand_id, idx) because tests
        # may reuse the same textual hand_id across runs; we only order by idx.
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hand_id TEXT NOT NULL,
                idx INTEGER NOT NULL,
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
                engine TEXT,
                evaluator TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (hand_id) REFERENCES hands(hand_id)
            )
            """
        )

        # Helpful non-unique index
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_actions_hand_idx ON actions(hand_id, idx)"
        )

        # Minimal migrations for stale DBs: add missing columns if needed
        self._ensure_columns(
            "hands",
            {
                "hand_id": "TEXT",
                "session_id": "INTEGER",
                "deck_seed": "TEXT",
                "engine": "TEXT",
                "evaluator": "TEXT",
                "created_at": "TEXT",
                "state_json": "TEXT",
            },
        )
        self._ensure_columns(
            "actions",
            {
                "hand_id": "TEXT",
                "idx": "INTEGER",
                "street": "TEXT",
                "actor_seat": "INTEGER",
                "type": "TEXT",
                "amount": "INTEGER",
                "bucket": "TEXT",
                "to_call_after": "INTEGER",
                "pot_after": "INTEGER",
                "time_ms": "INTEGER",
                "rng_seed": "TEXT",
                "snapped": "INTEGER",
                "meta": "TEXT",
                "engine": "TEXT",
                "evaluator": "TEXT",
                "created_at": "TEXT",
            },
        )

        self.conn.commit()

    def _column_names(self, table: str) -> set[str]:
        cur = self.conn.cursor()
        rows = cur.execute(f"PRAGMA table_info({table});").fetchall()
        return {r["name"] for r in rows}

    def _ensure_columns(self, table: str, desired: dict[str, str]) -> None:
        """Best-effort add of missing columns for an existing DB."""
        existing = self._column_names(table)
        cur = self.conn.cursor()
        for col, coltype in desired.items():
            if col not in existing:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
        # No commit here; caller commits once after all ops.

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    def new_session(self) -> int:
        """Create a new session and return its id."""
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO sessions (created_at) VALUES (?)",
            (datetime.now(timezone.utc).replace(microsecond=0).isoformat(),),
        )
        self.conn.commit()
        return cur.lastrowid

    # ------------------------------------------------------------------
    # Hand helpers
    # ------------------------------------------------------------------

    def _ensure_hand_exists(
        self,
        *,
        hand_id: str,
        session_id: Optional[int],
        deck_seed: Optional[str],
        engine: Optional[str],
        evaluator: Optional[str],
        state_json: Optional[str] = None,
    ) -> None:
        """
        Ensure there's a parent row in `hands` for FK integrity before logging actions.

        This is defensive; proper flow should upsert a real snapshot via
        `upsert_hand_snapshot` or `log_hand`. If a stale DB is used or the caller
        logs an action before snapshotting, we insert a minimal placeholder.
        """
        cur = self.conn.cursor()
        row = cur.execute(
            "SELECT 1 FROM hands WHERE hand_id = ? LIMIT 1", (hand_id,)
        ).fetchone()
        if row:
            return

        # Minimal placeholder JSON; will be updated by upsert/log_hand later.
        minimal_json = state_json or json.dumps({"hand_id": hand_id})
        cur.execute(
            """
            INSERT INTO hands (
                hand_id, session_id, deck_seed, engine, evaluator, created_at, state_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hand_id,
                session_id,
                deck_seed,
                engine or DEFAULT_ENGINE,
                evaluator or DEFAULT_EVALUATOR,
                datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                minimal_json,
            ),
        )
        self.conn.commit()

    def upsert_hand_snapshot(
        self,
        *,
        hand_id: str,
        session_id: Optional[int],
        deck_seed: Optional[str],
        engine: str,
        evaluator: str,
        state_json: str,
    ) -> None:
        """Insert or update the current snapshot for a hand (no REPLACE/delete)."""
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO hands (hand_id, session_id, deck_seed, engine, evaluator, created_at, state_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(hand_id) DO UPDATE SET
                session_id = excluded.session_id,
                deck_seed  = excluded.deck_seed,
                engine     = excluded.engine,
                evaluator  = excluded.evaluator,
                state_json = excluded.state_json
            """,
            (
                hand_id,
                session_id,
                deck_seed,
                engine,
                evaluator,
                datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                state_json,
            ),
        )
        self.conn.commit()

    def log_hand(
        self,
        state: GameState,
        engine: str,
        evaluator: str,
        session_id: Optional[int] = None,
    ) -> None:
        """Persist a complete hand snapshot, and insert actions only if none exist.

        In M1, actions are usually logged incrementally via log_action().
        This method is defensive: it will NOT duplicate actions if they
        were already recorded for this hand_id.
        """
        state_json = state.model_dump_json()
        self.upsert_hand_snapshot(
            hand_id=state.hand_id,
            session_id=session_id,
            deck_seed=state.deck_seed,
            engine=engine,
            evaluator=evaluator,
            state_json=state_json,
        )

        cur = self.conn.cursor()
        # If actions already exist for this hand, don't re-insert them
        exists = cur.execute(
            "SELECT 1 FROM actions WHERE hand_id = ? LIMIT 1", (state.hand_id,)
        ).fetchone()
        if exists:
            return

        for action in state.action_history:
            meta_str = json.dumps(action.meta) if action.meta is not None else None
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
                snapped=(
                    1 if action.snapped else 0 if action.snapped is not None else None
                ),
                meta=meta_str,
                engine=engine,
                evaluator=evaluator,
            )

    # ------------------------------------------------------------------
    # Action logging
    # ------------------------------------------------------------------

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
        engine: Optional[str] = None,
        evaluator: Optional[str] = None,
    ) -> None:
        """Record a single action for a hand.

        Safe to call repeatedly during a hand; the caller must manage the
        ``idx`` sequence. Writes are committed immediately.
        """
        # Make sure parent hand exists to satisfy FK constraints
        self._ensure_hand_exists(
            hand_id=hand_id,
            session_id=None,  # caller can later upsert full snapshot with session_id
            deck_seed=rng_seed,
            engine=engine or DEFAULT_ENGINE,
            evaluator=evaluator or DEFAULT_EVALUATOR,
        )

        cur = self.conn.cursor()
        snapped_val = None
        if snapped is not None:
            snapped_val = int(bool(snapped))

        cur.execute(
            """
            INSERT INTO actions (
                hand_id, idx, street, actor_seat, type, amount, bucket,
                to_call_after, pot_after, time_ms, rng_seed, snapped, meta,
                engine, evaluator, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                snapped_val,
                meta,
                engine or DEFAULT_ENGINE,
                evaluator or DEFAULT_EVALUATOR,
                datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
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
            """
            SELECT idx, street, actor_seat, type, amount, bucket,
                   to_call_after, pot_after, time_ms, rng_seed, snapped, meta,
                   engine, evaluator, created_at
            FROM actions
            WHERE hand_id = ?
            ORDER BY idx
            """,
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

    def fetch_session_actions(self, session_id: int) -> Iterable[sqlite3.Row]:
        """Yield all actions for all hands in a session, ordered by hand then idx."""
        cur = self.conn.cursor()
        for row in cur.execute(
            """
            SELECT a.hand_id, a.idx, a.street, a.actor_seat, a.type, a.amount, a.bucket,
                   a.to_call_after, a.pot_after, a.time_ms, a.rng_seed, a.snapped, a.meta,
                   a.engine, a.evaluator, a.created_at
            FROM actions a
            JOIN hands h ON h.hand_id = a.hand_id
            WHERE h.session_id = ?
            ORDER BY h.id, a.idx
            """,
            (session_id,),
        ):
            yield row

    def close(self) -> None:
        self.conn.close()
