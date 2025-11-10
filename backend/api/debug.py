# backend/api/debug.py
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from backend.adapters.engines import get_adapter

# This router gets mounted in main.py with prefix="/api"
# Final paths: /api/debug/engine/events and /api/debug/engine/snapshot
router = APIRouter(prefix="/debug/engine", tags=["debug"])


@router.get("/events")
def engine_events(
    since: int = Query(0, ge=0, description="Return events with seq > since"),
    limit: int = Query(200, ge=0, le=1000, description="Max events to return"),
) -> List[Dict[str, Any]]:
    """
    Return the in-memory engine debug events ring buffer (dev-only).
    Shape: a plain JSON array of events. Each event includes fields like:
    seq, hand, street, kind, pot, price, to_act, plus action metadata.
    """
    adapter = get_adapter()
    getter = getattr(adapter, "_get_events_since", None)
    if callable(getter):
        return getter(since=since, limit=limit)  # type: ignore[misc]
    # If the adapter doesn't support events, return an empty list.
    return []


@router.get("/snapshot")
def engine_snapshot() -> Dict[str, Any]:
    """
    Return a rich internal snapshot of the engine state (dev-only).
    Helpful to compare backend truth vs frontend rendering.
    """
    a = get_adapter()

    def last_action_dict(la: Optional[object]) -> Optional[Dict[str, Any]]:
        if la is None:
            return None
        return {
            "seat": getattr(la, "seat", None),
            "type": getattr(la, "type", None),
            "requested": getattr(la, "requested", None),
            "committed": getattr(la, "committed", None),
            "snapped": getattr(la, "snapped", None),
            "bucket_label": getattr(la, "bucket_label", None),
            "allowed_buckets": getattr(la, "allowed_buckets", None),
        }

    next_seat = getattr(a, "_next_to_act", None)
    to_call_next = getattr(a, "_to_call_next", 0)

    # Compute min raise + allowed buckets (if available)
    min_raise_total: Optional[int] = None
    allowed_buckets_next: List[str] = []
    try:
        if next_seat is not None:
            min_raise_total = a._compute_min_raise_total(int(next_seat), int(to_call_next))  # type: ignore[attr-defined]
            allowed_buckets_next = [
                b["label"] for b in a._allowed_buckets_data(int(to_call_next), next_seat)  # type: ignore[attr-defined]
            ]
    except Exception:
        # Keep optional fields None/[] if any internal detail differs
        pass

    return {
        "debug_enabled": os.getenv("ENGINE_DEBUG_HTTP", "0").lower() in ("1", "true", "yes", "on"),
        "table": {
            "seats": a.seats,
            "sb": a.sb,
            "bb": a.bb,
            "ante": a.ante,
            "button": a.button,
            "sb_seat": a.sb_seat,
            "bb_seat": a.bb_seat,
        },
        "hand_id": a.hand_id,
        "street": getattr(a, "_street", None),
        "base_seed": getattr(a, "base_seed", None),
        "deck_seed": getattr(a, "_deck_seed", None),
        "board_all": getattr(a, "_board", []),
        "players_holes": getattr(a, "_players_holes", []),
        "committed": getattr(a, "_committed", []),
        "current_price": getattr(a, "_current_price", 0),
        "last_raise_size": getattr(a, "_last_raise_size", 0),
        "raises_this_round": getattr(a, "_raises_this_round", 0),
        "pot_total": getattr(a, "_pot_total", 0),
        "next_to_act": next_seat,
        "to_call_next": to_call_next,
        "min_raise_total": min_raise_total,
        "allowed_buckets_next": allowed_buckets_next,
        "last_action": last_action_dict(getattr(a, "_last_action", None)),
    }
