"""FastAPI application entry point for the NLH trainer backend.

This module constructs a :class:`FastAPI` application, configures CORS
middleware for the development environment and registers routers for
session management, hand interaction and data export.  The root and
healthcheck endpoints provide simple liveness probes.
"""

from __future__ import annotations

from fastapi import FastAPI
try:
    # Load environment variables early if python‑dotenv is installed.
    from dotenv import load_dotenv  # type: ignore
except ImportError:
    # In production or CI environments the dependency may not be
    # available.  Falling back to no‑op if import fails.
    def load_dotenv() -> None:  # type: ignore[no-redef]
        """Fallback load_dotenv that does nothing when python‑dotenv is missing."""
        return None

# Always call load_dotenv (real or fallback) to ensure consistent behaviour.
load_dotenv()

# Routers
from backend.api.session import router as session_router
from backend.api.hand import router as hand_router
from backend.api.export import router as export_router

app = FastAPI(
    title="NLH Trainer API",
    version="0.1.0",
)

# backend/main.py (add after app = FastAPI(...))
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        # add any additional dev hosts as needed
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------- Health / Root --------

@app.get("/", tags=["health"])
def root() -> dict:
    return {"ok": True, "message": "NLH Trainer backend is up"}


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}


# -------- API Routers --------

# Everything under /api/...
app.include_router(session_router, prefix="/api")
app.include_router(hand_router, prefix="/api")
app.include_router(export_router, prefix="/api")