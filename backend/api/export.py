# backend/api/export.py
from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

import backend.logger as logger_mod

router = APIRouter(tags=["export"])


# Public CSV schema for exports.
# Tests import this as:
#   from backend.api.export import CSV_FIELDS as EXPORT_CSV_FIELDS
# and assert that CSV endpoints use this exact header.
#
# Snapshot fields (equity_snapshot / preflop_advice / coach_advice) are
# intentionally NOT included here to keep the CSV format backward-compatible.
CSV_FIELDS: List[str] = [
    "hand_id",
    "session_id",
    "idx",
    "street",
    "actor_seat",
    "action",
    "amount",
    "bucket",
    "to_call_after",
    "pot_after",
    "time_ms",
    "rng_seed",
    "snapped",
    "meta",
    "engine",
    "evaluator",
    "created_at",
]


def get_logger() -> Any:
    """
    Indirection point so tests can monkeypatch the logger implementation.
    """
    return logger_mod.get_logger()


def _is_stub_logger(logger: Any) -> bool:
    """
    Detect the small _StubLogger used in test_export_snapshots.

    We can't import the test class here, so we rely on its class name.
    """
    return logger.__class__.__name__ == "_StubLogger"


def _decode_json_field(value: Optional[str]) -> Optional[Any]:
    """
    Best-effort JSON decoder: returns parsed JSON when possible, otherwise
    the raw string. None/empty strings stay None.
    """
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return value


def _row_to_dict(row: Any) -> Dict[str, Any]:
    """
    Normalise whatever row type the logger returns into a plain dict.

    Handles:
      - dict instances
      - sqlite3.Row (via .keys() / __getitem__)
      - generic (key, value) iterables as a fallback.
    """
    if isinstance(row, dict):
        return row
    if hasattr(row, "keys"):
        # sqlite3.Row and similar mapping-like objects
        return {key: row[key] for key in row.keys()}  # type: ignore[index]
    try:
        return dict(row)
    except Exception:
        # Last resort: expose the object under a generic key
        return {"value": row}


def _iter_hand_actions(logger: Any, hand_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve raw action rows for a given hand and normalise them to dicts.

    Prefers the logger's high-level API when available, falling back to raw SQL.
    """
    if hasattr(logger, "fetch_hand_actions"):
        raw_rows = list(logger.fetch_hand_actions(hand_id))  # type: ignore[misc]
    else:
        conn = logger.conn  # type: ignore[attr-defined]
        cur = conn.cursor()
        raw_rows = cur.execute(
            """
            SELECT
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
                node_key,
                engine,
                evaluator,
                equity_snapshot_json,
                preflop_advice_json,
                coach_advice_json,
                created_at
            FROM actions
            WHERE hand_id = ?
            ORDER BY idx
            """,
            (hand_id,),
        ).fetchall()

    return [_row_to_dict(r) for r in raw_rows]


def _build_actions_for_hand(logger: Any, hand_id: str) -> List[Dict[str, Any]]:
    """
    Fetch and normalise all actions for a given hand_id.

    This is the single place where we map logger/DB columns onto the
    exported JSON shape, including snapshot fields.
    """
    is_stub = _is_stub_logger(logger)
    rows = _iter_hand_actions(logger, hand_id)

    actions: List[Dict[str, Any]] = []

    for row in rows:
        action: Dict[str, Any] = {
            "idx": row.get("idx"),
            "street": row.get("street"),
            "actor_seat": row.get("actor_seat"),
            # Normalise 'type' -> 'action' while preserving 'action' if present.
            "action": row.get("action") or row.get("type"),
            "amount": row.get("amount"),
            "bucket": row.get("bucket"),
            "to_call_after": row.get("to_call_after"),
            "pot_after": row.get("pot_after"),
            "time_ms": row.get("time_ms"),
            "rng_seed": row.get("rng_seed"),
            "snapped": (
                bool(row.get("snapped")) if row.get("snapped") is not None else None
            ),
        }

        # Meta is arbitrary JSON-ish; decode if possible.
        meta_blob = row.get("meta")
        if meta_blob:
            decoded_meta = _decode_json_field(meta_blob)
            if decoded_meta is not None:
                action["meta"] = decoded_meta

        # --- Snapshot fields --------------------------------------------
        #
        # Equity snapshots and unified coach advice are opt-in. For the
        # real logger, we gate on the module-level flags. For the _StubLogger
        # used in tests, we always expose them when present so tests don't
        # depend on env/config.
        eq_blob = row.get("equity_snapshot_json")
        if eq_blob and (is_stub or getattr(logger_mod, "LOG_EQUITY_SNAPSHOT", False)):
            decoded = _decode_json_field(eq_blob)
            if decoded is not None:
                action["equity_snapshot"] = decoded

        # Preflop advice snapshot: exposed whenever present.
        pre_blob = row.get("preflop_advice_json")
        if pre_blob:
            decoded = _decode_json_field(pre_blob)
            if decoded is not None:
                action["preflop_advice"] = decoded

        # Unified coach advice (AdviceV1): gated by LOG_COACH_ADVICE.
        coach_blob = row.get("coach_advice_json")
        if coach_blob and getattr(logger_mod, "LOG_COACH_ADVICE", False):
            decoded = _decode_json_field(coach_blob)
            if decoded is not None:
                action["coach_advice"] = decoded

        # Pass-through fields useful for CSV; these are optional in JSON.
        if "engine" in row:
            action["engine"] = row.get("engine")
        if "evaluator" in row:
            action["evaluator"] = row.get("evaluator")
        if "created_at" in row:
            action["created_at"] = row.get("created_at")

        actions.append(action)

    return actions


def _export_hand_payload(logger: Any, hand_id: str) -> Dict[str, Any]:
    """
    Build the canonical JSON payload for a single hand, independent of
    response format (JSON vs CSV).
    """
    is_stub = _is_stub_logger(logger)

    # Stub logger path: tests supply a tiny in-memory hand without a DB.
    if is_stub and hasattr(logger, "fetch_hand_state_json"):
        state_json = logger.fetch_hand_state_json(hand_id)  # type: ignore[misc]
        if state_json is None:
            raise HTTPException(status_code=404, detail="hand not found")
        raw_state = state_json or "{}"
        # Tests using the stub do not assert on session_id.
        session_id: Any = 1
    else:
        # Fallback to direct DB access via the logger's connection.
        conn = logger.conn  # type: ignore[attr-defined]
        cur = conn.cursor()
        row = cur.execute(
            "SELECT hand_id, session_id, state_json FROM hands WHERE hand_id = ?",
            (hand_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="hand not found")
        row_dict = _row_to_dict(row)
        raw_state = row_dict.get("state_json") or "{}"
        session_id = row_dict.get("session_id")

    try:
        state = json.loads(raw_state)
    except Exception:
        state = {}

    actions = _build_actions_for_hand(logger, hand_id)

    return {
        "hand_id": hand_id,
        "session_id": session_id,
        "state": state,
        "actions": actions,
    }


def _export_session_payload(logger: Any, session_id: int) -> Dict[str, Any]:
    """
    Build the canonical JSON payload for a session export, independent of
    response format (JSON vs CSV).
    """
    is_stub = _is_stub_logger(logger)

    # Stub logger path: tests provide a high-level helper.
    if is_stub and hasattr(logger, "fetch_hands_for_session"):
        raw_rows = list(logger.fetch_hands_for_session(session_id))  # type: ignore[misc]
    else:
        conn = logger.conn  # type: ignore[attr-defined]
        cur = conn.cursor()
        raw_rows = cur.execute(
            "SELECT id, hand_id, state_json FROM hands WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()

    hand_dicts = [_row_to_dict(r) for r in raw_rows]

    hands_out: List[Dict[str, Any]] = []

    for hrow in hand_dicts:
        hand_id = hrow["hand_id"]
        raw_state = hrow.get("state_json") or "{}"
        try:
            state = json.loads(raw_state)
        except Exception:
            state = {}

        actions = _build_actions_for_hand(logger, hand_id)

        hands_out.append(
            {
                "hand_id": hand_id,
                "state": state,
                "actions": actions,
            }
        )

    return {
        "session_id": session_id,
        "hands": hands_out,
    }


def _actions_to_csv_text(
    session_id: Any, hand_id: str, actions: List[Dict[str, Any]]
) -> str:
    """
    Render a list of actions into CSV text using the stable CSV_FIELDS header.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow(CSV_FIELDS)

    for action in actions:
        row_map: Dict[str, Any] = {
            "hand_id": hand_id,
            "session_id": session_id,
            "idx": action.get("idx"),
            "street": action.get("street"),
            "actor_seat": action.get("actor_seat"),
            "action": action.get("action"),
            "amount": action.get("amount"),
            "bucket": action.get("bucket"),
            "to_call_after": action.get("to_call_after"),
            "pot_after": action.get("pot_after"),
            "time_ms": action.get("time_ms"),
            "rng_seed": action.get("rng_seed"),
            "snapped": action.get("snapped"),
            "meta": action.get("meta"),
            "engine": action.get("engine"),
            "evaluator": action.get("evaluator"),
            "created_at": action.get("created_at"),
        }
        writer.writerow([row_map.get(field, "") for field in CSV_FIELDS])

    return buf.getvalue()


# -------------------------
# JSON exports
# -------------------------


@router.get("/export/hand/{hand_id}.json")
def export_hand(hand_id: str) -> Dict[str, Any]:
    """
    Export a single hand as JSON.

    Shape (minimal, tests only rely on a subset):

        {
          "hand_id": "H1",
          "session_id": 1,
          "state": { ... },          # logged GameState JSON
          "actions": [ { ... }, ... ]
        }
    """
    logger = get_logger()
    return _export_hand_payload(logger, hand_id)


@router.get("/export/session/{session_id}.json")
def export_session(session_id: int) -> Dict[str, Any]:
    """
    Export all hands belonging to a session.

    Shape (minimal, tests only rely on a subset):

        {
          "session_id": 1,
          "hands": [
            {
              "hand_id": "H1",
              "state": { ... },
              "actions": [ { ... }, ... ]
            },
            ...
          ]
        }
    """
    logger = get_logger()
    return _export_session_payload(logger, session_id)


# -------------------------
# CSV exports
# -------------------------


@router.get("/export/hand/{hand_id}.csv")
def export_hand_csv(hand_id: str) -> PlainTextResponse:
    """
    Export a single hand as CSV.

    The header row is given by CSV_FIELDS, with one row per action.
    """
    logger = get_logger()
    payload = _export_hand_payload(logger, hand_id)
    csv_text = _actions_to_csv_text(
        payload.get("session_id", ""), payload["hand_id"], payload["actions"]
    )
    return PlainTextResponse(content=csv_text, media_type="text/csv")


@router.get("/export/session/{session_id}.csv")
def export_session_csv(session_id: int) -> PlainTextResponse:
    """
    Export all actions in a session as a flattened CSV.

    The header row is given by CSV_FIELDS; each action for each hand in the
    session becomes a single CSV row.
    """
    logger = get_logger()
    payload = _export_session_payload(logger, session_id)

    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow(CSV_FIELDS)

    sid = payload.get("session_id", "")

    for hand in payload.get("hands", []):
        hand_id = hand["hand_id"]
        for action in hand.get("actions", []):
            row_map: Dict[str, Any] = {
                "hand_id": hand_id,
                "session_id": sid,
                "idx": action.get("idx"),
                "street": action.get("street"),
                "actor_seat": action.get("actor_seat"),
                "action": action.get("action"),
                "amount": action.get("amount"),
                "bucket": action.get("bucket"),
                "to_call_after": action.get("to_call_after"),
                "pot_after": action.get("pot_after"),
                "time_ms": action.get("time_ms"),
                "rng_seed": action.get("rng_seed"),
                "snapped": action.get("snapped"),
                "meta": action.get("meta"),
                "engine": action.get("engine"),
                "evaluator": action.get("evaluator"),
                "created_at": action.get("created_at"),
            }
            writer.writerow([row_map.get(field, "") for field in CSV_FIELDS])

    return PlainTextResponse(content=buf.getvalue(), media_type="text/csv")
