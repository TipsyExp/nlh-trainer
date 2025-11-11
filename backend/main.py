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
- If ENGINE_DEBUG_HTTP=true (or 1/yes/on), we include /api/debug endpoints for
  engine event logs / inspection (see backend/api/debug.py).
"""

from __future__ import annotations

import os
import uuid
from typing import IO, Optional, Union
from os import PathLike
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.background import BackgroundTask, BackgroundTasks

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
from backend.api.debug import router as debug_router  # conditionally included below


# Load environment variables (development convenience; harmless if empty)
load_dotenv()

# Read optional flags
ALLOW_DEV_AUTO = os.environ.get("ALLOW_DEV_AUTO", "false").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
DEBUG_HTTP_ENABLED = os.environ.get("ENGINE_DEBUG_HTTP", "false").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
# BOT_MODE is read by /api/session creation; we just ensure .env is loaded.
# Keeping a note for visibility:
DEFAULT_BOT_MODE = os.environ.get("BOT_MODE", "heuristic").strip().lower()


# -------- Lifespan (replaces deprecated @on_event startup) --------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Touch the logger to ensure schema migrations/creation have run.
    get_logger()
    yield


# Create app
app = FastAPI(
    title="NLH Trainer API",
    version="0.1.0",
    description="Backend API for the NLH training simulator.",
    lifespan=lifespan,
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

# ---------------------------------------------------------------------------
# Request ID middleware


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to each incoming HTTP request.

    The request ID is passed down into the engine adapter for correlation of
    emitted debug events. Clients may also provide an X-Request-ID header to
    override the auto-generated ID. The ID is cleared *after* the response is
    sent, via a BackgroundTask, so events emitted during response streaming
    remain correlated. The response will echo the X-Request-ID header.
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Stash on request (useful for handlers/background tasks)
        setattr(request.state, "request_id", req_id)

        # Attach to engine adapter for event correlation
        adapter = get_adapter()
        if hasattr(adapter, "attach_request_id"):
            adapter.attach_request_id(req_id)

        try:
            response = await call_next(request)
        except Exception:
            # Ensure cleanup on error paths too
            if hasattr(adapter, "attach_request_id"):
                adapter.attach_request_id(None)
            raise

        # Echo request ID header
        response.headers["X-Request-ID"] = req_id

        # Clear the adapter's request ID *after* response completes.
        clear_task = BackgroundTask(adapter.attach_request_id, None)
        existing_bg = getattr(response, "background", None)
        if existing_bg is None:
            response.background = clear_task
        elif isinstance(existing_bg, BackgroundTask):
            response.background = BackgroundTasks([existing_bg, clear_task])
        elif isinstance(existing_bg, BackgroundTasks):
            existing_bg.add_task(adapter.attach_request_id, None)
        else:
            # Fallback: if some other type, just replace to be safe.
            response.background = clear_task

        return response


# Register the middleware with the app. It must come after CORS for the
# middleware to see the request headers.
app.add_middleware(RequestIDMiddleware)


# -------- Health / Root --------
@app.get("/", tags=["health"])
def root() -> dict:
    return {
        "ok": True,
        "message": "NLH Trainer backend is up",
        "bot_mode_default": DEFAULT_BOT_MODE,
        "allow_dev_auto": ALLOW_DEV_AUTO,
        "engine_debug_http": DEBUG_HTTP_ENABLED,
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

# Optional: debug endpoints for engine event logs (dev-only)
if DEBUG_HTTP_ENABLED:
    app.include_router(debug_router, prefix="/api")


# -------- Optional dev-only helper: /api/hand/auto --------
if ALLOW_DEV_AUTO:
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
