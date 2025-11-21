# backend/coach/decision_context.py
"""
Shared decision-context helper for coaching.

This module builds a minimal, normalized view of a single decision that
can be shared across:

  * /api/coach/advice
  * preflop advisor
  * solver node builder
  * logging / exports

The context is derived from the same public state shape that backs
`/api/hand/state` (see docs/STATE-SCHEMA.md). For engine-backed calls
we build that public state via `_to_public_state` and keep the raw
engine snapshot alongside it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.adapters.engines import get_adapter
from backend.api.session import get_session_state
from backend.api.hand import _to_public_state


@dataclass(frozen=True)
class DecisionContext:
    """
    Minimal, street-agnostic description of a single decision.

    Fields are intentionally lightweight but sufficient for:

      * preflop advisor (node + hand classification),
      * postflop solver / equity-based coaching,
      * export snapshots and debugging.

    Attributes:
        hand_id:        Public hand identifier (e.g. "H1").
        idx:            Decision index within the hand (0-based).
        street:         "preflop", "flop", "turn", "river", "showdown", or "unknown".
        hero_seat:      Seat index of the human/hero player.
        n_players:      Number of seats in the `players` array (active players).
        board:          Flat list of board cards in street order
                        (flop first, then turn, then river), e.g.
                        ["Ah","Kd","3s","7c","2d"].
        pot_total:      Total pot size before the hero acts.
        to_call:        Amount the current actor must commit to continue.
        min_raise:      Minimum TOTAL commitment for a legal raise, or None
                        if not applicable or unknown.
        allowed_buckets: List of canonical bucket labels (["fold","call","2.5x",...]).
        deck_seed:      Optional deck seed used to reproduce the hand.
        hero_hole_cards: Hero's hole cards when known (may be masked in public state).
        known_hole_cards: Map of seat -> known hole cards from the state snapshot.
        stacks:         Optional per-seat stack sizes (if available).
        committed:      Optional per-seat committed amounts (if available).
        raw_state:      Underlying engine snapshot or state object; used
                        by lower-level helpers (e.g. solver node builder).
    """

    hand_id: str
    idx: int
    street: str
    hero_seat: int
    n_players: int
    board: List[str]
    pot_total: int
    to_call: int
    min_raise: Optional[int]
    allowed_buckets: List[str]
    deck_seed: Optional[str] = None

    hero_hole_cards: List[str] = field(default_factory=list)
    known_hole_cards: Dict[int, List[str]] = field(default_factory=dict)
    stacks: Dict[int, int] = field(default_factory=dict)
    committed: Dict[int, int] = field(default_factory=dict)

    # raw_state is intentionally excluded from repr to keep logs concise
    raw_state: Any = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def _normalize_board_from_state(state: Dict[str, Any]) -> List[str]:
    """
    Normalize state["board"] into a flat list of cards.

    Accepts either:
      * dict form: {"flop":[...], "turn":[...], "river":[...]}
      * flat list: ["Ah","Kd","3s",...]
    """
    board = state.get("board")

    # Dict form with street slices
    if isinstance(board, dict):
        out: List[str] = []
        for key in ("flop", "turn", "river"):
            v = board.get(key)
            if isinstance(v, list):
                out.extend([c for c in v if isinstance(c, str)])
        return out

    # Flat list form
    if isinstance(board, list):
        return [c for c in board if isinstance(c, str)]

    return []


def _extract_allowed(state: Dict[str, Any]) -> tuple[int, Optional[int], List[str]]:
    """
    Extract (to_call, min_raise, allowed_buckets) from a state dict.

    Missing or malformed fields are treated conservatively:
      * to_call → 0
      * min_raise → None
      * allowed_buckets → []
    """
    allowed = state.get("allowed") or {}
    to_call = 0
    min_raise: Optional[int] = None
    buckets: List[str] = []

    if isinstance(allowed, dict):
        tc = allowed.get("to_call")
        if isinstance(tc, (int, float)):
            to_call = int(tc)

        mr = allowed.get("min_raise")
        if isinstance(mr, (int, float)):
            min_raise = int(mr)

        ab = allowed.get("allowed_buckets")
        if isinstance(ab, list):
            buckets = [str(x) for x in ab]

    return to_call, min_raise, buckets


def _extract_players(
    state: Dict[str, Any], hero_seat: int
) -> tuple[int, List[str], Dict[int, List[str]]]:
    """
    Extract (n_players, hero_hole_cards, known_hole_cards).
    """
    players = state.get("players") or []
    n_players = 0
    hero_cards: List[str] = []
    known: Dict[int, List[str]] = {}

    if isinstance(players, list):
        for p in players:
            if not isinstance(p, dict):
                continue
            seat = p.get("seat")
            if not isinstance(seat, int):
                continue
            n_players += 1
            hc = p.get("hole_cards")
            if isinstance(hc, list) and all(isinstance(c, str) for c in hc):
                cards = list(hc)
                known[seat] = cards
                if seat == hero_seat:
                    hero_cards = cards

    return n_players, hero_cards, known


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------


def build_decision_context_from_state(
    state: Dict[str, Any],
    hand_id: str,
    idx: int,
    hero_seat: int,
    raw_state: Any | None = None,
) -> DecisionContext:
    """
    Build a DecisionContext from a public state snapshot.

    `state` is expected to look like `state["state"]` from `/api/hand/state`,
    as produced by `_to_public_state` (see docs/STATE-SCHEMA.md).

    This helper is used directly in tests and is also the core that the
    engine-backed `build_decision_context` function delegates to.
    """
    street_val = state.get("street")
    street = street_val if isinstance(street_val, str) else "unknown"

    board = _normalize_board_from_state(state)
    to_call, min_raise, buckets = _extract_allowed(state)
    n_players, hero_cards, known = _extract_players(state, hero_seat=hero_seat)

    pot_val = state.get("pot_total")
    pot_total = int(pot_val) if isinstance(pot_val, (int, float)) else 0

    deck_seed = state.get("deck_seed")
    if not isinstance(deck_seed, str):
        deck_seed = None

    # Stacks / committed are optional and may be filled in later once the
    # underlying engine exposes them in the public state; keep empty for now.
    ctx = DecisionContext(
        hand_id=str(hand_id),
        idx=int(idx),
        street=street,
        hero_seat=int(hero_seat),
        n_players=int(n_players),
        board=board,
        pot_total=pot_total,
        to_call=to_call,
        min_raise=min_raise,
        allowed_buckets=buckets,
        deck_seed=deck_seed,
        hero_hole_cards=hero_cards,
        known_hole_cards=known,
        stacks={},
        committed={},
        raw_state=raw_state if raw_state is not None else state,
    )
    return ctx


def build_decision_context(hand_id: str, idx: int) -> DecisionContext:
    """
    Build a DecisionContext for the *current* engine state.

    For Task 2 this is "current-only": we do not yet reconstruct historical
    state at arbitrary `idx` from logs. Instead, `(hand_id, idx)` is used
    mainly for identification in logs and exports.

    Steps:
      1. Read the engine snapshot via `get_adapter().state()`.
      2. Build the public state dict via `_to_public_state(human_seat)`.
      3. Delegate to `build_decision_context_from_state`, passing the raw
         engine snapshot through as `raw_state`.
    """
    adapter = get_adapter()
    ss = get_session_state()
    hero_seat = int(ss.human_seat)

    # Raw engine snapshot (PokerKitAdapter._GameSnap in the current engine).
    engine_state = adapter.state()

    # Public state dict (same shape as /api/hand/state.state).
    public_state = _to_public_state(hero_seat)

    return build_decision_context_from_state(
        public_state,
        hand_id=hand_id,
        idx=idx,
        hero_seat=hero_seat,
        raw_state=engine_state,
    )
