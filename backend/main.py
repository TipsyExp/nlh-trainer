"""
FastAPI application entrypoint for the NLH trainer backend.

This module wires together the various API routers and exposes
simple health checks.  New routers should be registered here
under the ``/api`` prefix to make their endpoints available.
"""

from __future__ import annotations

from fastapi import FastAPI

# Routers
from backend.api.session import router as session_router
from backend.api.hand import router as hand_router
from backend.api.export import router as export_router


app = FastAPI(
    title="NLH Trainer API",
    version="0.1.0",
)


# -------- Health / Root --------

@app.get("/", tags=["health"])
def root() -> dict:
    """Root endpoint used for quick up checks."""
    return {"ok": True, "message": "NLH Trainer backend is up"}


@app.get("/health", tags=["health"])
def health() -> dict:
    """Simple health check endpoint."""
    return {"status": "ok"}


# -------- API Routers --------

# Everything under /api/...
app.include_router(session_router, prefix="/api")
app.include_router(hand_router, prefix="/api")
app.include_router(export_router, prefix="/api")