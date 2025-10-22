# backend/main.py
from __future__ import annotations

from fastapi import FastAPI
from dotenv import load_dotenv; load_dotenv()

# Routers
from backend.api.session import router as session_router
from backend.api.hand import router as hand_router

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
