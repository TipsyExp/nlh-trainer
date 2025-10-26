"""Export API for the NLH trainer."""
from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict, Iterable, List

from fastapi import APIRouter, HTTPException, Response

from backend.logger import get_logger

router = APIRouter(tags=["export"])

# Stable header order for CSV outputs (contract)
CSV_FIELDS: List[str] = [
    "hand_id",
    "idx",
    "street",
    "actor_seat",
    "action",       # NOTE: mapped from DB column 'type'
    "amount",
    "bucket",
    "to_call_after",
    "pot_after",
    "time_ms",
    "rng_seed",
    "snapped",      # bool-ish (0/1) or empty
    "meta",         # raw string (JSON-encoded if present)
    "engine",
    "evaluator",
    "created_at",
]


def _bool_from_db(v: Any) -> Any:
    if v is None:
        return None
    # Normalize common sqlite row representations to Python bools
    if isinstance(v, bool):
        return v
    if isinstance(v, (int,)):
        return bool(v)
    s = str(v)
    if s.isdigit():
        return bool(int(s))
    # Fallback
    return bool(v)


def _row_get(row: Any, key: str) -> Any:
    """Safe getter for sqlite Row; returns None if column is missing."""
    if hasattr(row, "keys"):
        try:
            if key in row.keys():  # type: ignore[attr-defined]
                return row[key]
        except Exception:
            pass
    try:
        return row[key]  # might still work if row is a dict-like
    except Exception:
        return None


def _actions_to_dicts(rows: Iterable[Any], include_hand_id: str | None = None) -> List[Dict[str, Any]]:
    """Convert action rows into JSON-serialisable dicts with contract field names."""
    out: List[Dict[str, Any]] = []
    for r in rows:
        item = {
            "idx": _row_get(r, "idx"),
            "street": _row_get(r, "street"),
            "actor_seat": _row_get(r, "actor_seat"),
            "action": _row_get(r, "type"),  # rename from DB "type" -> contract "action"
            "amount": _row_get(r, "amount"),
            "bucket": _row_get(r, "bucket"),
            "to_call_after": _row_get(r, "to_call_after"),
            "pot_after": _row_get(r, "pot_after"),
            "time_ms": _row_get(r, "time_ms"),
            "rng_seed": _row_get(r, "rng_seed"),
            "snapped": _bool_from_db(_row_get(r, "snapped")),
            "meta": _row_get(r, "meta"),
            "engine": _row_get(r, "engine"),
            "evaluator": _row_get(r, "evaluator"),
            "created_at": _row_get(r, "created_at"),
        }
        if include_hand_id is not None:
            item = {"hand_id": include_hand_id, **item}
        out.append(item)
    return out


@router.get("/export/hand/{hand_id}.json")
def export_hand_json(hand_id: str) -> Dict[str, Any]:
    logger = get_logger()
    state_json = logger.fetch_hand_state_json(hand_id)
    if state_json is None:
        raise HTTPException(status_code=404, detail="hand not found")
    actions = _actions_to_dicts(logger.fetch_hand_actions(hand_id))
    return {"hand_id": hand_id, "state": json.loads(state_json), "actions": actions}


@router.get("/export/hand/{hand_id}.csv")
def export_hand_csv(hand_id: str) -> Response:
    logger = get_logger()
    state_json = logger.fetch_hand_state_json(hand_id)
    if state_json is None:
        raise HTTPException(status_code=404, detail="hand not found")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_FIELDS)

    for r in logger.fetch_hand_actions(hand_id):
        row = {
            "hand_id": hand_id,
            "idx": _row_get(r, "idx"),
            "street": _row_get(r, "street"),
            "actor_seat": _row_get(r, "actor_seat"),
            "action": _row_get(r, "type"),  # CSV column is "action"
            "amount": _row_get(r, "amount"),
            "bucket": _row_get(r, "bucket"),
            "to_call_after": _row_get(r, "to_call_after"),
            "pot_after": _row_get(r, "pot_after"),
            "time_ms": _row_get(r, "time_ms"),
            "rng_seed": _row_get(r, "rng_seed"),
            "snapped": "" if _row_get(r, "snapped") is None else int(bool(_row_get(r, "snapped"))),
            "meta": "" if _row_get(r, "meta") is None else _row_get(r, "meta"),
            "engine": _row_get(r, "engine"),
            "evaluator": _row_get(r, "evaluator"),
            "created_at": _row_get(r, "created_at"),
        }
        writer.writerow([row.get(k, "") if row.get(k, "") is not None else "" for k in CSV_FIELDS])

    return Response(content=buf.getvalue(), media_type="text/csv")


@router.get("/export/session/{session_id}.json")
def export_session_json(session_id: int) -> Dict[str, Any]:
    logger = get_logger()
    hands = list(logger.fetch_hands_for_session(session_id))
    if not hands:
        raise HTTPException(status_code=404, detail="session not found or empty")

    out: List[Dict[str, Any]] = []
    for row in hands:
        hand_id = row["hand_id"]
        state_json = row["state_json"]
        actions = _actions_to_dicts(logger.fetch_hand_actions(hand_id))
        out.append({"hand_id": hand_id, "state": json.loads(state_json), "actions": actions})

    return {"session_id": session_id, "hands": out}


@router.get("/export/session/{session_id}.csv")
def export_session_csv(session_id: int) -> Response:
    logger = get_logger()
    hands = list(logger.fetch_hands_for_session(session_id))
    if not hands:
        raise HTTPException(status_code=404, detail="session not found or empty")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_FIELDS)

    for hand in hands:
        hand_id = hand["hand_id"]
        for r in logger.fetch_hand_actions(hand_id):
            row = {
                "hand_id": hand_id,
                "idx": _row_get(r, "idx"),
                "street": _row_get(r, "street"),
                "actor_seat": _row_get(r, "actor_seat"),
                "action": _row_get(r, "type"),
                "amount": _row_get(r, "amount"),
                "bucket": _row_get(r, "bucket"),
                "to_call_after": _row_get(r, "to_call_after"),
                "pot_after": _row_get(r, "pot_after"),
                "time_ms": _row_get(r, "time_ms"),
                "rng_seed": _row_get(r, "rng_seed"),
                "snapped": "" if _row_get(r, "snapped") is None else int(bool(_row_get(r, "snapped"))),
                "meta": "" if _row_get(r, "meta") is None else _row_get(r, "meta"),
                "engine": _row_get(r, "engine"),
                "evaluator": _row_get(r, "evaluator"),
                "created_at": _row_get(r, "created_at"),
            }
            writer.writerow([row.get(k, "") if row.get(k, "") is not None else "" for k in CSV_FIELDS])

    return Response(content=buf.getvalue(), media_type="text/csv")
