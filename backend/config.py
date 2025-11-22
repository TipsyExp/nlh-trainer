# backend/config.py
"""
Centralized configuration for the NLH Trainer backend.

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


def _env_int(name: str, default: str) -> int:
    """Parse an int environment variable with a safe default."""
    try:
        return int(os.getenv(name, default).strip())
    except Exception:
        return int(default)


def _env_float(name: str, default: str) -> float:
    """Parse a float environment variable with a safe default."""
    try:
        return float(os.getenv(name, default).strip())
    except Exception:
        return float(default)


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
BOT_TIME_BUDGET_MS: int = _env_int("BOT_TIME_BUDGET_MS", "150")

# Maximum number of bot actions to apply in a single auto-advance loop.  If
# exceeded, the backend will raise an error to avoid infinite loops.
# Use BOT_MAX_STEPS to align constant and environment variable names.
BOT_MAX_STEPS: int = _env_int("BOT_MAX_STEPS", "100")

# Debug configuration
ENGINE_DEBUG_HTTP: bool = _env_bool("ENGINE_DEBUG_HTTP", "false")


# ---------------------------------------------------------------------------
# Coach / advisor configuration
# ---------------------------------------------------------------------------

# Global coach gate (solver + preflop + postflop). When false, both
# /api/coach/preflop and /api/coach/advice respond with HTTP 501.
# This flag is the single source of truth for coach availability.
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
PREFLOP_EQ_DEFEND_THRESH: float = _env_float("PREFLOP_EQ_DEFEND_THRESH", "0.48")

# Behaviour when equity fallback cannot run (e.g. no suitable equity backend).
# When true:
#   - chart miss + fallback unavailable -> advisor raises (API returns 501).
# When false (default):
#   - chart miss + fallback unavailable -> advisor returns a conservative
#     recommendation (e.g. fold) but still marks source="equity" with a
#     rationale explaining that fallback was unavailable.
PREFLOP_FALLBACK_REQUIRED: bool = _env_bool("PREFLOP_FALLBACK_REQUIRED", "false")

# Postflop coach (HU / multiway equity-based coach) configuration.
# This controls the postflop path used by /api/coach/advice.

# Global postflop coach gate. When false, /api/coach/advice will never
# attempt equity-based postflop advice and will instead return status
# "unsupported" for all postflop spots.
POSTFLOP_COACH_ENABLED: bool = _env_bool("POSTFLOP_COACH_ENABLED", "true")

# Default Monte Carlo iterations for postflop coach equity calls when not
# overridden by internal heuristics.
POSTFLOP_COACH_ITERS: int = _env_int("POSTFLOP_COACH_ITERS", "20000")

# Optional soft timeout (milliseconds) for postflop coach equity calls.
# 0 disables the dedicated postflop timeout (backends may still use their
# own defaults or the global EQUITY_TIMEOUT_MS).
POSTFLOP_COACH_TIMEOUT_MS: int = _env_int("POSTFLOP_COACH_TIMEOUT_MS", "0")

# Default villain profile / range family used by the postflop coach.
# For example: "TAG", "CALLCHECK", etc. Interpretation is owned by
# backend/coach/postflop/ranges.py.
POSTFLOP_COACH_PROFILE: str = os.getenv("POSTFLOP_COACH_PROFILE", "TAG").strip().upper()

# Multiway-specific toggles for the postflop coach. When disabled, the coach
# will treat multiway spots as unsupported even if the underlying equity
# backend can handle them.
POSTFLOP_COACH_MULTIWAY_ENABLED: bool = _env_bool(
    "POSTFLOP_COACH_MULTIWAY_ENABLED",
    "true",
)

# Default iterations / timeout for multiway equity calls, overridable per
# request. Defaults are slightly higher than HU due to slower convergence.
POSTFLOP_COACH_MULTIWAY_ITERS: int = _env_int(
    "POSTFLOP_COACH_MULTIWAY_ITERS",
    "30000",
)

# Policy for selecting / constraining backends in multiway coach calls.
# For now this is informational; the coach primarily relies on
# EQUITY_BACKEND_POLICY but this allows future overrides such as
# "ompeval_only" or "disabled".
POSTFLOP_COACH_MULTIWAY_POLICY: str = (
    os.getenv(
        "POSTFLOP_COACH_MULTIWAY_POLICY",
        "auto",
    )
    .strip()
    .lower()
)


# ---------------------------------------------------------------------------
# Equity engine configuration (selection / defaults)
# ---------------------------------------------------------------------------

# Backend selection policy for the equity service.
# Values: 'auto', 'ompeval', 'eval7', 'pokerkit'
# - 'auto' tries ompeval -> eval7 -> pokerkit in that order.
EQUITY_BACKEND_POLICY: str = os.getenv("EQUITY_BACKEND_POLICY", "auto").strip().lower()

# Default Monte Carlo iterations when a request does not provide `iters`.
# Keep small enough for CI; callers can override per-request.
EQUITY_ITERS: int = _env_int("EQUITY_ITERS", "20000")

# Optional global timeout hint (milliseconds) for equity computations.
# Backends treat this as best-effort; 0 disables timeout.
EQUITY_TIMEOUT_MS: int = _env_int("EQUITY_TIMEOUT_MS", "0")

# Number of threads for multi-threaded backends (e.g., OMPEval).
# 0 means "auto" (use hardware concurrency / backend default).
EQUITY_THREADS: int = _env_int("EQUITY_THREADS", "0")

# Optional Monte Carlo standard error target. If > 0, backends that support
# progressive sampling may stop early once stderr <= target. 0 disables.
EQUITY_STDERR_TARGET: float = _env_float("EQUITY_STDERR_TARGET", "0")

# Optional RNG seed for backends that expose seeding. Empty string means unset.
EQUITY_SEED: str = os.getenv("EQUITY_SEED", "").strip()


# ---------------------------------------------------------------------------
# Logging / snapshot configuration
# ---------------------------------------------------------------------------

# When true, successful equity calculations tied to a specific hand/index
# may be persisted as JSON snapshots and surfaced in exports.
LOG_EQUITY_SNAPSHOT: bool = _env_bool("LOG_EQUITY_SNAPSHOT", "false")

# When true, preflop advisor responses (chart or equity-based) tied to a
# specific hand/index may be persisted and surfaced in exports.
LOG_PREFLOP_ADVICE: bool = _env_bool("LOG_PREFLOP_ADVICE", "false")

# When true, the unified coach advice payload (AdviceV1) returned by
# /api/coach/advice may be persisted per decision (all streets) and
# surfaced in exports as coach_advice. This is independent of legacy
# preflop advice and equity snapshot logging.
LOG_COACH_ADVICE: bool = _env_bool("LOG_COACH_ADVICE", "false")

# Optional redaction knob for equity snapshots. When true, callers that
# log equity snapshots should avoid storing raw card/range detail and
# instead prefer abstracted identifiers (e.g. hand keys, range profile
# names). Behaviour is enforced by callers; this flag is intentionally
# conservative and defaults to false.
LOG_EQUITY_SNAPSHOT_REDACT: bool = _env_bool("LOG_EQUITY_SNAPSHOT_REDACT", "false")

# Expose additional flags here as needed.


# ---------------------------------------------------------------------------
# CORS configuration
# ---------------------------------------------------------------------------


def _csv_env(name: str, default: str = "") -> list[str]:
    """
    Parse a comma-separated environment variable into a list of strings.

    Strips whitespace from each entry and excludes empty strings.

    Args:
        name: Environment variable to read.
        default: Default value if the variable is not set.

    Returns:
        A list of strings.
    """
    raw = os.getenv(name, default)
    return [s.strip() for s in raw.split(",") if s.strip()]


class Config:
    """
    Configuration snapshot for the backend.

    This class centralizes configuration for runtime options that may be
    consumed outside of this module.  Instantiating ``Config`` captures
    environment variables at that moment.
    """

    def __init__(self) -> None:
        # Re-expose selected flags from the module namespace for convenience.
        self.COACH_ENABLED: bool = COACH_ENABLED

        # CORS settings
        self.CORS_ALLOW_ORIGINS: list[str] = _csv_env(
            "CORS_ALLOW_ORIGINS", "http://localhost:3000"
        )
        self.CORS_ALLOW_CREDENTIALS: bool = (
            os.getenv("CORS_ALLOW_CREDENTIALS", "false").lower() == "true"
        )
        self.CORS_ALLOW_METHODS: list[str] = _csv_env(
            "CORS_ALLOW_METHODS", "GET,POST,OPTIONS"
        )
        self.CORS_ALLOW_HEADERS: list[str] = _csv_env(
            "CORS_ALLOW_HEADERS", "Authorization,Content-Type"
        )


def get_config() -> Config:
    """
    Return a fresh ``Config`` instance with values loaded from environment variables.

    Callers should prefer accessing configuration flags directly from this
    instance rather than reading environment variables themselves.
    """
    return Config()
