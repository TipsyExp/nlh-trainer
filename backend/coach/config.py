# backend/coach/config.py
"""
Central configuration for the coaching layer.

This module aggregates defaults from three sources (in priority order):

    1. Environment variables (highest precedence)
    2. Optional YAML file: backend/config/coach.yml
    3. Hard-coded defaults (lowest precedence)

It exposes a single immutable CoachConfig instance via get_coach_config().
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Literal, Optional
import os

try:
    import yaml  # type: ignore[import]
except Exception:  # pragma: no cover - optional dependency
    yaml = None  # type: ignore[assignment]


FallbackMode = Literal["equity", "none"]


@dataclass(frozen=True)
class CoachConfig:
    # Preflop HU charts
    hu_preflop_chart_profile: str  # e.g. "default_100bb_2.5x"

    # Postflop solver profile (TexasSolver tree / config profile name)
    hu_postflop_solver_profile: str  # e.g. "texassolver_hu_100bb_default"

    # Villain postflop range profile (used by postflop/ranges.py)
    villain_postflop_profile: str  # e.g. "TAG"

    # Global TS toggle (in addition to COACH_ENABLED / TEXASSOLVER_PATH)
    enable_texas_solver: bool

    # Fallback behaviour when TS is disabled or a spot is unsupported
    #   "equity" → use equity / heuristic coach if available
    #   "none"   → return no advice for that node
    fallback_mode: FallbackMode


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _project_root() -> Path:
    """
    Best-effort project root detection.

    We assume this file lives at: backend/coach/config.py
    So backend/ is parent, and project root is parent of backend/.
    """
    here = Path(__file__).resolve()
    backend_dir = here.parent.parent  # .../backend
    return backend_dir.parent  # project root


def _load_yaml_config() -> Dict[str, Any]:
    """
    Load backend/config/coach.yml if present and PyYAML is available.

    Returns a dict of overrides; on any error returns {}.
    """
    if yaml is None:
        return {}

    cfg_path = _project_root() / "backend" / "config" / "coach.yml"
    if not cfg_path.exists():
        return {}

    try:
        with cfg_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)  # type: ignore[no-untyped-call]
    except Exception:
        return {}

    return data if isinstance(data, dict) else {}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    s = raw.strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off"}:
        return False
    return default


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip()


def _coerce_fallback_mode(value: Any, default: FallbackMode) -> FallbackMode:
    s = str(value).strip().lower()
    if s in {"equity", "none"}:
        return s  # type: ignore[return-value]
    return default


# ---------------------------------------------------------------------------
# Build singleton config
# ---------------------------------------------------------------------------


def _build_config() -> CoachConfig:
    # Base defaults
    defaults: Dict[str, Any] = {
        "hu_preflop_chart_profile": "default_100bb_2.5x",
        "hu_postflop_solver_profile": "texassolver_hu_100bb_default",
        "villain_postflop_profile": "TAG",
        "enable_texas_solver": True,
        "fallback_mode": "equity",
    }

    # YAML overrides (if any)
    yaml_cfg = _load_yaml_config()
    merged: Dict[str, Any] = {**defaults, **yaml_cfg}

    # Env overrides (highest precedence)
    hu_preflop_chart_profile = _env_str(
        "COACH_HU_PREFLOP_CHART_PROFILE",
        str(merged["hu_preflop_chart_profile"]),
    )
    hu_postflop_solver_profile = _env_str(
        "COACH_HU_POSTFLOP_SOLVER_PROFILE",
        str(merged["hu_postflop_solver_profile"]),
    )
    villain_postflop_profile = _env_str(
        "COACH_VILLAIN_POSTFLOP_PROFILE",
        str(merged["villain_postflop_profile"]),
    )
    enable_texas_solver = _env_bool(
        "COACH_ENABLE_TEXAS_SOLVER",
        bool(merged["enable_texas_solver"]),
    )
    fallback_mode = _coerce_fallback_mode(
        os.environ.get("COACH_FALLBACK_MODE", merged["fallback_mode"]),
        "equity",
    )

    return CoachConfig(
        hu_preflop_chart_profile=hu_preflop_chart_profile,
        hu_postflop_solver_profile=hu_postflop_solver_profile,
        villain_postflop_profile=villain_postflop_profile,
        enable_texas_solver=enable_texas_solver,
        fallback_mode=fallback_mode,
    )


_COACH_CONFIG: Optional[CoachConfig] = None


def get_coach_config() -> CoachConfig:
    """Return the process-wide CoachConfig singleton."""
    global _COACH_CONFIG
    if _COACH_CONFIG is None:
        _COACH_CONFIG = _build_config()
    return _COACH_CONFIG


__all__ = [
    "CoachConfig",
    "FallbackMode",
    "get_coach_config",
]
