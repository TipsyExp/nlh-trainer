# backend/coach/node_builder.py
from __future__ import annotations

from typing import List, Optional, Tuple

from backend.adapters.solver.texassolver_adapter import (
    SolveRequest,
    UnsupportedSpotError,
)

# We reuse the server's state assembly to avoid duplicating logic.
# get_state() is the same function behind GET /api/hand/state and returns:
#   { "state": {...}, "actor": {...} }  (shape used by the frontend)
try:
    # Delayed import so this file doesn't load heavy modules at import-time in CI
    from backend.api.hand import get_state as _server_get_state  # type: ignore
except Exception:  # pragma: no cover
    _server_get_state = None  # type: ignore


def _require_server_state() -> dict:
    if _server_get_state is None:
        raise UnsupportedSpotError("hand state accessor unavailable")
    try:
        data = _server_get_state()
        if not isinstance(data, dict):
            raise UnsupportedSpotError("unexpected state payload")
        return data
    except Exception as e:
        # Keep the adapter contract: turn internal issues into "unsupported" for now
        raise UnsupportedSpotError(f"state unavailable: {e}")


def _detect_ip_oop_seats(state: dict) -> Tuple[int, int]:
    """
    Heads-up postflop: Button acts in position (IP); the other is OOP.
    """
    table = state.get("table") or {}
    btn = table.get("button")
    seats = table.get("seats", 2)
    if not isinstance(btn, int):
        raise UnsupportedSpotError("button seat unknown")

    # In HU we expect seats == 2 and seats 0..(seats-1) to exist.
    # We'll assume seat indexes are 0..N-1 and opponent is the other seat.
    if seats != 2:
        raise UnsupportedSpotError("only heads-up supported for coach")
    ip_seat = btn
    oop_seat = 1 - ip_seat
    return ip_seat, oop_seat


def _chip_stack_for_seat(state: dict, seat: int) -> Optional[int]:
    """
    Try to read chips-behind for a given seat from the assembled state.
    Falls back to None if unavailable.
    """
    players = state.get("players") or []
    for p in players:
        if not isinstance(p, dict):
            continue
        if p.get("seat") == seat:
            # Prefer explicit 'stack' if present; otherwise try a few common keys.
            for k in ("stack", "chips", "behind"):
                v = p.get(k)
                if isinstance(v, int):
                    return v
    return None


def _board_cards(state: dict) -> List[str]:
    """
    Read board cards as ["Ah","Kd","3s"].
    """
    board = state.get("board")
    if isinstance(board, list) and all(isinstance(x, str) for x in board):
        return board
    # Some states nest board under state["community"]
    comm = state.get("community")
    if isinstance(comm, dict) and isinstance(comm.get("board"), list):
        b = comm["board"]
        if all(isinstance(x, str) for x in b):
            return b
    raise UnsupportedSpotError("board not available")


def _current_pot(state: dict) -> int:
    v = state.get("pot_total")
    if isinstance(v, int):
        return v
    # Try alternate spellings if present in your state model
    for k in ("pot", "pot_chips", "total_pot"):
        vv = state.get(k)
        if isinstance(vv, int):
            return vv
    # Last resort: 0 (not ideal, but keeps adapter predictable)
    return 0


def build_solve_request_from_hand(hand_id: str, idx: int) -> SolveRequest:
    """
    Build a minimal, deterministic SolveRequest for **postflop HU**.
    Preflop remains unsupported in Task-17.

    This intentionally uses conservative defaults for ranges & buckets:
      - spot: "SRP"
      - bucket_labels: ["50%","100%","jam"]
      - ranges: simple inline placeholders (updated later in M1)
    """
    data = _require_server_state()
    state = data.get("state") or {}
    if not isinstance(state, dict):
        raise UnsupportedSpotError("hand state missing")

    street = state.get("street")
    if street not in ("flop", "turn", "river"):
        # Task-17 scope: preflop unsupported to avoid ambiguous builder logic here.
        raise UnsupportedSpotError("preflop not supported")

    board = _board_cards(state)
    pot = _current_pot(state)

    # Seats (IP = button on postflop)
    ip_seat, oop_seat = _detect_ip_oop_seats(state)

    # Stacks behind — if unknown in the public state, fall back to a sane default.
    ip_stack = _chip_stack_for_seat(state, ip_seat)
    oop_stack = _chip_stack_for_seat(state, oop_seat)
    if ip_stack is None or oop_stack is None:
        # Use a conservative default; engine snaps sizes anyway.
        ip_stack = ip_stack or 10000
        oop_stack = oop_stack or 10000

    # Ranges (placeholder inline for Task-17). Replace with real ranges later in M1.
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
