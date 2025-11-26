# backend/coach/annotations/equity.py
"""
Helpers for attaching simple equity / pot-odds annotations to advice.

This module does **not** talk to any equity engine directly. Instead, it
takes pre-computed hero equity (vs a villain range) plus pot / to_call
information and produces an EquityAnnotation suitable for attaching to an
AdvicePayloadV1.

Typical flow:

    - Some upstream adapter (equity engine, solver, etc.) computes
      hero_vs_villain_equity in [0.0, 1.0].

    - The orchestrator passes that equity, together with pot size and
      to_call from the DecisionContext, into `make_equity_annotation(...)`.

    - The returned EquityAnnotation (if any) is attached to the advice.

Keeping this logic here allows you to:
    * Reuse consistent pot-odds maths across all coaches.
    * Centralise the human-readable “Equity X% vs req Y%” comment.
"""

from __future__ import annotations

from typing import Optional

from backend.coach.schemas import EquityAnnotation


def compute_pot_odds(to_call: int, pot_size: int) -> float:
    """
    Compute pot odds as a fraction in [0.0, 1.0].

    Definition here follows the standard "minimum equity to call" form:

        pot_odds = to_call / (pot_size + to_call)

    Where:
        - to_call: amount hero must put in to continue (chips).
        - pot_size: current pot before calling (chips).

    If `to_call <= 0` (check / all-in spot, etc.) or pot_size < 0, returns 0.0.
    """
    if to_call <= 0 or pot_size < 0:
        return 0.0

    denom = pot_size + to_call
    if denom <= 0:
        return 0.0

    v = to_call / float(denom)
    # Clamp to [0, 1] to be safe against weird inputs.
    return max(0.0, min(1.0, v))


def _format_pct(x: float) -> str:
    """Format a 0–1 float as a percentage string with one decimal place."""
    return f"{x * 100:.1f}%"


def make_equity_annotation(
    *,
    hero_equity: Optional[float],
    pot_size: int,
    to_call: int,
) -> Optional[EquityAnnotation]:
    """
    Build an EquityAnnotation from hero equity and pot/to_call.

    Args:
        hero_equity:
            Hero's equity vs villain range in [0.0, 1.0]. If None, no
            annotation is produced and the function returns None.

        pot_size:
            Current pot size in chips *before* hero acts.

        to_call:
            Amount hero must put in to continue.

    Returns:
        EquityAnnotation or None if no useful annotation can be made.

    Behaviour:
        - Computes pot_odds = to_call / (pot_size + to_call).
        - Sets min_equity_to_call = pot_odds.
        - Generates a short comment comparing hero_equity vs min_equity_to_call.
    """
    if hero_equity is None:
        return None

    # Normalise hero equity to [0, 1].
    e = max(0.0, min(1.0, float(hero_equity)))

    pot_odds = compute_pot_odds(to_call=to_call, pot_size=pot_size)
    min_eq = pot_odds  # under our definition, these are the same quantity

    # Simple text summary
    # If there is nothing to call, we still attach a neutral comment.
    if to_call <= 0:
        comment = (
            f"Equity {_format_pct(e)}; no call required in this spot "
            "(check / auto-continue)."
        )
    else:
        # Compare equity vs required equity with a small tolerance to avoid
        # flip-flopping around the equal line.
        eps = 0.01  # 1 percentage point

        diff = e - min_eq
        if diff > eps:
            comment = (
                f"Equity {_format_pct(e)} vs required {_format_pct(min_eq)}; "
                "continuing is profitable in theory."
            )
        elif diff < -eps:
            comment = (
                f"Equity {_format_pct(e)} vs required {_format_pct(min_eq)}; "
                "continuing would be losing in theory."
            )
        else:
            comment = (
                f"Equity {_format_pct(e)} vs required {_format_pct(min_eq)}; "
                "this spot is roughly breakeven."
            )

    return EquityAnnotation(
        hero_vs_villain_equity=e,
        pot_odds=pot_odds,
        min_equity_to_call=min_eq,
        comment=comment,
    )


__all__ = [
    "compute_pot_odds",
    "make_equity_annotation",
]
