# backend/api/coach.py
from __future__ import annotations

import os
import time
from typing import Dict, List, Literal

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.adapters.solver.texassolver_adapter import (
    TexasSolverAdapter,
    SolveRequest,
    CoachDisabledError,
    UnsupportedSpotError,
)

router = APIRouter(tags=["coach"])


def _coach_enabled() -> bool:
    val = os.environ.get("COACH_ENABLED", "false").strip().lower()
    return val in {"1", "true", "yes", "on"}


# -------------------------
# GET /api/coach/advice
# (Contract in place; integration with gameplay comes next)
# -------------------------
@router.get("/coach/advice")
def get_advice(hand_id: str = Query(...), idx: int = Query(0)) -> Dict:
    # For now, keep existing behavior so CI and current tests remain stable.
    if not _coach_enabled():
        # 501 with a simple string (matches existing scaffold behavior)
        raise HTTPException(status_code=501, detail="Coach is disabled.")
    # We’ll replace this with real integration when we have the node builder + snapshot write.
    raise HTTPException(status_code=501, detail="Coach is not available in this build.")


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

    adapter = TexasSolverAdapter()
    started = time.perf_counter()
    try:
        advice = adapter.solve(
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
        latency_ms = (time.perf_counter() - started) * 1000.0
        # No cache in this task; no node_key yet (Task-18)
        payload = {
            "recommended_bucket": advice["recommended_bucket"],
            "strategy": advice["strategy"],
            "ev_map": advice.get("ev_map", {}),
            "meta": {
                "status": "ok",
                "cached": False,
                "latency_ms": round(latency_ms, 3),
                "node_key": None,
            },
        }
        return JSONResponse(payload, status_code=200)

    except CoachDisabledError:
        # Adapter double-check; map to disabled
        return JSONResponse({"meta": {"status": "disabled"}}, status_code=501)

    except UnsupportedSpotError as e:
        # Adapter uses UnsupportedSpotError for several cases (including timeout).
        msg = str(e).lower()
        if "timed out" in msg or "timeout" in msg:
            return JSONResponse({"meta": {"status": "timeout"}}, status_code=504)
        return JSONResponse({"meta": {"status": "unsupported"}}, status_code=501)

    except Exception:
        # Unexpected adapter failure
        return JSONResponse({"meta": {"status": "error"}}, status_code=500)
