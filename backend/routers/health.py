"""
Health check router.

Provides a simple endpoint for determining if the service is
reachable.  This can be used in CI or by monitoring systems to
verify that the API is up.  No authentication is required for
accessing this endpoint.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", summary="Service health check")
async def health() -> dict[str, str]:
    """Return a simple health check message.

    Returns:
        A JSON object containing a status key.
    """
    return {"status": "ok"}