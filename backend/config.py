# backend/config.py
"""Centralized configuration for the NLH Trainer backend.

This module parses relevant environment variables once and exposes
shared constants for other modules to import.  Parsing is done in a
consistent way to avoid duplicate logic scattered throughout the codebase.

Boolean flags treat the values '1', 'true', 'yes' and 'on' (case insensitive)
as true; anything else is false.
"""

from __future__ import annotations

import os

# Load .env if python-dotenv is installed (safe no-op otherwise)
try:
    from dotenv import load_dotenv as _load_dotenv  # type: ignore

    _load_dotenv()
except Exception:
    pass


def _env_bool(name: str, default: str = "false") -> bool:
    """Parse a boolean environment variable."""
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Core engine / autoplay
# ---------------------------------------------------------------------------

# Auto-play: when true the backend will expose POST /api/hand/auto and will
# automatically step bot actions after a human action.  When false, bot
# actions are only advanced when the frontend explicitly calls the endpoint.
HAND_AUTO_ENABLED: bool = _env_bool("HAND_AUTO_ENABLED", "false")

# Engine / bot configuration
BOT_MODE: str = os.getenv("BOT_MODE", "heuristic").strip().lower()
BOT_PROFILE: str = os.getenv("BOT_PROFILE", "CALLCHECK").strip().upper()
BOT_TIME_BUDGET_MS: int = int(os.getenv("BOT_TIME_BUDGET_MS", "150"))

# Maximum number of bot actions to apply in a single auto-advance loop.  If
# exceeded, the backend will raise an error to avoid infinite loops.
# Use BOT_MAX_STEPS to align constant and environment variable names.
BOT_MAX_STEPS: int = int(os.getenv("BOT_MAX_STEPS", "100"))

# Debug configuration
ENGINE_DEBUG_HTTP: bool = _env_bool("ENGINE_DEBUG_HTTP", "false")


# ---------------------------------------------------------------------------
# Coach / preflop advisor configuration
# ---------------------------------------------------------------------------

# Global coach gate (solver + preflop advisor). When false, coach endpoints
# respond with HTTP 501.
COACH_ENABLED: bool = _env_bool("COACH_ENABLED", "false")

# Paths to preflop chart JSON files (dev/coach only; ':' or ';' separated).
# Example:
#   PREFLOP_CHART_PATHS="devdata/charts/hu_example.json"
PREFLOP_CHART_PATHS: str = os.getenv("PREFLOP_CHART_PATHS", "").strip()

# Equity-based defend threshold used by the preflop advisor when falling
# back to an equity heuristic (e.g. BB vs SB open). If hero equity against
# the configured villain range is >= this threshold, the advisor will
# recommend a defend; otherwise it will recommend a fold (for the nodes
# that use this rule).
PREFLOP_EQ_DEFEND_THRESH: float = float(os.getenv("PREFLOP_EQ_DEFEND_THRESH", "0.48"))

# Behaviour when equity fallback cannot run (e.g. no suitable equity backend).
# When true:
#   - chart miss + fallback unavailable -> advisor raises (API returns 501).
# When false:
#   - chart miss + fallback unavailable -> advisor returns a conservative
#     recommendation (e.g. fold) but still marks source="equity" with a
#     rationale explaining that fallback was unavailable.
PREFLOP_FALLBACK_REQUIRED: bool = _env_bool("PREFLOP_FALLBACK_REQUIRED", "true")

# Expose additional flags here as needed.
