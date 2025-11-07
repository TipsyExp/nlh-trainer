from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from backend.logger import get_logger

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS solver_cache (
  node_key TEXT PRIMARY KEY,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


def ensure_tables(conn) -> None:
    """Ensure the solver_cache table exists."""
    cur = conn.cursor()
    cur.execute(_TABLE_SQL)
    conn.commit()


def _utcnow_iso() -> str:
    # ISO 8601 with explicit offset, second precision, stable for lexicographic ordering
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso_ts(s: str) -> datetime:
    """Parse ISO 8601 timestamps we write (with offset). Fallbacks are lenient."""
    try:
        dt = datetime.fromisoformat(s)
        # Ensure timezone-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        # Basic fallback for trailing 'Z'
        if s.endswith("Z"):
            try:
                return datetime.fromisoformat(s[:-1]).replace(tzinfo=timezone.utc)
            except Exception:
                pass
    # Last resort: treat as now to avoid negative durations
    return datetime.now(timezone.utc)


def _get_int_env(name: str, default: int) -> int:
    try:
        raw = os.environ.get(name)
        if raw is None or raw.strip() == "":
            return default
        return int(raw)
    except Exception:
        return default


class SolverCache:
    """SQLite-backed cache for solver advice with TTL & LRU controls.

    Uses the application logger's sqlite connection (get_logger().conn).
    """

    def __init__(self) -> None:
        self._logger = get_logger()
        # logger.conn is a sqlite3.Connection with row_factory that allows name-based access
        self._conn = self._logger.conn  # type: ignore[attr-defined]
        ensure_tables(self._conn)
        self._max_rows = _get_int_env("COACH_CACHE_MAX_ROWS", 5000)
        self._ttl_days = _get_int_env("COACH_CACHE_TTL_DAYS", 30)

    # --- Back-compat raw accessors (string payload) ---
    def get(self, node_key: str) -> Optional[str]:
        cur = self._conn.cursor()
        row = cur.execute(
            "SELECT payload_json FROM solver_cache WHERE node_key = ?",
            (node_key,),
        ).fetchone()
        return None if row is None else row["payload_json"]

    def set(self, node_key: str, payload_json: str) -> None:
        now = _utcnow_iso()
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO solver_cache (node_key, payload_json, created_at)
                 VALUES (?, ?, ?)
            ON CONFLICT(node_key) DO UPDATE SET
                 payload_json = excluded.payload_json,
                 created_at   = excluded.created_at
            """,
            (node_key, payload_json, now),
        )
        self._conn.commit()

    # --- Task-18 API (TTL-aware, dict payloads) ---
    def get_cached(self, node_key: str) -> Optional[dict]:
        """Return cached payload (dict) if present and not expired; else None."""
        cur = self._conn.cursor()
        row = cur.execute(
            "SELECT payload_json, created_at FROM solver_cache WHERE node_key = ?",
            (node_key,),
        ).fetchone()
        if row is None:
            self._log("miss", node_key)
            return None

        created_at = _parse_iso_ts(row["created_at"])  # type: ignore[index]
        if self._is_expired(created_at):
            self._log("expired", node_key)
            return None

        try:
            payload = json.loads(row["payload_json"])  # type: ignore[index]
        except Exception:
            # Treat corrupt row as a miss
            self._log("corrupt", node_key)
            return None

        self._log("hit", node_key)
        return payload

    def put_cached(self, node_key: str, payload: dict) -> None:
        payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        self.set(node_key, payload_json)
        self._log("put", node_key)

    def prune(self) -> int:
        """Enforce LRU by trimming oldest rows to keep table <= max_rows.
        Returns number of rows deleted.
        """
        cur = self._conn.cursor()
        row = cur.execute("SELECT COUNT(*) AS n FROM solver_cache").fetchone()
        total = int(row["n"]) if row is not None else 0  # type: ignore[index]
        if total <= self._max_rows:
            return 0
        to_delete = total - self._max_rows
        cur.execute(
            """
            DELETE FROM solver_cache
             WHERE node_key IN (
               SELECT node_key FROM solver_cache
                ORDER BY created_at ASC
                LIMIT ?
             )
            """,
            (to_delete,),
        )
        deleted = cur.rowcount or 0
        self._conn.commit()
        self._log(f"prune n={deleted}", None)
        return deleted

    # --- helpers ---
    def _is_expired(self, created_at: datetime) -> bool:
        ttl = timedelta(days=self._ttl_days)
        now = datetime.now(timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return (now - created_at) > ttl

    def _log(self, kind: str, node_key: Optional[str]) -> None:
        prefix = "coach_cache"
        msg = f"{prefix} {kind}"
        if node_key:
            msg += f" node_key={node_key[:12]}"
        logger = getattr(self, "_logger", None)
        if logger is not None and hasattr(logger, "info"):
            try:
                logger.info(msg)
                return
            except Exception:
                pass
        # Fallback
        print(msg)


# --- Optional module-level helpers for convenience ---
_CACHE_SINGLETON: Optional[SolverCache] = None


def _cache() -> SolverCache:
    global _CACHE_SINGLETON
    if _CACHE_SINGLETON is None:
        _CACHE_SINGLETON = SolverCache()
    return _CACHE_SINGLETON


def get_cached(node_key: str) -> Optional[dict]:
    return _cache().get_cached(node_key)


def put_cached(node_key: str, payload: dict) -> None:
    _cache().put_cached(node_key, payload)


def prune() -> int:
    return _cache().prune()
