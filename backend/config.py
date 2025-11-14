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

# Coach / preflop advisor configuration
COACH_ENABLED: bool = _env_bool("COACH_ENABLED", "false")

# Paths to preflop chart JSON files (dev/coach only; ':' or ';' separated).
# Example:
#   PREFLOP_CHART_PATHS="devdata/charts/hu_example.json"
PREFLOP_CHART_PATHS: str = os.getenv("PREFLOP_CHART_PATHS", "").strip()

# Equity-based defend threshold for future preflop advisor heuristics.
# Declared now so docs/tests can rely on it; not yet used in the chart-only MVP.
PREFLOP_EQ_DEFEND_THRESH: float = float(os.getenv("PREFLOP_EQ_DEFEND_THRESH", "0.48"))

# Expose additional flags here as needed.
