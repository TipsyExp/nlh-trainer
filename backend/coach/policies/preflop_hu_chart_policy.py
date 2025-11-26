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

     This API:
       - inspects a DecisionContext,
       - canonicalises hero's hole cards (e.g. ["As","Kd"] → "AKo"),
       - looks up a mix in the chart for the inferred node,
       - returns a small advice object exposing `.bucket_mix` /
         `.action_mix`.

  2) A small class wrapper that orchestrator code *may* use:
       - PreflopHUChartPolicy.build_advice(ctx) -> dict | None

     This wraps `get_hu_preflop_advice` and converts the result into
     a JSON-friendly dict of the shape the orchestrator expects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional
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

    Attributes:
        node:
            String identifier for the preflop node (e.g. "BTN_open").

        hand_key:
            Canonical hand key such as "AKo", "J9s", "TT".

        bucket_mix:
            Mapping from abstract bucket/action id -> probability in [0, 1].

        recommended_bucket:
            The argmax bucket id from bucket_mix (or None if mix is empty).

        raw_chart:
            Optional underlying chart object (for debugging / tracing).
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

    # Fallback: uniform across actions if we have no positive mass
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
      - Otherwise return None.
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


def _extract_mix_from_chart(
    chart: Any, node_id: str, hand_key: str
) -> Optional[Dict[str, float]]:
    """
    Try several common chart APIs to obtain a bucket/action mix for
    (node_id, hand_key).

    Supports:
      - chart.lookup_mix(node, hand_key) -> dict
      - chart.lookup(node, hand_key) -> row with .strategy_bar
      - chart.lookup(node, hand_key) -> dict

    Tests inject a DummyChart with a compatible API via monkeypatching
    `load_hu_chart`.
    """
    # 1) Explicit mix helper, if provided.
    if hasattr(chart, "lookup_mix"):
        mix = chart.lookup_mix(node_id, hand_key)  # type: ignore[call-arg]
        if isinstance(mix, Mapping):
            return {str(k): float(v) for k, v in mix.items()}

    # 2) Generic lookup returning a row object or dict.
    if hasattr(chart, "lookup"):
        row = chart.lookup(node_id, hand_key)  # type: ignore[call-arg]
        if row is None:
            return None

        # a) Row with strategy_bar attribute (PreflopChart-like)
        strategy_bar = getattr(row, "strategy_bar", None)
        if isinstance(strategy_bar, Mapping):
            return {str(k): float(v) for k, v in strategy_bar.items()}

        # b) Row itself is a dict
        if isinstance(row, Mapping):
            return {str(k): float(v) for k, v in row.items()}

    return None


# ---------------------------------------------------------------------------
# Chart loading (function form so tests can monkeypatch it)
# ---------------------------------------------------------------------------


def load_hu_chart(profile: str = DEFAULT_PROFILE_NAME) -> Any:
    """
    Load a single HU preflop chart for the given profile.

    **Important:** In tests, this function is monkeypatched to return a
    DummyChart with the expected API.

    In production code you can wire this up to:

      * the YAML-backed HU charts in backend.coach.preflop.hu_charts, or
      * any other chart representation that supports either:
            - lookup_mix(node_id, hand_key) -> {bucket: freq, ...}
            - lookup(node_id, hand_key) -> row with .strategy_bar
            - lookup(node_id, hand_key) -> {bucket: freq, ...}

    For now, the default implementation is a stub that signals “no chart”.
    """
    raise RuntimeError("HU preflop charts are not wired up yet")


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

    Behaviour (v1):

      - Ignore non-preflop or non-HU spots (return None).
      - Require hero_hole_cards to be present; otherwise return None.
      - Infer a coarse node_id from the DecisionContext.
      - Load the HU chart for the given profile via load_hu_chart().
      - Look up the action/bucket mix for (node_id, hand_key).
      - Normalise and sample a recommended bucket.
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

    raw_mix = _extract_mix_from_chart(chart, node_id, hand_key)
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

    Some older test code refers to this name; we keep it to avoid
    breaking imports.
    """
    return get_hu_preflop_advice(ctx, profile=profile, rng=rng)


# ---------------------------------------------------------------------------
# Orchestrator-facing class wrapper (optional)
# ---------------------------------------------------------------------------


class PreflopHUChartPolicy:
    """
    Small wrapper that higher-level orchestration code can use.

    Example:

        policy = PreflopHUChartPolicy(profile="default_100bb_2.5x")
        advice_dict = policy.build_advice(ctx)

    build_advice(ctx) returns either:

      - None              -> no advice for this spot
      - dict(...)         -> JSON-friendly payload including:
            {
              "kind": "preflop_hu_chart",
              "source": "preflop_hu_chart_v1",
              "node": "...",
              "hand_key": "...",
              "recommended_bucket": "...",
              "strategy": { ... },
              "profile": "default_100bb_2.5x",
            }
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
            # profile name can be useful for debugging / UI
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
