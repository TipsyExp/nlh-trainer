from __future__ import annotations

from fastapi import FastAPI

# Routers
from backend.api.session import router as session_router
from backend.api.hand import router as hand_router

app = FastAPI(title="NLH Trainer API", version="0.1.0")


@app.get("/")
def root():
    return {"ok": True, "message": "NLH Trainer API"}


# Mount API routes
app.include_router(session_router, prefix="/api")
app.include_router(hand_router, prefix="/api")
