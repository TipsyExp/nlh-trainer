# backend/review/store.py
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from backend.logger import get_logger


# -----------------------
# Internal helpers
# -----------------------


def _conn():
    # Uses the shared sqlite connection with row_factory set in logger
    return get_logger().conn  # type: ignore[attr-defined]


def _table_exists(table: str) -> bool:
    conn = _conn()
    cur = conn.cursor()
    row = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _columns(table: str) -> List[str]:
    conn = _conn()
    if not _table_exists(table):
        return []
    cur = conn.cursor()
    rows = cur.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(r["name"]) for r in rows]  # type: ignore[index]


def _has_col(table: str, col: str) -> bool:
    return col in _columns(table)


def _rows_to_dicts(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return [dict(r) for r in rows]


def _first_present(table: str, *candidates: str) -> Optional[str]:
    cols = set(_columns(table))
    for c in candidates:
        if c in cols:
            return c
    return None


def _actions_schema() -> Dict[str, Optional[str]]:
    """
    Detect the concrete column names used by the actions table and
    return a mapping for logical fields -> concrete column name (or None).
    """
    table = "actions"
    return {
        "idx": _first_present(table, "idx"),
        "created_at": _first_present(table, "created_at"),
        "street": _first_present(table, "street"),
        "actor": _first_present(table, "actor_seat", "actor"),
        "action": _first_present(table, "type", "action"),
        "amount": _first_present(table, "amount"),
        "pot_after": _first_present(table, "pot_after"),
        "stack_after": _first_present(table, "stack_after"),
        "bucket": _first_present(table, "bucket"),
        "snapped": _first_present(table, "snapped"),
        "rng": _first_present(table, "rng_seed", "rng"),
        "engine": _first_present(table, "engine"),
        "evaluator": _first_present(table, "evaluator"),
    }


# -----------------------
# Public: listing & summary
# -----------------------


def list_recent_hands(
    limit: int = 100,
    offset: int = 0,
    order: str = "desc",
) -> List[Dict[str, Any]]:
    """
    Return recent hands derived from the `actions` table.
    Best-effort fields: hand_id, started_at, finished_at, num_actions, seats, final_pot, winners, has_advice.
    If tables/columns are missing, fields may be None / defaults.

    NOTE: This function is read-only and performs no migrations.
    """
    if not _table_exists("actions"):
        return []

    schema = _actions_schema()
    has_created = schema["created_at"] is not None
    has_actor = schema["actor"] is not None
    has_pot_after = schema["pot_after"] is not None

    # Build aggregate query dynamically based on available columns.
    select_parts = ["hand_id", "COUNT(*) AS num_actions"]
    order_key = "num_actions"

    if has_created:
        select_parts.append("MIN(created_at) AS started_at")
        select_parts.append("MAX(created_at) AS finished_at")
        order_key = "finished_at"

    if has_actor:
        select_parts.append(f"COUNT(DISTINCT {schema['actor']}) AS seats")  # type: ignore[index]

    if has_pot_after:
        select_parts.append("MAX(pot_after) AS final_pot")

    sel = ", ".join(select_parts)
    ord_dir = "ASC" if str(order).lower() == "asc" else "DESC"

    conn = _conn()
    cur = conn.cursor()
    rows = cur.execute(
        f"""
        SELECT {sel}
          FROM actions
         GROUP BY hand_id
         ORDER BY {order_key} {ord_dir}
         LIMIT ? OFFSET ?
        """,
        (max(0, int(limit)), max(0, int(offset))),
    ).fetchall()

    items = _rows_to_dicts(rows)

    # winners: best-effort — look for rows whose action indicates a collect/win
    winners: Dict[str, List[str]] = {}
    action_col = schema["action"]
    actor_col = schema["actor"]
    if action_col and actor_col:
        wrows = cur.execute(
            f"""
            SELECT hand_id, DISTINCT {actor_col} AS actor
              FROM actions
             WHERE {action_col} IN ('win','collect')
            """.replace(
                "DISTINCT", "DISTINCT"
            ),  # keep DISTINCT in proper place
        ).fetchall()
        for r in wrows:
            hid = str(r["hand_id"])  # type: ignore[index]
            winners.setdefault(hid, []).append(str(r["actor"]))  # type: ignore[index]

    # has_advice: mark if any snapshot exists for the hand (if advice table present)
    advice_hands: set[str] = set()
    if _table_exists("coach_advice"):
        arows = cur.execute("SELECT DISTINCT hand_id FROM coach_advice").fetchall()
        advice_hands = {str(r["hand_id"]) for r in arows}  # type: ignore[index]

    # attach winners/has_advice
    for it in items:
        hid = str(it.get("hand_id"))
        it["winners"] = winners.get(hid, [])
        it["has_advice"] = hid in advice_hands

    return items


def get_hand_summary(hand_id: str) -> Dict[str, Any]:
    """
    Return a single-hand summary derived from `actions`. Missing fields may be None/defaults.
    """
    if not _table_exists("actions"):
        return {
            "hand_id": hand_id,
            "started_at": None,
            "finished_at": None,
            "seats": None,
            "final_pot": None,
            "winners": [],
            "num_actions": 0,
        }

    schema = _actions_schema()
    has_created = schema["created_at"] is not None
    has_actor = schema["actor"] is not None
    has_pot_after = schema["pot_after"] is not None

    select_parts = ["COUNT(*) AS num_actions"]
    if has_created:
        select_parts.append("MIN(created_at) AS started_at")
        select_parts.append("MAX(created_at) AS finished_at")
    if has_actor:
        select_parts.append(f"COUNT(DISTINCT {schema['actor']}) AS seats")  # type: ignore[index]
    if has_pot_after:
        select_parts.append("MAX(pot_after) AS final_pot")

    sel = ", ".join(select_parts)

    conn = _conn()
    cur = conn.cursor()
    row = cur.execute(
        f"""
        SELECT {sel}
          FROM actions
         WHERE hand_id = ?
        """,
        (hand_id,),
    ).fetchone()

    num_actions = int(row["num_actions"]) if row and row["num_actions"] is not None else 0  # type: ignore[index]

    # winners best-effort
    winners: List[str] = []
    action_col = schema["action"]
    actor_col = schema["actor"]
    if action_col and actor_col:
        wrows = cur.execute(
            f"""
            SELECT DISTINCT {actor_col} AS actor
              FROM actions
             WHERE hand_id = ?
               AND {action_col} IN ('win','collect')
            """,
            (hand_id,),
        ).fetchall()
        winners = [str(r["actor"]) for r in wrows]  # type: ignore[index]

    return {
        "hand_id": hand_id,
        "started_at": row["started_at"] if row and "started_at" in row.keys() else None,  # type: ignore[attr-defined]
        "finished_at": row["finished_at"] if row and "finished_at" in row.keys() else None,  # type: ignore[attr-defined]
        "seats": int(row["seats"]) if row and "seats" in row.keys() and row["seats"] is not None else None,  # type: ignore[attr-defined]
        "final_pot": row["final_pot"] if row and "final_pot" in row.keys() else None,  # type: ignore[attr-defined]
        "winners": winners,
        "num_actions": num_actions,
    }


# -----------------------
# Public: hand details
# -----------------------

# We normalize output keys for callers, regardless of DB column names.
_NORMALIZED_ACTION_KEYS: Tuple[str, ...] = (
    "idx",
    "street",
    "actor",
    "action",
    "amount",
    "pot_after",
    "stack_after",
    "bucket",
    "snapped",
    "rng",
    "engine",
    "evaluator",
    "created_at",
)


def get_hand_actions(hand_id: str) -> List[Dict[str, Any]]:
    """
    Return ordered actions for a hand. Emits normalized keys even if the
    underlying DB uses different column names (e.g., actor_seat/type/rng_seed).
    Missing keys become None.
    """
    if not _table_exists("actions"):
        return []

    schema = _actions_schema()

    # Prefer idx ordering; fallback to created_at if idx column absent.
    has_idx = schema["idx"] is not None
    has_created = schema["created_at"] is not None

    order_clause = f"ORDER BY {schema['idx']} ASC" if has_idx else ""
    if not has_idx and has_created:
        order_clause = f"ORDER BY {schema['created_at']} ASC"

    conn = _conn()
    cur = conn.cursor()
    rows = cur.execute(
        f"SELECT * FROM actions WHERE hand_id = ? {order_clause}",
        (hand_id,),
    ).fetchall()

    # Map rows to a stable shape (normalized keys; None if missing)
    result: List[Dict[str, Any]] = []
    available_cols = set(_columns("actions"))

    # Build a map from normalized -> concrete column name
    col_map = {
        "idx": schema["idx"],
        "street": schema["street"],
        "actor": schema["actor"],
        "action": schema["action"],
        "amount": schema["amount"],
        "pot_after": schema["pot_after"],
        "stack_after": schema["stack_after"],
        "bucket": schema["bucket"],
        "snapped": schema["snapped"],
        "rng": schema["rng"],
        "engine": schema["engine"],
        "evaluator": schema["evaluator"],
        "created_at": schema["created_at"],
    }

    for r in rows:
        d = dict(r)
        item: Dict[str, Any] = {"hand_id": hand_id}
        for norm_key in _NORMALIZED_ACTION_KEYS:
            concrete = col_map.get(norm_key)
            if concrete and concrete in available_cols:
                item[norm_key] = d.get(concrete)
            else:
                item[norm_key] = None
        result.append(item)

    return result


# -----------------------
# Public: advice snapshots
# -----------------------


def get_advice_by_hand(hand_id: str) -> Dict[int, Dict[str, Any]]:
    """
    Return all advice snapshots for a hand, indexed by idx.
    Shape:
      { idx: { "node_key": str, "advice_json": dict, "created_at": str | None } }
    If `coach_advice` table doesn't exist, returns {}.
    """
    if not _table_exists("coach_advice"):
        return {}

    conn = _conn()
    cur = conn.cursor()

    # Detect columns (created_at may or may not exist)
    cols = set(_columns("coach_advice"))
    has_created = "created_at" in cols

    sel = "hand_id, idx, node_key, advice_json"
    if has_created:
        sel += ", created_at"

    rows = cur.execute(
        f"""
        SELECT {sel}
          FROM coach_advice
         WHERE hand_id = ?
        """,
        (hand_id,),
    ).fetchall()

    out: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        idx = int(r["idx"])  # type: ignore[index]
        out[idx] = {
            "node_key": r["node_key"],  # type: ignore[index]
            "advice_json": r["advice_json"],  # type: ignore[index]
            "created_at": r["created_at"] if has_created else None,  # type: ignore[index]
        }
    return out


def get_advice_snapshot(hand_id: str, idx: int) -> Optional[Dict[str, Any]]:
    """
    Return a single advice snapshot for (hand_id, idx), or None.
    """
    if not _table_exists("coach_advice"):
        return None

    conn = _conn()
    cur = conn.cursor()
    cols = set(_columns("coach_advice"))
    has_created = "created_at" in cols

    sel = "hand_id, idx, node_key, advice_json"
    if has_created:
        sel += ", created_at"

    row = cur.execute(
        f"""
        SELECT {sel}
          FROM coach_advice
         WHERE hand_id = ? AND idx = ?
         LIMIT 1
        """,
        (hand_id, idx),
    ).fetchone()

    if row is None:
        return None

    return {
        "node_key": row["node_key"],  # type: ignore[index]
        "advice_json": row["advice_json"],  # type: ignore[index]
        "created_at": row["created_at"] if has_created else None,  # type: ignore[index]
    }
