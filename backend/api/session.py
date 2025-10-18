# backend/api/session.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from backend.adapters.engines import get_adapter

router = APIRouter(tags=["session"])


# ---------- In-memory session state ----------

@dataclass
class SessionState:
    seats: int
    sb: int
    bb: int
    ante: int
    stacks: List[int]
    base_seed: Optional[str]
    human_seat: int


_STATE: Optional[SessionState] = None


def get_session_state() -> SessionState:
    if _STATE is None:
        raise RuntimeError("Session not initialized")
    return _STATE


# ---------- Models ----------

class SessionRequest(BaseModel):
    seats: int
    sb: int
    bb: int
    ante: int = 0
    stacks: List[int]
    base_seed: Optional[str] = None
    human_seat: int = 0

    @field_validator("human_seat")
    @classmethod
    def _check_human_seat(cls, v: int, info):
        seats = info.data.get("seats")
        if seats is not None and not (0 <= v < seats):
            raise ValueError("human_seat out of range")
        return v


class SessionResponse(BaseModel):
    ok: bool
    detail: str


# ---------- Routes ----------

@router.post("/session", response_model=SessionResponse)
def create_or_reset_session(req: SessionRequest) -> SessionResponse:
    global _STATE
    try:
        eng = get_adapter()
        # Matches adapter signature: (seats, sb, bb, ante, stacks, base_seed=None)
        eng.start_table(req.seats, req.sb, req.bb, req.ante, req.stacks, req.base_seed)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"failed to start table: {e}") from e

    _STATE = SessionState(
        seats=req.seats,
        sb=req.sb,
        bb=req.bb,
        ante=req.ante,
        stacks=req.stacks,
        base_seed=req.base_seed,
        human_seat=req.human_seat,
    )
    return SessionResponse(ok=True, detail="session created/reset")
