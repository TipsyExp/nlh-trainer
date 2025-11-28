# backend/coach/policies/preflop_hu_chart_policy.py
"""
Heads-up preflop policy driven by HU charts.

This module sits between:

  * a HU chart loader (abstracted via `load_hu_chart`), and
  * higher-level coaching logic (orchestrator, tests).

It provides two layers:

  1) A simple functional API used by existing tests:
       - load_hu_chart(profile)
       - get_hu_preflop_advice(ctx, profile=...)
       - get_hu_preflop_recommendation(ctx, profile=...)  (alias)

  2) A small class wrapper that orchestrator code may use:
       - PreflopHUChartPolicy.build_advice(ctx) -> dict | None
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, List
import random

from backend.coach.decision_context import DecisionContext
from backend.coach.preflop.charts import canonicalize_hand

# Default profile name used by tests and config.
DEFAULT_PROFILE_NAME = "default_100bb_2.5x"


# ---------------------------------------------------------------------------
# Internal helpers / data structures
# ---------------------------------------------------------------------------


@dataclass
class PreflopHUAdvice:
    """
    Lightweight advice object used by tests and internal callers.
    """

    node: str
    hand_key: str
    bucket_mix: Dict[str, float]
    recommended_bucket: Optional[str]
    raw_chart: Optional[Any] = None

    @property
    def action_mix(self) -> Dict[str, float]:
        """
        Backwards-compatible alias used by some older tests / callers.
        """
        return self.bucket_mix


def _normalise_distribution(raw: Mapping[str, float]) -> Dict[str, float]:
    """
    Normalise a mapping of action -> non-negative weight into
    a proper probability distribution.

    If all weights are zero or negative, fall back to a uniform
    distribution over the keys.
    """
    cleaned: Dict[str, float] = {}
    for k, v in raw.items():
        try:
            fv = float(v)
        except Exception:
            fv = 0.0
        cleaned[k] = fv if fv > 0.0 else 0.0

    total = sum(cleaned.values())
    if total > 0.0:
        return {k: v / total for k, v in cleaned.items()}

    if not cleaned:
        return {}

    n = float(len(cleaned))
    return {k: 1.0 / n for k in cleaned.keys()}


def _sample_from_distribution(
    dist: Mapping[str, float], rng: random.Random
) -> Optional[str]:
    """
    Sample a single key from a probability distribution mapping.
    Returns None if the distribution is empty.
    """
    items = list(dist.items())
    if not items:
        return None

    r = rng.random()
    cumulative = 0.0
    for action_id, p in items:
        cumulative += p
        if r <= cumulative:
            return action_id
    # Numerical edge case: return last action
    return items[-1][0]


def _infer_node_id(ctx: DecisionContext) -> Optional[str]:
    """
    Very coarse mapping from DecisionContext → HU preflop node id.

    v1 behaviour:
      - HU only.
      - If hero is the button → "BTN_open".
      - If hero is BB → "BB_vs_BTN_open".
    """
    if ctx.street != "preflop":
        return None
    if ctx.n_players != 2:
        return None

    if ctx.hero_seat == ctx.button:
        return "BTN_open"
    if ctx.hero_seat == ctx.bb_seat:
        return "BB_vs_BTN_open"

    return None


# ---------------------------------------------------------------------------
# Chart loading (function form so tests can monkeypatch it)
# ---------------------------------------------------------------------------


def load_hu_chart(profile: str = DEFAULT_PROFILE_NAME) -> Any:
    """
    Load a single HU preflop chart for the given profile.

    In production, this delegates to backend.coach.preflop.hu_charts.load_default_chart_set()
    and selects the first chart for the requested profile.

    In tests, this function is commonly monkeypatched.
    """
    try:
        from backend.coach.preflop.hu_charts import load_default_chart_set
    except Exception:
        # Charts not wired up (older build / missing dependency).
        return None

    chart_set = load_default_chart_set()

    # Preferred API: HUChartSet.charts_for_profile
    charts: List[Any]
    try:
        charts = chart_set.charts_for_profile(profile)  # type: ignore[attr-defined]
    except Exception:
        # Fallback: treat HUChartSet as an iterable of charts
        try:
            charts = list(chart_set)  # type: ignore[arg-type]
        except Exception:
            return None

    if not charts:
        return None

    # For v1 we only need a single chart.
    return charts[0]


# ---------------------------------------------------------------------------
# Public functional API used by tests / simple callers
# ---------------------------------------------------------------------------


def get_hu_preflop_advice(
    ctx: DecisionContext,
    profile: str = DEFAULT_PROFILE_NAME,
    rng: Optional[random.Random] = None,
) -> Optional[PreflopHUAdvice]:
    """
    Main functional entrypoint for HU preflop chart advice.
    """
    if ctx.street != "preflop":
        return None
    if ctx.n_players != 2:
        return None

    if not ctx.hero_hole_cards or len(ctx.hero_hole_cards) != 2:
        return None

    node_id = _infer_node_id(ctx)
    if node_id is None:
        return None

    # Canonicalise hero's holding, e.g. ["As","Kd"] -> "AKo"
    hand_key = canonicalize_hand(ctx.hero_hole_cards)  # type: ignore[arg-type]

    try:
        chart = load_hu_chart(profile)
    except Exception:
        # If charts are not wired up yet, just say “no advice”.
        return None

    if chart is None:
        return None

    # chart is expected to be a PreflopChart-like object with lookup/lookup_mix
    from typing import Mapping as _Mapping  # local alias only

    raw_mix: Optional[_Mapping[str, float]]
    if hasattr(chart, "lookup_mix"):
        raw_mix = chart.lookup_mix(node_id, hand_key)  # type: ignore[call-arg]
    else:
        row = chart.lookup(node_id, hand_key)  # type: ignore[call-arg]
        if row is None:
            raw_mix = None
        else:
            strategy_bar = getattr(row, "strategy_bar", None)
            if isinstance(strategy_bar, _Mapping):
                raw_mix = strategy_bar
            elif isinstance(row, _Mapping):
                raw_mix = row
            else:
                raw_mix = None

    if not raw_mix:
        return None

    bucket_mix = _normalise_distribution(raw_mix)

    # Sample a recommended bucket using a local RNG (or provided one)
    local_rng = rng or random.Random()
    chosen = _sample_from_distribution(bucket_mix, local_rng)

    return PreflopHUAdvice(
        node=node_id,
        hand_key=hand_key,
        bucket_mix=bucket_mix,
        recommended_bucket=chosen,
        raw_chart=chart,
    )


def get_hu_preflop_recommendation(
    ctx: DecisionContext,
    profile: str = DEFAULT_PROFILE_NAME,
    rng: Optional[random.Random] = None,
) -> Optional[PreflopHUAdvice]:
    """
    Backwards-compatible alias for get_hu_preflop_advice.
    """
    return get_hu_preflop_advice(ctx, profile=profile, rng=rng)


# ---------------------------------------------------------------------------
# Orchestrator-facing class wrapper (optional)
# ---------------------------------------------------------------------------


class PreflopHUChartPolicy:
    """
    Small wrapper that higher-level orchestration code can use.
    """

    def __init__(
        self,
        profile: str = DEFAULT_PROFILE_NAME,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.profile = profile
        self._rng = rng or random.Random()

    def build_advice(self, ctx: DecisionContext) -> Optional[Dict[str, Any]]:
        # Be tolerant of older test monkeypatches that define
        # get_hu_preflop_advice(ctx, profile) without an `rng` parameter.
        try:
            adv = get_hu_preflop_advice(ctx, profile=self.profile, rng=self._rng)
        except TypeError:
            adv = get_hu_preflop_advice(ctx, profile=self.profile)

        if adv is None:
            return None

        # Ensure we always have a recommended bucket (argmax fallback)
        recommended = adv.recommended_bucket
        if recommended is None and adv.bucket_mix:
            recommended = max(adv.bucket_mix.items(), key=lambda kv: kv[1])[0]

        return {
            "kind": "preflop_hu_chart",
            "source": "preflop_hu_chart_v1",
            "node": adv.node,
            "hand_key": adv.hand_key,
            "recommended_bucket": recommended,
            "strategy": dict(adv.bucket_mix),
            "profile": self.profile,
        }


__all__ = [
    "DEFAULT_PROFILE_NAME",
    "PreflopHUAdvice",
    "load_hu_chart",
    "get_hu_preflop_advice",
    "get_hu_preflop_recommendation",
    "PreflopHUChartPolicy",
]
