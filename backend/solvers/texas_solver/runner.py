# backend/solvers/texas_solver/runner.py
"""
Thin, domain-level runner around the TexasSolver adapter + cache.

This module gives higher-level callers (preflop/postflop coach policies)
a small, stable API:

  * describe a single HU postflop node in terms of:
      - street / board
      - pot size
      - IP / OOP stacks behind
      - IP / OOP ranges (solver-native text)
      - abstract bet-size bucket labels (e.g. ["33%", "66%", "100%", "jam"])
      - spot type ("SRP" | "3BP")
  * receive:
      - an advice payload (strategy + EV map) as a plain dict
      - a flag indicating whether it came from cache
      - a stable node_key (sha256 over the SolveRequest)

All the low-level details of:

  * building the TexasSolver input script,
  * invoking the console binary,
  * parsing JSON,
  * and persisting to SQLite

are delegated to:

  - backend.adapters.solver.texassolver_adapter.TexasSolverAdapter / SolveRequest
  - backend.coach.texassolver_cache.resolve_with_cache

This keeps the solver integration nicely layered:

  adapters/    → "glue" to external binaries / libs
  solvers/     → domain-facing runner utilities for a given solver
  coach/       → policies that call into solvers with poker-specific context
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from backend.adapters.solver.texassolver_adapter import SolveRequest
from backend.coach.texassolver_cache import resolve_with_cache


# Default bucket labels used when the caller doesn't specify their own.
# These are expressed in the *coach* / UI's naming convention and will be
# mapped to pot-% internally by the adapter.
DEFAULT_BUCKET_LABELS: List[str] = ["33%", "66%", "100%", "jam"]


@dataclass(frozen=True)
class NodeInputs:
    """
    High-level description of a single HU postflop node to be solved.

    This is intentionally very close to SolveRequest, but remains solver-
    agnostic at the call site: coach code constructs a NodeInputs, and this
    module handles the SolveRequest + cache plumbing.
    """

    street: str  # "flop" | "turn" | "river"
    board: List[str]  # ["Ah", "Kd", "3s"] etc.
    pot: int  # current pot size (chips)
    ip_stack: int  # stack behind IP (chips)
    oop_stack: int  # stack behind OOP (chips)
    ip_range: str  # solver-native text (e.g. "22+,A2s+,K9s+,...")
    oop_range: str  # solver-native text
    bucket_labels: List[str]
    spot: str = "SRP"  # "SRP" | "3BP"


def to_solve_request(node: NodeInputs) -> SolveRequest:
    """
    Convert a NodeInputs into the canonical SolveRequest understood by the
    adapter + cache.

    This keeps SolveRequest as the single "truth" for how a node is passed
    to TexasSolver, while allowing coach code to remain decoupled from the
    adapter module.
    """
    return SolveRequest(
        street=node.street,
        board=list(node.board),
        pot=int(node.pot),
        ip_stack=int(node.ip_stack),
        oop_stack=int(node.oop_stack),
        ip_range=node.ip_range,
        oop_range=node.oop_range,
        bucket_labels=list(node.bucket_labels),
        spot=node.spot,
    )


def solve_node(node: NodeInputs) -> Tuple[Dict[str, Any], bool, str]:
    """
    Solve a single HU postflop node via TexasSolver with persistent caching.

    Args:
        node:
            High-level node description (street, board, pot, stacks, ranges,
            bucket labels, spot type).

    Returns:
        (payload, from_cache, node_key)
        - payload:   advice payload as a plain dict with at least:
                       { "recommended_bucket": str,
                         "strategy": {label: prob, ...},
                         "ev_map":  {label: ev,   ...} }
        - from_cache: True if returned from cache, False if freshly solved.
        - node_key:   stable node key (sha256 hex) derived from SolveRequest.

    Raises:
        CoachDisabledError, UnsupportedSpotError – propagated from the adapter
        layer if COACH / solver are disabled or the spot is unsupported.
    """
    req = to_solve_request(node)
    payload, cached, node_key = resolve_with_cache(req)
    return payload, cached, node_key


def solve_simple(
    *,
    street: str,
    board: List[str],
    pot: int,
    ip_stack: int,
    oop_stack: int,
    ip_range: str,
    oop_range: str,
    bucket_labels: List[str] | None = None,
    spot: str = "SRP",
) -> Tuple[Dict[str, Any], bool, str]:
    """
    Convenience wrapper for callers that don't want to construct NodeInputs.

    Example usage from a coach policy:

        payload, cached, node_key = solve_simple(
            street="flop",
            board=["Ah", "Kd", "3s"],
            pot=150,
            ip_stack=4850,
            oop_stack=5000,
            ip_range=hero_range_str,
            oop_range=villain_range_str,
            bucket_labels=["33%", "66%", "100%", "jam"],
            spot="SRP",
        )

    The return values are identical to solve_node(...).
    """
    labels = (
        list(bucket_labels)
        if bucket_labels is not None
        else list(DEFAULT_BUCKET_LABELS)
    )
    node = NodeInputs(
        street=street,
        board=board,
        pot=pot,
        ip_stack=ip_stack,
        oop_stack=oop_stack,
        ip_range=ip_range,
        oop_range=oop_range,
        bucket_labels=labels,
        spot=spot,
    )
    return solve_node(node)


__all__ = [
    "DEFAULT_BUCKET_LABELS",
    "NodeInputs",
    "to_solve_request",
    "solve_node",
    "solve_simple",
]
