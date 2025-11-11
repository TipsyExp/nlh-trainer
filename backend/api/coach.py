# backend/api/coach.py
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Literal, cast

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.adapters.engines import get_adapter
from backend.api.session import get_session_state
from backend.api.hand import (
    _auto_advance_bots,
    _to_public_state,
)
from backend.adapters.solver.texassolver_adapter import (
    TexasSolverAdapter,
    SolveRequest,
    CoachDisabledError,
    UnsupportedSpotError,
)
from backend.coach.texassolver_cache import resolve_with_cache

router = APIRouter(tags=["coach"])


def _coach_enabled() -> bool:
    val = os.environ.get("COACH_ENABLED", "false").strip().lower()
    return val in {"1", "true", "yes", "on"}


def _current_hand_id_str() -> str:
    """Return current adapter hand id in 'H#' form; raise if none."""
    h = getattr(get_adapter(), "hand_id", None)
    if not h:
        raise RuntimeError("no hand in progress")
    return f"H{h}" if isinstance(h, int) else str(h)


# -------------------------
# GET /api/coach/advice
# -------------------------
@router.get("/coach/advice")
def get_advice(hand_id: str = Query(...), idx: int = Query(0)) -> JSONResponse:
    if not _coach_enabled():
        return JSONResponse({"meta": {"status": "disabled"}}, status_code=501)

    # Build canonical node (stub / may raise UnsupportedSpotError)
    try:
        from backend.coach.node_builder import build_solve_request_from_hand

        node_req = build_solve_request_from_hand(hand_id, idx)
    except UnsupportedSpotError as e:
        msg = str(e).lower()
        if "timed out" in msg or "timeout" in msg:
            return JSONResponse({"meta": {"status": "timeout"}}, status_code=504)
        return JSONResponse({"meta": {"status": "unsupported"}}, status_code=501)
    except Exception:
        return JSONResponse({"meta": {"status": "error"}}, status_code=500)

    started = time.perf_counter()
    try:
        advice_payload, cached, node_key = resolve_with_cache(node_req)
        latency_ms = (time.perf_counter() - started) * 1000.0

        # Pull fields safely with fallbacks
        recommended_bucket = cast(str, advice_payload.get("recommended_bucket", ""))
        strategy = cast(Dict[str, float], advice_payload.get("strategy", {}))
        ev_map = cast(Dict[str, float], advice_payload.get("ev_map", {}))

        payload: Dict[str, Any] = {
            "recommended_bucket": recommended_bucket,
            "strategy": strategy,
            "ev_map": ev_map,
            "meta": {
                "status": "ok",
                "cached": bool(cached),
                "latency_ms": round(latency_ms, 3),
                "node_key": node_key,
            },
        }

        # Success only: persist snapshot
        try:
            from backend.coach.advice_store import write_snapshot

            write_snapshot(hand_id, idx, node_key=node_key, advice_json=payload)
        except Exception:
            # Never fail the request on snapshot errors
            pass

        # tiny structured log
        try:
            top = recommended_bucket or "-"
            ck = "true" if cached else "false"
            nk = (node_key or "")[:12]
            print(
                f"coach_advice hand={hand_id} idx={idx} status=ok latency_ms={payload['meta']['latency_ms']} top={top} cached={ck} node_key={nk}"
            )
        except Exception:
            pass

        return JSONResponse(payload, status_code=200)

    except CoachDisabledError:
        return JSONResponse({"meta": {"status": "disabled"}}, status_code=501)
    except UnsupportedSpotError as e:
        msg = str(e).lower()
        if "timed out" in msg or "timeout" in msg:
            return JSONResponse({"meta": {"status": "timeout"}}, status_code=504)
        return JSONResponse({"meta": {"status": "unsupported"}}, status_code=501)
    except Exception:
        return JSONResponse({"meta": {"status": "error"}}, status_code=500)


# -------------------------
# Dev/Test endpoint to exercise the adapter directly
# POST /api/coach/test_solve
# -------------------------


class SolveRequestModel(BaseModel):
    street: Literal["flop", "turn", "river"]
    board: List[str] = Field(..., description='["Ah","Kd","3s"]')
    pot: int
    ip_stack: int
    oop_stack: int
    ip_range: str
    oop_range: str
    bucket_labels: List[str]
    spot: Literal["SRP", "3BP"] = "SRP"


@router.post("/coach/test_solve")
def post_test_solve(req: SolveRequestModel = Body(...)) -> JSONResponse:
    if not _coach_enabled():
        return JSONResponse({"meta": {"status": "disabled"}}, status_code=501)

    # Intentionally uncached for a clean dev endpoint
    adapter = TexasSolverAdapter()
    started = time.perf_counter()
    try:
        advice_raw = adapter.solve(
            SolveRequest(
                street=req.street,
                board=req.board,
                pot=req.pot,
                ip_stack=req.ip_stack,
                oop_stack=req.oop_stack,
                ip_range=req.ip_range,
                oop_range=req.oop_range,
                bucket_labels=req.bucket_labels,
                spot=req.spot,
            )
        )
        advice = cast(Dict[str, Any], advice_raw)  # mypy: treat as plain dict
        latency_ms = (time.perf_counter() - started) * 1000.0

        recommended_bucket = cast(str, advice.get("recommended_bucket", ""))
        strategy = cast(Dict[str, float], advice.get("strategy", {}))
        ev_map = cast(Dict[str, float], advice.get("ev_map", {}))

        payload: Dict[str, Any] = {
            "recommended_bucket": recommended_bucket,
            "strategy": strategy,
            "ev_map": ev_map,
            "meta": {
                "status": "ok",
                "cached": False,
                "latency_ms": round(latency_ms, 3),
                "node_key": None,
            },
        }
        return JSONResponse(payload, status_code=200)

    except CoachDisabledError:
        return JSONResponse({"meta": {"status": "disabled"}}, status_code=501)

    except UnsupportedSpotError as e:
        msg = str(e).lower()
        if "timed out" in msg or "timeout" in msg:
            return JSONResponse({"meta": {"status": "timeout"}}, status_code=504)
        return JSONResponse({"meta": {"status": "unsupported"}}, status_code=501)

    except Exception:
        return JSONResponse({"meta": {"status": "error"}}, status_code=500)


# ------------------------------------------
# POST /api/coach/ensure_progress (production)
# ------------------------------------------
@router.post("/coach/ensure_progress")
def post_ensure_progress() -> JSONResponse:
    """
    Production-safe bot trigger: if it's a bot's turn, advance bots until it's
    the human's turn (or hand ends). Returns the updated state plus the list of
    bot actions taken. If it's already the human's turn, no-ops and returns
    the current state with an empty list.
    """
    adapter = get_adapter()
    ss = get_session_state()
    human_seat = ss.human_seat

    # Resolve current hand id (error if none)
    try:
        hand_id = _current_hand_id_str()
    except RuntimeError:
        return JSONResponse(
            {
                "ok": False,
                "bots_applied": [],
                "state": {},
                "meta": {"status": "no_hand"},
            },
            status_code=400,
        )

    # If it's a bot to act, advance; otherwise just return state
    actor = adapter.next_actor()
    bots: List[Dict[str, Any]] = []
    if actor and int(actor.get("seat", -1)) != int(human_seat):
        try:
            bots = _auto_advance_bots(hand_id, human_seat)
        except RuntimeError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    # Return current snapshot (post-bot if any advanced)
    state = _to_public_state(human_seat)
    return JSONResponse(
        {"ok": True, "bots_applied": bots, "state": state}, status_code=200
    )
