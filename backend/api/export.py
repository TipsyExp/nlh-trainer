"""
API routes for exporting logged hand data.

These routes surface per-hand exports from the underlying SQLite logger.
Two formats are provided:

* JSON: the exact serialized GameState as originally logged via ``SQLiteLogger.log_hand``.
* CSV: a tabular representation of the recorded action history for the hand.

Requests will return ``404 Not Found`` if no matching hand exists.  For hands
with no recorded actions the CSV export will return an empty body with a
header row omitted.
"""

from __future__ import annotations

import os
from fastapi import APIRouter, HTTPException, Response

from backend.database import SQLiteLogger


router = APIRouter(tags=["export"])


def _get_logger() -> SQLiteLogger:
    """Instantiate a new SQLiteLogger using the configured path.

    The database path is controlled via the ``LOG_DB_PATH`` environment
    variable and defaults to ``./data/m0.sqlite``.  A fresh connection is
    created for each request to ensure thread safety when FastAPI is run
    with multiple workers.
    """
    db_path = os.getenv("LOG_DB_PATH", "./data/m0.sqlite")
    return SQLiteLogger(db_path)


@router.get("/export/hand/{hand_id}/json", response_class=Response)
def export_hand_json(hand_id: str) -> Response:
    """Return the raw JSON state for a logged hand.

    Args:
        hand_id: Unique identifier of the hand to export.

    Returns:
        A ``Response`` with ``application/json`` content containing the
        serialized GameState.  Raises ``HTTPException`` with status 404
        if the hand does not exist.
    """
    logger = _get_logger()
    try:
        state_json = logger.get_hand_json(hand_id)
        if not state_json:
            raise HTTPException(status_code=404, detail="hand not found")
        return Response(content=state_json, media_type="application/json")
    finally:
        # Always close the DB connection
        logger.close()


@router.get("/export/hand/{hand_id}/csv", response_class=Response)
def export_hand_csv(hand_id: str) -> Response:
    """Return the action history for a hand in CSV format.

    Args:
        hand_id: Unique identifier of the hand to export.

    Returns:
        A ``Response`` with ``text/csv`` content.  If the hand is not
        found a 404 is raised.  If the hand exists but no actions were
        recorded, an empty CSV (no header or rows) is returned.
    """
    logger = _get_logger()
    try:
        # Ensure the hand exists even if no actions are recorded.
        state_json = logger.get_hand_json(hand_id)
        if not state_json:
            raise HTTPException(status_code=404, detail="hand not found")
        csv_data = logger.export_actions_csv(hand_id)
        if csv_data is None:
            # Return an empty body with CSV media type when no actions exist.
            csv_data = ""
        return Response(content=csv_data, media_type="text/csv")
    finally:
        logger.close()