# backend/logger.py
"""
Simple singleton logger accessor for the NLH trainer.

This module wraps the :class:`SQLiteLogger` defined in ``backend.database``
and provides a process-wide singleton instance. The logger's database
path is configured via the ``LOG_DB_PATH`` environment variable. If
unset, a default path within the system temp directory is used.

Use ``get_logger()`` to obtain the logger rather than instantiating
``SQLiteLogger`` directly. Tests may call ``init_logger()`` to force
reinitialization with a specific path, or ``reset_logger()`` to close
and clear the current instance.

In addition to the bare logger, this module also exposes tiny helpers
for attaching JSON snapshots (equity / preflop advice) to the per-hand,
per-decision rows in the log database. These helpers are opt-in and
controlled via configuration flags in ``backend.config``.

A stub for unified coach advice snapshots (all streets, AdviceV1) is also
provided via ``log_coach_advice``. It currently behaves as a no-op; later
tasks will wire it to persist the full AdviceV1 payload, including HU and
multiway fields such as ``meta.n_players`` and ``equity.players``.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Mapping, Optional

from .config import (
    LOG_EQUITY_SNAPSHOT,
    LOG_EQUITY_SNAPSHOT_REDACT,
    LOG_PREFLOP_ADVICE,
)
from .database import SQLiteLogger

_LOGGER: Optional[SQLiteLogger] = None
_DB_PATH_CACHED: Optional[str] = None
_SNAPSHOT_TABLE_CACHED: Optional[str] = None  # table that holds hand_id/idx rows


def _default_db_path() -> str:
    # Cross-platform temp location (Windows/macOS/Linux)
    return os.path.join(tempfile.gettempdir(), "nlh_trainer.sqlite")


def _resolve_db_path(explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit
    return os.environ.get("LOG_DB_PATH", _default_db_path())


def _find_snapshot_table(conn: Any) -> Optional[str]:
    """
    Best-effort detection of the per-decision table used for snapshots.

    Heuristic:
      - Look for the first table that has both `hand_id` and `idx` columns.
      - Cache the result for subsequent calls.

    Returns:
        Table name if found, else None.
    """
    global _SNAPSHOT_TABLE_CACHED

    if _SNAPSHOT_TABLE_CACHED:
        return _SNAPSHOT_TABLE_CACHED

    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cur.fetchall()]
    except Exception:
        return None

    for tbl in tables:
        try:
            cur = conn.execute(f"PRAGMA table_info({tbl})")
            cols = [row[1] for row in cur.fetchall()]
        except Exception:
            continue
        if "hand_id" in cols and "idx" in cols:
            _SNAPSHOT_TABLE_CACHED = tbl
            return tbl

    return None


def _ensure_snapshot_columns(conn: Any) -> None:
    """
    Ensure the snapshot JSON columns exist on the per-decision table.

    This inspects the schema via PRAGMA and only adds columns if they
    are missing, avoiding the need for SQLite's newer IF NOT EXISTS
    variant of ALTER TABLE.

    This function is best-effort and will silently return on errors.
    """
    try:
        table = _find_snapshot_table(conn)
        if not table:
            return

        cur = conn.execute(f"PRAGMA table_info({table})")
        cols = [row[1] for row in cur.fetchall()]

        want_cols = ["equity_snapshot_json", "preflop_advice_json"]
        for col in want_cols:
            if col not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")

        conn.commit()
    except Exception:
        # Logging must never break the main application flow.
        return


def _redact_equity_snapshot(snapshot: Mapping[str, Any], redact: bool) -> dict:
    """
    Optionally redact sensitive parts of an equity snapshot before storage.

    This is intentionally coarse-grained: it removes or anonymises fields
    that are likely to contain raw cards/ranges while preserving useful
    metadata for debugging.

    If `redact` is False, the snapshot is returned as-is (copied to a dict).
    """
    data: dict[str, Any] = dict(snapshot)
    if not redact:
        return data

    # Commonly sensitive fields; keep minimal information.
    if "players" in data and isinstance(data["players"], list):
        players = data["players"]
        redacted_players: list[Any] = []
        for p in players:
            if isinstance(p, dict):
                # Keep seat / index if present, drop detailed range/hand info.
                minimal: dict[str, Any] = {}
                if "seat" in p:
                    minimal["seat"] = p["seat"]
                minimal["redacted"] = True
                redacted_players.append(minimal)
            else:
                redacted_players.append({"redacted": True})
        data["players"] = redacted_players

    for key in ("board", "dead", "hero_hand", "villain_range", "inputs"):
        if key in data:
            data[key] = "redacted"

    return data


def get_logger() -> SQLiteLogger:
    """Return a singleton instance of :class:`SQLiteLogger`.

    The database file used by the logger is determined by the
    ``LOG_DB_PATH`` environment variable (or a default in the system temp
    directory). If the env var changes mid-process (common during tests),
    this accessor will reinitialize the logger to point at the new path.
    """
    global _LOGGER, _DB_PATH_CACHED
    path = _resolve_db_path()
    if _LOGGER is None:
        _LOGGER = SQLiteLogger(path)
        _DB_PATH_CACHED = path
        # Best-effort migration of snapshot columns (no-op on failure).
        try:
            conn = getattr(_LOGGER, "conn", None)
            if conn is not None:
                _ensure_snapshot_columns(conn)
        except Exception:
            pass
        return _LOGGER

    # If the env path changed since the last call, reinitialize.
    if _DB_PATH_CACHED != path:
        try:
            _LOGGER.close()
        except Exception:
            pass
        _LOGGER = SQLiteLogger(path)
        _DB_PATH_CACHED = path
        try:
            conn = getattr(_LOGGER, "conn", None)
            if conn is not None:
                _ensure_snapshot_columns(conn)
        except Exception:
            pass

    return _LOGGER


def init_logger(db_path: Optional[str] = None) -> SQLiteLogger:
    """Force (re)create the singleton logger with the given path.

    Useful for tests or scripts that need an isolated database, independent
    of the current LOG_DB_PATH environment variable.
    """
    global _LOGGER, _DB_PATH_CACHED, _SNAPSHOT_TABLE_CACHED
    if _LOGGER is not None:
        try:
            _LOGGER.close()
        except Exception:
            pass
    resolved = _resolve_db_path(db_path)
    _LOGGER = SQLiteLogger(resolved)
    _DB_PATH_CACHED = resolved
    _SNAPSHOT_TABLE_CACHED = None
    try:
        conn = getattr(_LOGGER, "conn", None)
        if conn is not None:
            _ensure_snapshot_columns(conn)
    except Exception:
        pass
    return _LOGGER


def reset_logger() -> None:
    """Close and clear the current singleton logger (for tests)."""
    global _LOGGER, _DB_PATH_CACHED, _SNAPSHOT_TABLE_CACHED
    if _LOGGER is not None:
        try:
            _LOGGER.close()
        finally:
            _LOGGER = None
            _DB_PATH_CACHED = None
            _SNAPSHOT_TABLE_CACHED = None


def log_equity_snapshot(
    hand_id: str,
    idx: int,
    snapshot: Mapping[str, Any],
) -> None:
    """
    Attach an equity snapshot JSON blob to the per-decision log row.

    Behaviour:
      - No-op unless LOG_EQUITY_SNAPSHOT is true.
      - Best-effort: any errors (missing tables, schema mismatch, etc.)
        are swallowed.
      - When LOG_EQUITY_SNAPSHOT_REDACT is true, a redacted view of the
        snapshot is stored instead of the raw payload.
    """
    if not LOG_EQUITY_SNAPSHOT:
        return

    try:
        logger = get_logger()
        conn = getattr(logger, "conn", None)
        if conn is None:
            return

        _ensure_snapshot_columns(conn)
        table = _find_snapshot_table(conn)
        if not table:
            return

        payload_obj = _redact_equity_snapshot(snapshot, LOG_EQUITY_SNAPSHOT_REDACT)
        payload = json.dumps(payload_obj, separators=(",", ":"), sort_keys=True)

        conn.execute(
            f"UPDATE {table} "
            "SET equity_snapshot_json = ? "
            "WHERE hand_id = ? AND idx = ?",
            (payload, hand_id, idx),
        )
        conn.commit()
    except Exception:
        # Logging must never affect primary control flow.
        return


def log_preflop_advice(
    hand_id: str,
    idx: int,
    advice: Mapping[str, Any],
) -> None:
    """
    Attach a preflop advice JSON blob to the per-decision log row.

    Behaviour:
      - No-op unless LOG_PREFLOP_ADVICE is true.
      - Best-effort: any errors are swallowed.
    """
    if not LOG_PREFLOP_ADVICE:
        return

    try:
        logger = get_logger()
        conn = getattr(logger, "conn", None)
        if conn is None:
            return

        _ensure_snapshot_columns(conn)
        table = _find_snapshot_table(conn)
        if not table:
            return

        payload = json.dumps(dict(advice), separators=(",", ":"), sort_keys=True)
        conn.execute(
            f"UPDATE {table} "
            "SET preflop_advice_json = ? "
            "WHERE hand_id = ? AND idx = ?",
            (payload, hand_id, idx),
        )
        conn.commit()
    except Exception:
        return


def log_coach_advice(
    hand_id: str,
    idx: int,
    advice: Mapping[str, Any],
) -> None:
    """
    Placeholder hook for logging unified coach advice (AdviceV1).

    The ``advice`` mapping is expected to be a serialized AdviceV1 payload,
    which naturally supports both heads-up and multiway decisions via:

      * ``meta.n_players`` – number of active players in the pot.
      * ``equity.players`` – optional per-seat equity records.
      * ``equity.vs_field`` – optional hero-vs-field aggregate.

    Task 3–4 introduce the postflop coach and multiway-aware advice. Actual
    persistence of this blob into the log database (including schema changes
    and a dedicated LOG_COACH_ADVICE flag) is deferred to a later task.

    Callers may safely invoke this function; it is currently a no-op.
    """
    # Intentional no-op until coach_advice logging is implemented in Task 6.
    return


__all__ = [
    "get_logger",
    "init_logger",
    "reset_logger",
    "log_equity_snapshot",
    "log_preflop_advice",
    "log_coach_advice",
]
