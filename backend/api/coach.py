from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(tags=["coach"])


def _coach_enabled() -> bool:
    val = os.environ.get("COACH_ENABLED", "false").strip().lower()
    return val in {"1", "true", "yes", "on"}


@router.get("/coach/advice")
def get_advice(hand_id: str = Query(...), idx: int = Query(0)) -> dict:
    # For this scaffold, always return 501; when disabled, make it explicit.
    if not _coach_enabled():
        raise HTTPException(status_code=501, detail="Coach is disabled.")
    raise HTTPException(status_code=501, detail="Coach is not available in this build.")
