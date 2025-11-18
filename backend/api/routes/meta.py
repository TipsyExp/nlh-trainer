# backend/api/routes/meta.py
"""
Meta API route for exposing backend capabilities and coach configuration.

This module defines a lightweight endpoint for the frontend to discover
supported functionality without making trial calls.  The response includes
information about the equity backend (e.g. which implementation is
currently selected and whether it supports ranges or multi‐way play) and
whether the coach feature is enabled.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.services.equity.service import EquityService
from backend.config import COACH_ENABLED  # reuse existing configuration flag


router = APIRouter(tags=["meta"])


@router.get("/meta")
def get_meta() -> dict:
    """Return a capability snapshot for the frontend.

    The equity section reflects the currently selected backend and its
    supported features.  The coach section simply reports whether the
    coach endpoints are enabled via configuration.

    Returns:
        A dictionary with two keys:
        - ``equity``: capability details for the equity engine.
        - ``coach``: a single ``enabled`` boolean flag.
    """
    svc = EquityService()
    eq_caps = svc.capabilities()
    return {
        "equity": eq_caps,
        "coach": {"enabled": bool(COACH_ENABLED)},
    }
