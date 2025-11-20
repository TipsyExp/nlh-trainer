# backend/schemas/advice.py
from __future__ import annotations

from typing import List, Optional, Literal

from pydantic import BaseModel, Field


# -------------------------
# Core types for the unified Advice payload
# -------------------------


AdviceStatus = Literal["ok", "disabled", "unsupported", "not_found", "timeout", "error"]


class StrategyPart(BaseModel):
    """
    Single segment of a strategy distribution.

    Each entry represents an action label and the fraction of time that action
    should be taken in this spot.  The trainer frontend maps these into
    percentage widths for the strategy bar.
    """

    action: str = Field(
        ...,
        description="Bucket/action label, e.g. 'fold', 'call', '2.5x', 'jam'.",
    )
    weight: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Probability weight in [0,1] for this action.",
    )


class AdviceMeta(BaseModel):
    """
    Minimal, street-agnostic description of the decision.

    This is the part of the payload that tells the UI where the advice applies
    (street, hero seat, number of players) and how it was produced.
    """

    street: Literal["preflop", "flop", "turn", "river", "showdown", "unknown"] = Field(
        ...,
        description="Street at which the decision occurs.",
    )
    n_players: int = Field(
        ...,
        ge=0,
        description="Number of players still in the hand at this decision.",
    )
    hero_seat: int = Field(
        ...,
        ge=0,
        description="Seat index of the hero (human) player.",
    )
    source: str = Field(
        ...,
        description=(
            "Origin of the advice, e.g. 'chart', 'equity', 'rule', 'mixed', "
            "or another backend-specific label."
        ),
    )


class AdviceRecommendation(BaseModel):
    """
    Recommended action and optional strategy distribution.

    The 'bucket' identifies the primary recommendation.  The optional
    'strategy_bar' provides a more detailed mixed strategy that can be rendered
    as a bar chart on the frontend.
    """

    bucket: str = Field(
        ...,
        description=(
            "Primary recommended bucket, e.g. 'fold', 'call', 'check', "
            "'2.5x', '2.5xR', 'jam'."
        ),
    )
    strategy_bar: Optional[List[StrategyPart]] = Field(
        default=None,
        description="Optional list of (action, weight) entries for a mixed strategy.",
    )


class AdviceEquityPlayer(BaseModel):
    """
    Per-player equity entry.

    Used when the coach computes equities for multiple players (hero + villains).
    """

    seat: int = Field(
        ...,
        ge=0,
        description="Seat index for this player.",
    )
    equity: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Normalized equity for this player in [0,1].",
    )


class AdviceEquity(BaseModel):
    """
    Optional equity block attached to advice.

    This mirrors the essential parts of /api/equity responses but is adapted for
    per-decision coaching (hero-centric).
    """

    backend: Optional[str] = Field(
        default=None,
        description="Name of the equity backend used (e.g. 'ompeval').",
    )
    mode: Optional[Literal["hands", "ranges"]] = Field(
        default=None,
        description="Equity mode: 'hands' for fixed hands, 'ranges' for ranges.",
    )
    hero: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Hero's equity in [0,1] against the current field.",
    )
    players: Optional[List[AdviceEquityPlayer]] = Field(
        default=None,
        description="Optional list of per-player equities (including hero).",
    )
    vs_field: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Hero equity vs everyone else combined, when available.",
    )
    exact: Optional[bool] = Field(
        default=None,
        description="Whether the result is exact enumeration (True) or Monte Carlo (False).",
    )
    iters: Optional[int] = Field(
        default=None,
        ge=0,
        description="Effective number of Monte Carlo iterations (if applicable).",
    )


class AdviceThresholds(BaseModel):
    """
    Optional threshold hints used in the rationale.

    These values help the UI and logs explain *why* a recommendation was made
    (e.g. comparing hero equity to required pot odds).
    """

    pot_odds: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Required equity in [0,1] to continue (e.g. call) given the current price.",
    )
    spr: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Stack-to-pot ratio at this decision (hero effective stack / pot).",
    )


class AdviceV1Model(BaseModel):
    """
    Canonical shape for coach advice responses (version 1).

    This model backs the /api/coach/advice endpoint and any snapshots attached
    to exports.  All-streets, all-player-counts advice should conform to this
    schema, with optional blocks omitted when not applicable.

    See docs/COACH-ADVICE-PAYLOAD.md for the narrative specification.
    """

    # Use Literal[1] to make the version effectively constant while keeping
    # mypy and pydantic happy.
    version: Literal[1] = Field(
        1,
        description="Advice payload version.  Current version is 1.",
    )
    status: AdviceStatus = Field(
        ...,
        description=(
            "'ok' when advice is actionable; other values indicate disabled, "
            "unsupported or error states."
        ),
    )
    meta: AdviceMeta = Field(
        ...,
        description="Street- and seat-level context describing where this advice applies.",
    )
    recommendation: Optional[AdviceRecommendation] = Field(
        default=None,
        description="Recommended bucket and optional mixed strategy.",
    )
    equity: Optional[AdviceEquity] = Field(
        default=None,
        description="Optional hero/players equity information backing the advice.",
    )
    thresholds: Optional[AdviceThresholds] = Field(
        default=None,
        description="Optional pot-odds / SPR thresholds used in the rationale.",
    )
    rationale: Optional[str] = Field(
        default=None,
        description="Human-readable explanation of the recommendation.",
    )

    class Config:
        # Be tolerant of extra fields from older/newer backends.
        extra = "ignore"
