"""FastAPI application entry point for the NLH trainer backend.

Constructs a FastAPI app, configures CORS for local development, and
registers routers for session management, hand interaction, and data
export. Root and health endpoints provide simple liveness probes.
"""

from __future__ import annotations

# --- ALL IMPORTS AT THE TOP (fixes ruff E402) ---
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Optional env loader (no-op if python-dotenv isn't installed)
try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:

    def load_dotenv() -> None:  # type: ignore[no-redef]
        return None


# First-party imports (also kept above any executable statements)
from backend.logger import get_logger  # ensure DB init on startup
from backend.api.session import router as session_router
from backend.api.hand import router as hand_router
from backend.api.export import router as export_router

# If/when you add coach API:
# from backend.api.coach import router as coach_router

# --- Executable statements AFTER all imports ---
# Load environment variables (development convenience; harmless if empty)
load_dotenv()

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
    return {"ok": True, "message": "NLH Trainer backend is up"}


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}


# -------- API Routers --------
# Everything under /api/...
app.include_router(session_router, prefix="/api")
app.include_router(hand_router, prefix="/api")
app.include_router(export_router, prefix="/api")
# app.include_router(coach_router, prefix="/api")
