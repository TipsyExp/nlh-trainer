"""Export API for the NLH trainer.

This module defines endpoints for exporting hand and session data in
JSON or CSV formats.  The exported payloads allow consumers to
round‑trip a hand through the simulator by deserialising the state
and action history and replaying them.  When exporting multiple hands
in a session the same structure is repeated for each hand.
"""

from __future__ import annotations

import json
import io
from typing import Any, Dict, Iterable, List

from fastapi import APIRouter, HTTPException, Response

from backend.logger import get_logger

router = APIRouter(tags=["export"])


def _actions_to_dicts(rows: Iterable[Any]) -> List[Dict[str, Any]]:
    """Convert action rows from the database into JSON‑serialisable dicts."""
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "idx": r["idx"],
                "street": r["street"],
                "actor_seat": r["actor_seat"],
                "type": r["type"],
                "amount": r["amount"],
                "bucket": r["bucket"],
                "to_call_after": r["to_call_after"],
                "pot_after": r["pot_after"],
                "time_ms": r["time_ms"],
                "rng_seed": r["rng_seed"],
                "snapped": r["snapped"],
                "meta": r["meta"],
            }
        )
    return out


@router.get("/export/hand/{hand_id}.json")
def export_hand_json(hand_id: str) -> Dict[str, Any]:
    """Export a single hand as JSON.

    The response contains the serialised GameState and the list of
    per‑action records.  If the hand id is unknown a 404 is returned.
    """
    logger = get_logger()
    state_json = logger.fetch_hand_state_json(hand_id)
    if state_json is None:
        raise HTTPException(status_code=404, detail="hand not found")
    actions = _actions_to_dicts(logger.fetch_hand_actions(hand_id))
    return {"state": json.loads(state_json), "actions": actions}


@router.get("/export/hand/{hand_id}.csv")
def export_hand_csv(hand_id: str) -> Response:
    """Export a single hand's action history as CSV.

    The CSV includes a header row followed by one row per action.  If
    the hand id is unknown a 404 is returned.  The state is not
    included in the CSV variant.
    """
    logger = get_logger()
    # Ensure hand exists
    state_json = logger.fetch_hand_state_json(hand_id)
    if state_json is None:
        raise HTTPException(status_code=404, detail="hand not found")
    rows = logger.fetch_hand_actions(hand_id)
    header = [
        "idx",
        "street",
        "actor_seat",
        "type",
        "amount",
        "bucket",
        "to_call_after",
        "pot_after",
        "time_ms",
        "rng_seed",
        "snapped",
        "meta",
    ]
    buf = io.StringIO()
    buf.write(",".join(header) + "\n")
    for r in rows:
        values = [
            r["idx"],
            r["street"],
            r["actor_seat"],
            r["type"],
            r["amount"],
            r["bucket"],
            r["to_call_after"],
            r["pot_after"],
            r["time_ms"],
            r["rng_seed"],
            r["snapped"],
            r["meta"],
        ]
        # Convert None to empty string
        buf.write(",".join("" if v is None else str(v) for v in values) + "\n")
    data = buf.getvalue()
    return Response(content=data, media_type="text/csv")


@router.get("/export/session/{session_id}.json")
def export_session_json(session_id: int) -> Dict[str, Any]:
    """Export all hands in a session as JSON.

    The response contains a list of objects, one per hand.  Each object
    mirrors the structure returned by ``export_hand_json``.  If the
    session has no hands a 404 is returned.
    """
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
    return {"hands": out}


@router.get("/export/session/{session_id}.csv")
def export_session_csv(session_id: int) -> Response:
    """Export all hands in a session as a CSV archive.

    The CSV contains a header identifying the hand id followed by the
    action records for that hand.  Each hand is separated by a blank
    line.  If the session is unknown a 404 is returned.
    """
    logger = get_logger()
    hands = list(logger.fetch_hands_for_session(session_id))
    if not hands:
        raise HTTPException(status_code=404, detail="session not found or empty")
    header = [
        "hand_id",
        "idx",
        "street",
        "actor_seat",
        "type",
        "amount",
        "bucket",
        "to_call_after",
        "pot_after",
        "time_ms",
        "rng_seed",
        "snapped",
        "meta",
    ]
    buf = io.StringIO()
    buf.write(",".join(header) + "\n")
    for hand in hands:
        hand_id = hand["hand_id"]
        for r in logger.fetch_hand_actions(hand_id):
            values = [
                hand_id,
                r["idx"],
                r["street"],
                r["actor_seat"],
                r["type"],
                r["amount"],
                r["bucket"],
                r["to_call_after"],
                r["pot_after"],
                r["time_ms"],
                r["rng_seed"],
                r["snapped"],
                r["meta"],
            ]
            buf.write(",".join("" if v is None else str(v) for v in values) + "\n")
        # separate hands with a blank line
        buf.write("\n")
    data = buf.getvalue()
    return Response(content=data, media_type="text/csv")
