# backend/main.py
"""FastAPI application entry point for the NLH trainer backend.

Constructs a FastAPI app, configures CORS for local development, and
registers routers for session management, hand interaction, and data
export. Root and health endpoints provide simple liveness probes.

Note: Optional bot profile selection is env-gated (BOT_PROFILE).
`backend/api/hand.py` reads BOT_PROFILE directly, and this file loads
.env on startup for convenience.

Coach API:
- Router is always registered under /api, but the endpoint itself returns 501
  unless COACH_ENABLED=true (see backend/api/coach.py).

Dev helpers:
- If ALLOW_DEV_AUTO=true (or 1/yes), we expose POST /api/hand/auto which
  advances all bot actions up to the next human decision or end-of-hand.
"""

from __future__ import annotations

import os
from typing import IO, Optional, Union
from os import PathLike

# --- ALL IMPORTS AT THE TOP (fixes ruff E402) ---
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Optional env loader (no-op if python-dotenv isn't installed)
try:
    from dotenv import load_dotenv as _load_dotenv  # type: ignore[no-redef]
except ImportError:
    # Match the real signature exactly so mypy is satisfied
    def load_dotenv(
        dotenv_path: Optional[Union[str, PathLike[str]]] = None,
        stream: Optional[IO[str]] = None,
        verbose: bool = False,
        override: bool = False,
        interpolate: bool = True,
        encoding: Optional[str] = None,
    ) -> bool:
        return False

else:
    # Use the real function when available
    load_dotenv = _load_dotenv

# First-party imports (also kept above any executable statements)
from backend.logger import get_logger  # ensure DB init on startup
from backend.adapters.engines import get_adapter
from backend.api.session import router as session_router
from backend.api.hand import router as hand_router
from backend.api.export import router as export_router
from backend.api.coach import router as coach_router  # coach scaffold (501 by default)
from backend.api.review import router as review_router

# --- Executable statements AFTER all imports ---
# Load environment variables (development convenience; harmless if empty)
load_dotenv()

# Read optional flags
ALLOW_DEV_AUTO = os.environ.get("ALLOW_DEV_AUTO", "false").strip().lower() in (
    "1",
    "true",
    "yes",
)
# BOT_MODE is read by /api/session creation; we just ensure .env is loaded.
# Keeping a note for visibility:
DEFAULT_BOT_MODE = os.environ.get("BOT_MODE", "heuristic").strip().lower()

# Create app
app = FastAPI(
    title="NLH Trainer API",
    version="0.1.0",
    description="Backend API for the NLH training simulator.",
)

# CORS for local frontend dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------- Startup hook (ensure DB schema exists early) --------
@app.on_event("startup")
def _init_db() -> None:
    # Touch the logger to ensure schema migrations/creation have run.
    get_logger()


# -------- Health / Root --------
@app.get("/", tags=["health"])
def root() -> dict:
    return {
        "ok": True,
        "message": "NLH Trainer backend is up",
        "bot_mode_default": DEFAULT_BOT_MODE,
        "allow_dev_auto": ALLOW_DEV_AUTO,
    }


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}


# -------- API Routers --------
# Everything under /api/...
app.include_router(session_router, prefix="/api")
app.include_router(hand_router, prefix="/api")
app.include_router(export_router, prefix="/api")
app.include_router(coach_router, prefix="/api")
app.include_router(review_router, prefix="/api")


# -------- Optional dev-only helper: /api/hand/auto --------
if ALLOW_DEV_AUTO:
    # Import *privately* used helpers from the hand API (dev-only).
    # This avoids duplicating action-loop/logging logic here.
    from backend.api import hand as hand_api  # type: ignore

    @app.post("/api/hand/auto", tags=["hand"])
    def hand_auto() -> dict:
        """
        Advance bot actions until it's the human's turn or the hand ends.
        Returns final state (same shape as GET /api/hand/state.state) and a
        list of bot actions that were applied in this call.
        """
        adapter = get_adapter()
        hand_id_any = getattr(adapter, "hand_id", None)
        if not hand_id_any:
            raise HTTPException(status_code=400, detail="no hand in progress")

        hand_id = hand_api._hand_id_str(hand_id_any)  # dev-only, private helper
        ss = hand_api.get_session_state()
        bots_applied = hand_api._auto_advance_bots(hand_id, ss.human_seat)
        # Persist a snapshot after advancing
        hand_api._persist_snapshot(hand_id)
        state = hand_api._to_public_state(ss.human_seat)
        return {"ok": True, "bots_applied": bots_applied, "state": state}
