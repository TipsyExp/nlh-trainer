# backend/coach/advice_store.py
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union


# Where to place the SQLite DB.
# Priority: COACH_DB_PATH > DB_PATH > default "data/app.sqlite3"
def _db_path() -> Path:
    for key in ("COACH_DB_PATH", "DB_PATH"):
        val = os.getenv(key)
        if val and val.strip():
            return Path(val).expanduser().resolve()
    return (Path("data") / "app.sqlite3").resolve()


def _ensure_dir(p: Path) -> None:
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    # Idempotent schema creation.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS coach_advice (
            hand_id    TEXT    NOT NULL,
            idx        INTEGER NOT NULL,
            node_key   TEXT,
            advice_json TEXT   NOT NULL,
            created_at TEXT    NOT NULL,
            PRIMARY KEY (hand_id, idx)
        );
        """
    )
    # Some reasonable defaults for durability/perf in a local app.
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")


def _connect() -> sqlite3.Connection:
    path = _db_path()
    _ensure_dir(path)
    conn = sqlite3.connect(str(path), timeout=30.0, check_same_thread=False)
    _ensure_schema(conn)
    return conn


def write_snapshot(
    hand_id: str,
    idx: int,
    node_key: Optional[str],
    advice_json: Union[str, dict[str, Any]],
) -> None:
    """
    Persist a single snapshot of advice for a decision.
    Upserts by (hand_id, idx).

    Parameters
    ----------
    hand_id : str
        The hand identifier.
    idx : int
        The decision index within the hand.
    node_key : Optional[str]
        Stable hash/key for this node (Task-18 will generate this). Can be None.
    advice_json : Union[str, dict[str, Any]]
        The advice payload to store. If a dict is provided, it will be JSON-encoded.
    """
    # Normalize payload to a compact JSON string.
    if isinstance(advice_json, str):
        payload = advice_json
    else:
        payload = json.dumps(advice_json, separators=(",", ":"), sort_keys=True)

    created_at = datetime.now(timezone.utc).isoformat()

    conn = _connect()
    try:
        # Use SQLite upsert (>= 3.24.0). Falls back gracefully on modern runners.
        conn.execute(
            """
            INSERT INTO coach_advice(hand_id, idx, node_key, advice_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(hand_id, idx) DO UPDATE SET
                node_key    = excluded.node_key,
                advice_json = excluded.advice_json,
                created_at  = excluded.created_at;
            """,
            (hand_id, idx, node_key, payload, created_at),
        )
        conn.commit()
    finally:
        conn.close()
