# backend/coach/node_builder.py
"""
Solver node builder for /api/coach/advice.

This module converts a backend "decision" (hand_id, idx) into a
TexasSolver-compatible SolveRequest. It is intentionally conservative:

  * Only postflop HU spots are currently supported.
  * Preflop raises UnsupportedSpotError.
  * Stacks default to a sane placeholder when not available.

The key design change for M3 is that this builder now relies on the shared
DecisionContext helper instead of re-deriving state from the HTTP layer
(`/api/hand/state`). All solver-based coaching should ultimately consume
DecisionContext so that preflop advisor, postflop coach and exports share a
single understanding of the spot.

See:
  - backend/coach/decision_context.py
  - backend/schemas/advice.py
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from backend.adapters.solver.texassolver_adapter import (
    SolveRequest,
    UnsupportedSpotError,
)
from backend.coach.decision_context import DecisionContext, build_decision_context


def _detect_ip_oop_seats_from_ctx(ctx: DecisionContext) -> Tuple[int, int]:
    """
    Heads-up postflop: Button acts in position (IP); the other is OOP.

    Uses the underlying engine table snapshot from the decision context.
    """
    raw_state = ctx.raw_state
    table = getattr(raw_state, "table", None)
    btn = getattr(table, "button", None) if table is not None else None
    seats = getattr(table, "seats", None) if table is not None else None

    if not isinstance(btn, int):
        raise UnsupportedSpotError("button seat unknown")

    if not isinstance(seats, int):
        seats = 2  # conservative HU default if table metadata is incomplete

    # In HU we expect seats == 2 and seat indexes 0..(seats-1).
    if seats != 2:
        raise UnsupportedSpotError("only heads-up supported for coach")

    ip_seat = btn
    # Opponent seat in a 2-handed game: the other index in {0,1}.
    oop_seat = 1 - ip_seat
    return ip_seat, oop_seat


def _chip_stack_for_seat(ctx: DecisionContext, seat: int) -> Optional[int]:
    """
    Try to read chips-behind for a given seat from the engine snapshot.

    Falls back to None if unavailable; callers should substitute a sane
    default (e.g. 10000) in that case. This mirrors the previous
    behaviour that inspected the public state dict.
    """
    raw_state = ctx.raw_state
    players = getattr(raw_state, "players", []) or []
    if seat < 0 or seat >= len(players):
        return None

    p = players[seat]
    keys = ("stack", "chips", "behind")

    if isinstance(p, dict):
        for k in keys:
            v = p.get(k)
            if isinstance(v, int):
                return v
    else:
        for k in keys:
            v = getattr(p, k, None)
            if isinstance(v, int):
                return v
    return None


def _flatten_board(ctx: DecisionContext) -> List[str]:
    """
    Return a shallow copy of the board cards.

    DecisionContext.board is already a flat list in flop→turn→river order,
    but this helper keeps the caller insulated from internal representation.
    """
    return list(ctx.board)


def build_solve_request_from_hand(hand_id: str, idx: int) -> SolveRequest:
    """
    Build a minimal, deterministic SolveRequest for **postflop HU**.

    Current scope:
      - Uses DecisionContext built from the active engine state.
      - Supports only flop/turn/river streets.
      - Requires exactly two seats (HU) based on table metadata.
      - Uses conservative placeholder ranges & buckets.

    Preflop remains unsupported: callers should rely on the preflop advisor
    rather than the solver path for now.
    """
    # Build a shared decision context from the engine snapshot. Any failure
    # to obtain context is treated as "unsupported" to keep the API contract
    # simple for /api/coach/advice.
    try:
        ctx = build_decision_context(hand_id=hand_id, idx=idx)
    except Exception as e:  # pragma: no cover - mapped to UnsupportedSpotError
        raise UnsupportedSpotError(f"decision context unavailable: {e}") from e

    street = ctx.street
    if street not in ("flop", "turn", "river"):
        # Task scope: preflop unsupported to avoid mixing solver and chart logic.
        raise UnsupportedSpotError("preflop not supported")

    board = _flatten_board(ctx)
    pot = int(ctx.pot_total)

    # Seats (IP = button on postflop)
    ip_seat, oop_seat = _detect_ip_oop_seats_from_ctx(ctx)

    # Stacks behind — if unknown, fall back to a conservative default.
    ip_stack = _chip_stack_for_seat(ctx, ip_seat)
    oop_stack = _chip_stack_for_seat(ctx, oop_seat)
    if ip_stack is None or oop_stack is None:
        # Use a conservative default; the engine will snap bet sizes anyway.
        ip_stack = ip_stack or 10000
        oop_stack = oop_stack or 10000

    # Ranges (placeholder inline for now; will be wired to real profiles later).
    ip_range = "AA,KK,QQ,JJ,TT,AKs,AQs"
    oop_range = "AA,KK,QQ,JJ,TT,AKs,AQo"

    # Buckets: keep small & deterministic for now.
    bucket_labels = ["50%", "100%", "jam"]

    # Spot: default to SRP until preflop tree classification is wired in.
    spot = "SRP"

    return SolveRequest(
        street=street,
        board=board,
        pot=int(pot),
        ip_stack=int(ip_stack),
        oop_stack=int(oop_stack),
        ip_range=ip_range,
        oop_range=oop_range,
        bucket_labels=bucket_labels,
        spot=spot,
    )
