# backend/api/review.py
from __future__ import annotations

import json
from typing import Any, Dict, Literal

from fastapi import APIRouter, Path, Query
from fastapi.responses import JSONResponse

from backend.review.store import (
    get_advice_by_hand,
    get_hand_actions,
    get_hand_summary,
    list_recent_hands,
)

router = APIRouter(tags=["review"])


def _maybe_parse_json(val: Any) -> Any:
    """If val looks like JSON (string), parse it; otherwise return as-is."""
    if isinstance(val, str):
        s = val.strip()
        if s.startswith("{") or s.startswith("["):
            try:
                return json.loads(s)
            except Exception:
                return val
    return val


@router.get("/review/hands")
def get_review_hands(
    limit: int = Query(100, ge=1, le=1000, description="Max number of hands to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    order: Literal["asc", "desc"] = Query(
        "desc", description="Sort by finished_at (if available) or count fallback"
    ),
) -> JSONResponse:
    """
    List recent hands (best-effort: depends on available schema columns).

    Response shape (matches frontend types):
    {
      "hands": [
        {
          "hand_id": str,
          "finished_at": str | null,
          "seats": int,
          "final_pot": float | null,
          "winners": list[str],
          "action_count": int,
          "has_advice": bool
        },
        ...
      ],
      "meta": { "status": "ok", "count": int, "limit": int, "offset": int, "order": "asc"|"desc" }
    }
    """
    try:
        items = list_recent_hands(limit=limit, offset=offset, order=order)
        payload: Dict[str, Any] = {
            "hands": items,
            "meta": {
                "status": "ok",
                "count": len(items),
                "limit": limit,
                "offset": offset,
                "order": order,
            },
        }
        return JSONResponse(payload, status_code=200)
    except Exception:
        return JSONResponse({"meta": {"status": "error"}}, status_code=500)


@router.get("/review/hand/{hand_id}")
def get_review_hand(
    hand_id: str = Path(..., description="Hand identifier"),
) -> JSONResponse:
    """
    Return a single hand view: summary, ordered actions, and advice snapshots (if any).

    Response shape (matches frontend types):
    {
      "hand_id": str,
      "summary": {
        "seats": int,
        "final_pot": float | null,
        "winners": list[str],
        "started_at": str | null,
        "finished_at": str | null
      },
      "board": {
        "flop"?: list[str],
        "turn"?: str | null,
        "river"?: str | null
      } | null,
      "actions": [...],
      "advice_by_idx": { "<idx>": { recommended_bucket, strategy, ev_map, meta? }, ... },
      "meta": { "status": "ok" }
    }
    """
    try:
        summary = get_hand_summary(hand_id)
        actions = get_hand_actions(hand_id)
        advice_raw = get_advice_by_hand(hand_id)

        # Normalize advice_json to dicts and merge node_key/created_at into meta
        advice_by_idx: Dict[int, Dict[str, Any]] = {}
        for idx, snap in advice_raw.items():
            parsed = _maybe_parse_json(snap.get("advice_json"))

            # Ensure we have a dict payload to attach meta to; otherwise wrap as {"raw": ...}
            if isinstance(parsed, dict):
                advice_obj: Dict[str, Any] = dict(parsed)
                meta = dict(advice_obj.get("meta") or {})
            else:
                advice_obj = {"raw": parsed}
                meta = {}

            nk = snap.get("node_key")
            ca = snap.get("created_at")
            if nk is not None:
                meta["node_key"] = nk
            if ca is not None:
                meta["created_at"] = ca
            if meta:
                advice_obj["meta"] = meta

            advice_by_idx[idx] = advice_obj

        payload: Dict[str, Any] = {
            "hand_id": hand_id,
            "summary": summary,
            # Board is optional in M1; include null if not available to keep the shape stable.
            "board": (
                summary.get("board")
                if isinstance(summary, dict) and "board" in summary
                else None
            ),
            "actions": actions,
            "advice_by_idx": advice_by_idx,
            "meta": {"status": "ok"},
        }
        return JSONResponse(payload, status_code=200)
    except Exception:
        return JSONResponse({"meta": {"status": "error"}}, status_code=500)


__all__ = ["router"]
