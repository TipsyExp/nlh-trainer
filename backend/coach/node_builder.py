# backend/coach/node_builder.py
from __future__ import annotations

from backend.adapters.solver.texassolver_adapter import (
    SolveRequest,
    UnsupportedSpotError,
)


def build_solve_request_from_hand(hand_id: str, idx: int) -> SolveRequest:
    """
    Stub for Task-17 Step 5.
    Replace this with real extraction from gameplay state:
      - street, board, pot
      - ip_stack, oop_stack
      - ip_range, oop_range
      - bucket_labels
      - spot: "SRP" or "3BP"
    Until wired, we raise UnsupportedSpotError so the API returns a clean 501.
    """
    raise UnsupportedSpotError(
        f"Node builder not wired yet (hand_id={hand_id}, idx={idx})"
    )
