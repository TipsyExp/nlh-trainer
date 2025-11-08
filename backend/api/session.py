# backend/api/session.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional, Literal, cast

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from backend.adapters.engines import get_adapter
from backend.logger import get_logger

router = APIRouter(tags=["session"])

# ---------- In-memory session state ----------

BotMode = Literal["none", "heuristic"]


@dataclass
class SessionState:
    seats: int
    sb: int
    bb: int
    ante: int
    stacks: List[int]
    base_seed: Optional[str]
    human_seat: int
    logger_session_id: int
    bot_mode: BotMode


_STATE: Optional[SessionState] = None


def get_session_state() -> SessionState:
    """Return the current session state or raise if none has been created."""
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
    bot_mode: Optional[str] = None  # validated & normalized below

    @field_validator("human_seat")
    @classmethod
    def _check_human_seat(cls, v: int, info):
        seats = info.data.get("seats")
        if seats is not None and not (0 <= v < seats):
            raise ValueError("human_seat out of range")
        return v

    @field_validator("bot_mode")
    @classmethod
    def _norm_bot_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        vv = str(v).strip().lower()
        if vv not in ("none", "heuristic"):
            raise ValueError("bot_mode must be 'none' or 'heuristic'")
        return vv


class SessionResponse(BaseModel):
    ok: bool
    detail: str
    session_id: int


# ---------- Routes ----------


@router.post("/session", response_model=SessionResponse)
def create_or_reset_session(req: SessionRequest) -> SessionResponse:
    """Create a new session or reset the current one.

    This endpoint initialises the poker engine with the supplied table
    configuration and records a new session in the logger. The returned
    response includes the new session_id.
    """
    global _STATE
    try:
        eng = get_adapter()
        # Matches adapter signature: (seats, sb, bb, ante, stacks, base_seed=None)
        eng.start_table(req.seats, req.sb, req.bb, req.ante, req.stacks, req.base_seed)
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"failed to start table: {e}"
        ) from e

    # Create a new session in the logger
    logger = get_logger()
    session_id = logger.new_session()

    # Determine bot_mode from request or environment (default 'heuristic')
    env_default = os.environ.get("BOT_MODE", "heuristic").strip().lower()
    chosen = req.bot_mode or env_default
    if chosen not in ("none", "heuristic"):
        chosen = "heuristic"
    bot_mode: BotMode = cast(BotMode, chosen)

    _STATE = SessionState(
        seats=req.seats,
        sb=req.sb,
        bb=req.bb,
        ante=req.ante,
        stacks=req.stacks,
        base_seed=req.base_seed,
        human_seat=req.human_seat,
        logger_session_id=session_id,
        bot_mode=bot_mode,
    )
    return SessionResponse(
        ok=True, detail="session created/reset", session_id=session_id
    )
