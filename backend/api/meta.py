# backend/api/meta.py
"""
Meta capabilities endpoint.

This module exposes a small `/api/meta` endpoint that the frontend uses to
discover backend capabilities (equity + coach).  It is intentionally cheap to
compute and stable in shape.

The returned JSON is the canonical source for:
  - whether coaching is enabled,
  - whether the unified advice route is available and which version it speaks,
  - basic equity capabilities (policy/backend name, range support, max players).

See:
  - docs/API-CONTRACT.md
  - docs/COACH-ADVICE-PAYLOAD.md
  - docs/CONFIGURATION.md
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.config import COACH_ENABLED, EQUITY_BACKEND_POLICY

router = APIRouter(tags=["meta"])


def _coach_meta() -> Dict[str, Any]:
    """
    Build the coach capability block.

    Notes:
      - `enabled` mirrors COACH_ENABLED gating.
      - `advice_route` reflects that /api/coach/advice is mounted.
      - `advice_version` matches AdviceV1.version (currently 1).
    """
    enabled = bool(COACH_ENABLED)
    return {
        "enabled": enabled,
        "advice_route": True,  # this module is present → route is intended to be live
        "advice_version": 1,
    }


def _equity_meta() -> Dict[str, Any]:
    """
    Build the equity capability block.

    This is deliberately conservative and based primarily on configuration. Where
    possible you can later extend this to introspect the active EquityService
    (e.g. default backend, real max player count).  The current fields are:

      - backend:         name/policy configured (for display only).
      - policy:          raw EQUITY_BACKEND_POLICY value.
      - supports_ranges: frontend hint for range inputs (true for policies that
                         *can* support ranges when the right backend is present).
      - max_players:     soft upper bound for equity calls (UI hint only).

    The overlay treats these as hints; failures at /api/equity are still handled
    gracefully.
    """
    policy = (EQUITY_BACKEND_POLICY or "auto").lower()

    # Heuristic: policies that *can* support ranges when the backend is present.
    supports_ranges = policy in {"auto", "ompeval", "eval7"}

    # OMPEval supports up to 6 players; other backends may support fewer.
    # Use 6 as a soft hint so the UI is willing to attempt multiway where
    # backends are available; /api/equity will still guard unsupported cases.
    max_players = 6

    return {
        "backend": policy,
        "policy": policy,
        "supports_ranges": supports_ranges,
        "max_players": max_players,
    }


@router.get("/meta")
def get_meta() -> JSONResponse:
    """
    Return a snapshot of backend capabilities.

    Example shape:

      {
        "coach": {
          "enabled": true,
          "advice_route": true,
          "advice_version": 1
        },
        "equity": {
          "backend": "auto",
          "policy": "auto",
          "supports_ranges": true,
          "max_players": 6
        }
      }

    Frontend types in `frontend/types/meta.ts` should mirror this structure.
    """
    payload: Dict[str, Any] = {
        "coach": _coach_meta(),
        "equity": _equity_meta(),
    }
    return JSONResponse(payload, status_code=200)
