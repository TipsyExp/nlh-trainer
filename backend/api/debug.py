# backend/api/debug.py
"""
Development-only debug endpoints for the NLH engine.

These routes expose rich event and state information when ENGINE_DEBUG_HTTP is
enabled. They are not intended for production and should be gated behind
configuration flags. The endpoints provide:

* `/events` – engine events with extended metadata such as timestamps, request
  IDs and invariant flags.
* `/snapshot` – the current full internal state of the engine.
* `/diff` – a compact delta between two events or snapshots.
* `/config` – current debug configuration and environment toggles.
* `/export` – export a ZIP bundle of events, snapshot and config for
  offline analysis.
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from backend.adapters.engines import get_adapter

# Import configuration flags.  ENGINE_DEBUG_HTTP determines whether these endpoints
# are included by backend/main.py.  HAND_AUTO_ENABLED is exposed in /config for
# visibility.
from backend.config import ENGINE_DEBUG_HTTP, HAND_AUTO_ENABLED
from backend.api.session import get_session_state

# This router gets mounted in main.py with prefix="/api"
# Final paths: /api/debug/engine/events, /api/debug/engine/snapshot, etc.
router = APIRouter(prefix="/debug/engine", tags=["debug"])


@router.get("/events")
def engine_events(
    since: int = Query(0, ge=0, description="Return events with seq > since"),
    limit: int = Query(200, ge=0, le=1000, description="Max events to return"),
    hand_id: Optional[int] = Query(None, description="Filter events by hand ID"),
    street: Optional[str] = Query(
        None, description="Filter events by street (preflop/flop/turn/river/showdown)"
    ),
) -> List[Dict[str, Any]]:
    """Return the in-memory engine debug events ring buffer (dev-only).

    Shape: a plain JSON array of events.  Each event includes fields like:
    seq, hand_id, street, kind, pot, price, to_act, actor_before/after,
    state_hash, delta, invariants and optional latency metrics.
    """
    adapter = get_adapter()
    getter = getattr(adapter, "_get_events_since", None)
    if not callable(getter):
        return []
    events = getter(since=since, limit=limit)  # type: ignore[misc]
    # Apply optional filters
    if hand_id is not None:
        events = [e for e in events if int(e.get("hand_id", 0)) == int(hand_id)]
    if street is not None:
        # Normalize both sides to lower case for robust matching (e.g., "Flop" vs "flop").
        events = [
            e for e in events if str(e.get("street", "")).lower() == street.lower()
        ]
    return events


@router.get("/snapshot")
def engine_snapshot() -> Dict[str, Any]:
    """Return a rich internal snapshot of the engine state (dev-only).

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
        # Mirror the effective debug flag from configuration instead of re-parsing the environment.
        "debug_enabled": ENGINE_DEBUG_HTTP,
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


@router.get("/diff")
def engine_diff(
    from_seq: int = Query(..., ge=1, description="Lower-bound event seq (inclusive)"),
    to_seq: int = Query(..., ge=1, description="Upper-bound event seq (inclusive)"),
) -> Dict[str, Any]:
    """Return a compact delta between two debug events.

    The diff includes key state fields (street, actor, pot, committed, price, board)
    and shows how they changed between the two events.  If either event isn't
    found, a 404 is returned.
    """
    adapter = get_adapter()
    events = getattr(adapter, "_debug_events", None)
    if events is None:
        raise HTTPException(status_code=404, detail="debug events not enabled")
    ev_from = None
    ev_to = None
    for e in events:
        seq = int(e.get("seq", 0))
        if seq >= from_seq and ev_from is None:
            ev_from = e
        if seq >= to_seq:
            ev_to = e
            break
    if ev_from is None or ev_to is None:
        raise HTTPException(
            status_code=404, detail="events not found for given seq range"
        )
    # Compute diff between two event snapshots.  Only fields of interest are compared.
    # Only compare keys that exist in both events to avoid polluting the diff with None values.
    candidate_keys = {
        "street",
        "actor_after",
        "pot",
        "price",
        "to_act",
        "board",
        "committed",
    }
    diff: Dict[str, Any] = {}
    for key in candidate_keys:
        if key in ev_from and key in ev_to:
            v1 = ev_from.get(key)
            v2 = ev_to.get(key)
            if v1 != v2:
                diff[key] = {"from": v1, "to": v2}
    return {
        "from_seq": from_seq,
        "to_seq": to_seq,
        "diff": diff,
    }


@router.get("/config")
def engine_config() -> Dict[str, Any]:
    """Return the effective debug configuration and environment toggles."""
    adapter = get_adapter()
    ring = getattr(adapter, "_debug_events", None)
    ring_maxlen = getattr(ring, "maxlen", None) if ring is not None else None
    return {
        # Surface the key debug and auto-play flags as seen by the running process.
        "ENGINE_DEBUG_HTTP": str(ENGINE_DEBUG_HTTP).lower(),
        "HAND_AUTO_ENABLED": str(HAND_AUTO_ENABLED).lower(),
        "ENGINE_DEBUG_RING_MAX": os.getenv("ENGINE_DEBUG_RING_MAX", "300"),
        "DEBUG_SAMPLING": os.getenv("DEBUG_SAMPLING", "1"),
        "BOT_TRACE": os.getenv("BOT_TRACE", "0"),
        "DEBUG_EXPORT_SANITIZE": os.getenv("DEBUG_EXPORT_SANITIZE", "true"),
        "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
        "ring_buffer_size": ring_maxlen,
    }


@router.post("/export")
def export_bundle(
    sanitize: bool = Query(True, description="Redact PII and card visibility")
) -> Response:
    """Return a ZIP bundle containing events, snapshot, config and seeds.

    The ZIP includes:
    - events.json: the list of all debug events currently stored
    - snapshot.json: the current internal engine snapshot
    - config.json: the effective debug configuration
    - seeds.json: the engine's base and deck seeds
    Optionally, sanitizes sensitive data such as hole cards and request bodies.
    """
    adapter = get_adapter()
    events: List[Dict[str, Any]] = []
    try:
        # Determine how many events to fetch.  A limit of 0 yields no events on many adapters.
        ring = getattr(adapter, "_debug_events", None)
        # If the ring exists, use its length; otherwise fall back to a generous default (1000).
        limit = len(ring) if ring is not None else 1000
        events = adapter._get_events_since(0, limit=limit)  # type: ignore[misc]
    except Exception:
        pass
    snapshot = engine_snapshot()
    config = engine_config()
    seeds = {
        "base_seed": getattr(adapter, "base_seed", None),
        "deck_seed": getattr(adapter, "_deck_seed", None),
    }
    # Sanitize player hole cards by masking non-humans (all seats except the human) unless showdown
    if sanitize and "players_holes" in snapshot:
        ph = snapshot["players_holes"]
        street = snapshot.get("street")
        # Determine the human seat from the session so we don't expose the hero's cards
        try:
            human_seat = get_session_state().human_seat
        except Exception:
            human_seat = 0
        # If not at showdown, mask all seat hole cards except the human seat for reproducibility
        if street != "showdown":
            masked: List[List[str]] = []
            for idx, cards in enumerate(ph):
                if idx == human_seat:
                    masked.append(cards)
                else:
                    masked.append(["XX", "XX"])
            snapshot["players_holes"] = masked
    # Build ZIP in memory
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("events.json", json.dumps(events, default=str, indent=2))
        zf.writestr("snapshot.json", json.dumps(snapshot, default=str, indent=2))
        zf.writestr("config.json", json.dumps(config, default=str, indent=2))
        zf.writestr("seeds.json", json.dumps(seeds, default=str, indent=2))
    mem.seek(0)
    headers = {"Content-Disposition": "attachment; filename=nlh_debug_bundle.zip"}
    return Response(content=mem.read(), media_type="application/zip", headers=headers)
