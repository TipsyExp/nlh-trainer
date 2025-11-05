from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from backend.logger import get_logger

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS solver_cache (
  node_key TEXT PRIMARY KEY,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


class SolverCache:
    def __init__(self) -> None:
        self._conn = get_logger().conn  # type: ignore[attr-defined]
        cur = self._conn.cursor()
        cur.execute(_TABLE_SQL)
        self._conn.commit()

    def get(self, node_key: str) -> Optional[str]:
        cur = self._conn.cursor()
        row = cur.execute(
            "SELECT payload_json FROM solver_cache WHERE node_key = ?",
            (node_key,),
        ).fetchone()
        return None if row is None else row["payload_json"]

    def set(self, node_key: str, payload_json: str) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
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
