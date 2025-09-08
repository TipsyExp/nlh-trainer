"""
Entry point for the FastAPI application used by the NLH training
simulator.  The API is intentionally minimal at this stage of
development (M0) and exposes only a health check endpoint.

Future milestones will extend this app with endpoints for
creating sessions, playing hands and exporting histories.  See
``docs/STATE-SCHEMA.md`` and ``docs/M0-SPEC.md`` for further
information.
"""

from fastapi import FastAPI

from .routers import health

app = FastAPI(
    title="NLH Training Simulator",
    description=(
        "A training simulator for no‑limit hold'em, providing a local "
        "engine and UI for studying hands."
    ),
    version="0.0.1",
)

app.include_router(health.router)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint that returns a brief welcome message.

    Returns:
        A JSON object with a welcome message.
    """
    return {"message": "Welcome to the NLH training simulator API"}