# backend/coach/schemas.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

# ---------------------------------------------------------------------------
# Type aliases / enums
# ---------------------------------------------------------------------------

AdviceKind = Literal[
    "noop",
    "preflop_hu_chart",
    "postflop_solver",
    "equity_heuristic",
]

AdviceSourceName = Literal[
    "preflop_chart",
    "texas_solver",
    "equity_heuristic",
    "noop",
]

HeroPosition = Literal[
    "BTN",
    "SB",
    "BB",
    "UTG",
    "HJ",
    "CO",
    "unknown",
]

ActionMix = Dict[str, float]


# ---------------------------------------------------------------------------
# Context: what spot is this advice for?
# ---------------------------------------------------------------------------


@dataclass
class AdviceContext:
    """
    Normalised view of the hand state at the moment of the decision.

    This is a thin, coach-facing projection over DecisionContext. It’s meant
    to be stable for the API even if the underlying engine / DecisionContext
    grows new fields.
    """

    street: str  # "preflop" | "flop" | "turn" | "river" | "showdown" | "unknown"
    hero_position: HeroPosition
    hero_seat: int

    hero_cards: Optional[List[str]]  # e.g. ["Ah", "Kd"]
    board: List[str]  # e.g. ["7h","6c","2s"] or [] preflop

    pot_size: int  # total pot in chips BEFORE hero acts
    to_call: int  # amount hero must put in to continue
    stack_effective: Optional[int]  # effective stack vs main villain (chips)

    # Optional: what the engine says is legal right now (for UI sanity checks).
    allowed_buckets: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Recommendation: what we think hero should do?
# ---------------------------------------------------------------------------


@dataclass
class AdviceRecommendation:
    """
    The coach’s actual recommendation for this spot.

    primary_action:
        The single action we recommend the user take (already mapped to
        something meaningful to the UI, like "fold", "call", "2.5x", "75%", "jam").

    action_mix:
        Mixed strategy over the available actions, if known. Keys should
        match either engine bucket labels or UI labels.

    sizing_hint:
        Optional, mainly for raises/bets; mirrors the primary sizing the
        coach is thinking in (e.g. "2.5x", "4x", "50%", "75%", "jam").
    """

    primary_action: str
    action_mix: ActionMix = field(default_factory=dict)
    sizing_hint: Optional[str] = None


# ---------------------------------------------------------------------------
# Source / provenance: where did this advice come from?
# ---------------------------------------------------------------------------


@dataclass
class AdviceSource:
    """
    Provenance + config for the recommendation.

    source:
        High-level mechanism used to generate the advice.

    profile:
        Name of the chart / villain profile / TS config used.

    node_key:
        For solver-backed advice, the stable cache key (if any) so the
        frontend/logging can refer back to the same node.

    cached:
        Whether this result came from cache or was freshly solved.
    """

    kind: AdviceKind
    source: AdviceSourceName

    profile: Optional[str] = None  # e.g. "default_100bb_2.5x", "TAG"
    config_name: Optional[str] = None  # e.g. "hu_100bb_default"
    node_key: Optional[str] = None
    cached: Optional[bool] = None


# ---------------------------------------------------------------------------
# Optional equity annotation
# ---------------------------------------------------------------------------


@dataclass
class EquityAnnotation:
    """
    Optional equity / pot-odds summary attached to the advice.

    All fields are in [0.0, 1.0] where applicable.
    """

    hero_vs_villain_equity: Optional[float] = None
    pot_odds: Optional[float] = None
    min_equity_to_call: Optional[float] = None
    comment: Optional[str] = None  # short human-readable summary


# ---------------------------------------------------------------------------
# Raw backend details (for advanced UIs / debugging)
# ---------------------------------------------------------------------------


@dataclass
class RawStrategyDetails:
    """
    Optional raw backend details that the frontend may want for advanced
    views (matrix visualisations, solver graphing, debugging).

    You can keep this as a generic dict-of-dicts so we don't hard-bind to
    either TexasSolver JSON or chart row formats.
    """

    # For solver-backed advice (postflop)
    solver_strategy: Optional[Dict[str, Any]] = None  # e.g. full TS node dump
    solver_ev_map: Optional[Dict[str, float]] = None

    # For chart-backed advice (preflop)
    chart_row: Optional[Dict[str, Any]] = None  # raw row from PreflopChart

    # Escape hatch for anything else
    extras: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Main Advice payload (what /api/coach/advice will ultimately return)
# ---------------------------------------------------------------------------


@dataclass
class AdvicePayloadV1:
    """
    Canonical advice payload for a single decision.

    This is what the API layer should eventually serialise to JSON for the
    frontend. Different coach backends (preflop charts, solver, heuristics)
    should all be able to populate this structure.

    `street` is duplicated from `context.street` so simple consumers
    don't need to drill into `context` for the most common field.
    """

    context: AdviceContext
    recommendation: AdviceRecommendation
    source: AdviceSource

    equity: Optional[EquityAnnotation] = None
    raw: Optional[RawStrategyDetails] = None

    # Denormalised convenience field; kept at the end with a default so it
    # doesn't break existing callers.
    street: str = ""

    def __post_init__(self) -> None:
        # If street wasn't explicitly set, mirror it from the context.
        if not self.street and self.context is not None:
            self.street = self.context.street
