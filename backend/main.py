"""FastAPI application entry point for the NLH trainer backend.

Constructs a FastAPI app, configures CORS for local development, and
registers routers for session management, hand interaction, and data
export. Root and health endpoints provide simple liveness probes.
"""

from __future__ import annotations

from fastapi import FastAPI

# Optional env loader (no-op if python-dotenv isn't installed)
try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:
    def load_dotenv() -> None:  # type: ignore[no-redef]
        return None

# Load environment variables (development convenience; harmless if empty)
load_dotenv()

# Routers
from backend.api.session import router as session_router
from backend.api.hand import router as hand_router
from backend.api.export import router as export_router
from backend.logger import get_logger  # ensure DB init on startup

app = FastAPI(
    title="NLH Trainer API",
    version="0.1.0",
    description="Backend API for the NLH training simulator.",
)

# CORS for local frontend dev
from fastapi.middleware.cors import CORSMiddleware

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
