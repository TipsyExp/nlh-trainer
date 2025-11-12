# backend/main.py
"""FastAPI application entry point for the NLH trainer backend.

Constructs a FastAPI app, configures CORS for local development, and
registers routers for session management, hand interaction, and data
export. Root and health endpoints provide simple liveness probes.

Notes:

* Runtime flags are parsed once in ``backend.config`` and imported here.
  ``HAND_AUTO_ENABLED`` controls both exposure of the dev ``POST /api/hand/auto``
  endpoint and auto-stepping of bots after a human action. ``ENGINE_DEBUG_HTTP``
  gates the debug endpoints under ``/api/debug``. ``DEFAULT_BOT_MODE`` reflects
  the default bot mode as declared in the environment.
* This file no longer re-parses ``ALLOW_DEV_AUTO`` or ``ENGINE_DEBUG_HTTP``.
  The old dev helper route has been removed in favour of relying on the
  ``/api/hand/auto`` route defined in ``backend/api/hand.py`` when auto play is enabled.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.background import BackgroundTask, BackgroundTasks
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config import (
    HAND_AUTO_ENABLED,
    ENGINE_DEBUG_HTTP,
    BOT_MODE as DEFAULT_BOT_MODE,
)
from backend.logger import get_logger  # ensure DB init on startup
from backend.adapters.engines import get_adapter
from backend.api.session import router as session_router
from backend.api.hand import router as hand_router
from backend.api.export import router as export_router
from backend.api.coach import router as coach_router  # coach scaffold (501 by default)
from backend.api.review import router as review_router
from backend.api.debug import router as debug_router  # conditionally included below


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
        # Expose runtime flags for diagnostics.  The hand auto flag controls both
        # exposure of POST /api/hand/auto and auto-play after human actions.
        "hand_auto_enabled": HAND_AUTO_ENABLED,
        "engine_debug_http": ENGINE_DEBUG_HTTP,
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
if ENGINE_DEBUG_HTTP:
    app.include_router(debug_router, prefix="/api")

# The POST /api/hand/auto route is always provided by backend/api/hand.py.  It
# returns a 501 when HAND_AUTO_ENABLED is false.  No additional dev helper is registered here.
