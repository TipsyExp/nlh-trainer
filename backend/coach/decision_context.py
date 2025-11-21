# backend/coach/decision_context.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.adapters.engines import get_adapter
from backend.api.session import get_session_state


@dataclass(frozen=True)
class DecisionContext:
    """
    Canonical backend representation of a single decision.

    This is the object that coaching logic (preflop, postflop, solver-based)
    should consume when building AdviceV1 payloads. It is intentionally
    hero-centric but still captures enough information to support multiway
    equity and positional heuristics.

    Fields:

        hand_id:
            External hand identifier, e.g. "H1". This is the key used by
            logging and export endpoints and should match the engine's current
            hand id for live contexts.

        idx:
            Action index within the hand. For the current implementation this
            is carried through by the caller but not yet used to reconstruct
            historical states. Future versions will guarantee that the
            context reflects the state *just before* action idx.

        street:
            Current street as a string: "preflop", "flop", "turn", "river",
            "showdown" or "unknown".

        hero_seat:
            Seat index of the human player (from the session state or caller).

        n_players:
            Number of seats still in the hand (best-effort based on player
            status; see `active_seats`).

        active_seats:
            List of seat indices that appear to still be in the hand.

        board:
            Flat list of board cards in flop→turn→river order, e.g.
            ["Ah", "Kd", "3s", "7c", "2d"].

        pot_total:
            Total pot size in chips *before* the next action.

        to_call:
            Amount (chips) the current actor must commit to continue.
            0 when checking is allowed or when the hand is terminal.

        min_raise:
            Minimum TOTAL commitment required to make a legal raise from
            this spot, or None if not applicable / unknown.

        allowed_buckets:
            List of legal bucket labels, e.g. ["fold","call","2.5xR","jam"].

        deck_seed:
            Deterministic deck seed string, when available.

        hero_hole_cards:
            Hero's hole cards as a list of two card strings, when available.
            Taken directly from engine/public state (unmasked).

        button, sb_seat, bb_seat:
            Positional anchors from the table snapshot.

        terminal:
            True when the hand is in a terminal state (no meaningful next
            action). For engine-based contexts this is inferred from the
            adapter's `next_actor()`; for state-based contexts it is inferred
            from `state["to_act"]`.

        last_action:
            Lightweight summary of the engine's last action, when available.
            Mirrors the `last_action` shape described in docs/STATE-SCHEMA.md.

        raw_state:
            The underlying state object:

              * For engine-based contexts: the adapter.state() snapshot.
              * For state-based contexts: the public state dict.

            Provided as an escape hatch for advanced consumers; treat as
            read-only.

        seat_stacks:
            Best-effort mapping of seat index → stack behind in chips at this
            decision. This is derived from the players array when available.
            Intended for multiway equity / SPR heuristics.

        seat_committed:
            Best-effort mapping of seat index → total chips committed so far
            in the hand (or on the current street, depending on engine
            semantics). Also derived from the players array.

        hero_stack:
            Convenience view of `seat_stacks[hero_seat]` when known.

        hero_committed:
            Convenience view of `seat_committed[hero_seat]` when known.
    """

    hand_id: str
    idx: int

    street: str
    hero_seat: int
    n_players: int
    active_seats: List[int]

    board: List[str]
    pot_total: int
    to_call: int
    min_raise: Optional[int]
    allowed_buckets: List[str]
    deck_seed: Optional[str]

    hero_hole_cards: Optional[List[str]]

    button: int
    sb_seat: int
    bb_seat: int

    terminal: bool

    last_action: Optional[Dict[str, Any]]

    raw_state: Any

    # Multiway / stack context (best-effort, optional)
    seat_stacks: Dict[int, int] = field(default_factory=dict)
    seat_committed: Dict[int, int] = field(default_factory=dict)
    hero_stack: Optional[int] = None
    hero_committed: Optional[int] = None


# ---------------------------------------------------------------------------
# Internal helpers (shape-normalisation)
# ---------------------------------------------------------------------------


def _normalize_board_any(board_obj: Any) -> List[str]:
    """
    Normalise a board representation into a flat list of card strings.

    Accepts:
      - dict like {"flop": [...], "turn": [...], "river": [...]}
      - flat list ["Ah","Kd","3s",...]
      - anything else → [].
    """
    cards: List[str] = []

    if isinstance(board_obj, dict):
        segments = [
            board_obj.get("flop") or [],
            board_obj.get("turn") or [],
            board_obj.get("river") or [],
        ]
        for seg in segments:
            if isinstance(seg, list):
                for c in seg:
                    if isinstance(c, str):
                        cards.append(c)
        return cards

    if isinstance(board_obj, list):
        for c in board_obj:
            if isinstance(c, str):
                cards.append(c)
        return cards

    return []


def _infer_active_seats_from_players(players: Any) -> List[int]:
    """
    Best-effort inference of active seats given a players array.

    For each player entry (dict or object), if a 'status' field is present and
    stringifies to something containing 'fold', 'out' or 'sitout', that seat
    is treated as inactive. Otherwise it is treated as active.
    """
    if not isinstance(players, list):
        return []

    active: List[int] = []
    for idx, p in enumerate(players):
        status = None
        if isinstance(p, dict):
            status = p.get("status")
        else:
            status = getattr(p, "status", None)

        if status is None:
            active.append(idx)
            continue

        s = str(status).lower()
        if "fold" in s or "out" in s or "sitout" in s:
            continue
        active.append(idx)

    return active


def _extract_hero_hole_cards_from_players(
    players: Any, hero_seat: int
) -> Optional[List[str]]:
    """
    Extract hero's hole cards from a players list (dict or engine objects).
    """
    if not isinstance(players, list):
        return None
    if hero_seat < 0 or hero_seat >= len(players):
        return None

    p = players[hero_seat]
    cards = None
    if isinstance(p, dict):
        cards = p.get("hole_cards")
    else:
        cards = getattr(p, "hole_cards", None)

    if not isinstance(cards, list):
        return None

    out: List[str] = []
    for c in cards:
        if isinstance(c, str):
            out.append(c)
        else:
            out.append(str(c))
    return out or None


def _extract_stacks_and_committed_from_players(
    players: Any,
) -> tuple[Dict[int, int], Dict[int, int]]:
    """
    Best-effort extraction of per-seat stack / committed information.

    This looks for common fields on each player entry:

        * 'stack'
        * 'committed'

    on either dict-like entries or engine player objects. Values are coerced
    to ints when numeric. Missing or non-numeric fields are ignored.

    Returns:
        (seat_stacks, seat_committed) where each is a mapping seat -> int.
    """
    seat_stacks: Dict[int, int] = {}
    seat_committed: Dict[int, int] = {}

    if not isinstance(players, list):
        return seat_stacks, seat_committed

    for idx, p in enumerate(players):
        if isinstance(p, dict):
            stack_val = p.get("stack")
            committed_val = p.get("committed")
        else:
            stack_val = getattr(p, "stack", None)
            committed_val = getattr(p, "committed", None)

        if isinstance(stack_val, (int, float)):
            seat_stacks[idx] = int(stack_val)
        if isinstance(committed_val, (int, float)):
            seat_committed[idx] = int(committed_val)

    return seat_stacks, seat_committed


def _normalize_last_action(la: Any) -> Optional[Dict[str, Any]]:
    """
    Normalise a last_action payload into a dict or None.

    Accepts:
      - dict (copied)
      - engine dataclass-like objects with attributes:
          seat, type, requested, committed, snapped, bucket_label, allowed_buckets
      - None
    """
    if la is None:
        return None

    if isinstance(la, dict):
        return dict(la)

    out: Dict[str, Any] = {}
    for key in (
        "seat",
        "type",
        "requested",
        "committed",
        "snapped",
        "bucket_label",
        "allowed_buckets",
    ):
        if hasattr(la, key):
            out[key] = getattr(la, key)

    return out or None


# ---------------------------------------------------------------------------
# State-dict → DecisionContext (used in tests & exports)
# ---------------------------------------------------------------------------


def build_decision_context_from_state(
    state: Dict[str, Any],
    hand_id: str,
    idx: int,
    hero_seat: int,
) -> DecisionContext:
    """
    Build a DecisionContext from a public state dict.

    This helper is designed for:
      - tests (using synthetic /api/hand/state-style payloads),
      - future export / replay tooling that reconstructs context from logged
        JSON snapshots.

    The `state` argument should look like /api/hand/state["state"], as
    documented in docs/STATE-SCHEMA.md.
    """
    table = state.get("table") or {}
    players = state.get("players") or []

    street = str(state.get("street", "unknown"))

    board = _normalize_board_any(state.get("board"))
    pot_total = int(state.get("pot_total", 0) or 0)

    allowed = state.get("allowed") or {}
    to_call = int(allowed.get("to_call", 0) or 0)

    mr = allowed.get("min_raise", None)
    min_raise: Optional[int]
    if isinstance(mr, (int, float)):
        min_raise = int(mr)
    else:
        min_raise = None

    buckets_raw = allowed.get("allowed_buckets") or []
    allowed_buckets = (
        [str(b) for b in buckets_raw] if isinstance(buckets_raw, list) else []
    )

    deck_seed_val = state.get("deck_seed")
    deck_seed: Optional[str]
    if isinstance(deck_seed_val, str):
        deck_seed = deck_seed_val
    elif isinstance(deck_seed_val, (int, float)):
        deck_seed = str(deck_seed_val)
    else:
        deck_seed = None

    active_seats = _infer_active_seats_from_players(players)
    n_players = len(active_seats)

    # Per-seat stack / committed information (best-effort)
    seat_stacks, seat_committed = _extract_stacks_and_committed_from_players(players)

    hero_seat_int = int(hero_seat)
    hero_cards = _extract_hero_hole_cards_from_players(players, hero_seat_int)

    button = int(table.get("button", 0) or 0)
    sb_seat = int(table.get("sb_seat", 0) or 0)
    bb_seat = int(table.get("bb_seat", 0) or 0)

    # Terminal if to_act is missing or explicitly None.
    to_act = state.get("to_act") if "to_act" in state else None
    terminal = to_act is None

    last_action = _normalize_last_action(state.get("last_action"))

    hero_stack = seat_stacks.get(hero_seat_int)
    hero_committed = seat_committed.get(hero_seat_int)

    return DecisionContext(
        hand_id=str(hand_id),
        idx=int(idx),
        street=street,
        hero_seat=hero_seat_int,
        n_players=n_players,
        active_seats=active_seats,
        board=board,
        pot_total=pot_total,
        to_call=to_call,
        min_raise=min_raise,
        allowed_buckets=allowed_buckets,
        deck_seed=deck_seed,
        hero_hole_cards=hero_cards,
        button=button,
        sb_seat=sb_seat,
        bb_seat=bb_seat,
        terminal=terminal,
        last_action=last_action,
        raw_state=state,
        seat_stacks=seat_stacks,
        seat_committed=seat_committed,
        hero_stack=hero_stack,
        hero_committed=hero_committed,
    )


# ---------------------------------------------------------------------------
# Live engine → DecisionContext (used by /api/coach/advice, node_builder)
# ---------------------------------------------------------------------------


def build_decision_context(hand_id: str, idx: int) -> DecisionContext:
    """
    Build a DecisionContext for the given (hand_id, idx) pair from the
    **current** engine state.

    Current behaviour:

      - Validates that `hand_id` matches the adapter's active hand id.
      - Derives all fields from adapter.state() and adapter.next_actor().
      - Does NOT yet replay historical actions based on idx; idx is carried
        through for logging/export correlation only.

    Raises:
        RuntimeError:
            If there is no active hand in the engine.

        ValueError:
            If the provided hand_id does not match the engine's current hand.
    """
    adapter = get_adapter()
    ss = get_session_state()
    hero_seat = ss.human_seat

    engine_hand_id = getattr(adapter, "hand_id", None)
    if engine_hand_id is None:
        raise RuntimeError("no active hand in progress for decision context")

    # Normalise engine hand id to the "H#" string form used by logging/export.
    if isinstance(engine_hand_id, int):
        engine_hand_str = f"H{engine_hand_id}"
    else:
        engine_hand_str = str(engine_hand_id)

    hand_id_str = str(hand_id)
    if hand_id_str != engine_hand_str:
        raise ValueError(
            f"decision context mismatch: requested hand_id={hand_id_str}, "
            f"engine hand_id={engine_hand_str}"
        )

    state = adapter.state()
    table = getattr(state, "table", None)

    street = str(getattr(state, "street", "unknown"))

    board_attr = getattr(state, "board", None)
    board = _normalize_board_any(board_attr)

    pot_total = int(getattr(state, "pot_total", 0) or 0)

    # Actor / allowed buckets
    raw_actor = adapter.next_actor() or None  # adapter may return {} when no actor
    if raw_actor:
        to_call = int(raw_actor.get("to_call", 0) or 0)
        mr = raw_actor.get("min_raise", None)
        min_raise: Optional[int]
        if isinstance(mr, (int, float)):
            min_raise = int(mr)
        else:
            min_raise = None
        buckets_raw = raw_actor.get("allowed_buckets") or []
        allowed_buckets = (
            [str(b) for b in buckets_raw] if isinstance(buckets_raw, list) else []
        )
        terminal = False
    else:
        to_call = 0
        min_raise = None
        allowed_buckets = []
        terminal = True

    deck_seed_val = getattr(state, "deck_seed", None)
    deck_seed: Optional[str]
    if isinstance(deck_seed_val, str):
        deck_seed = deck_seed_val
    elif isinstance(deck_seed_val, (int, float)):
        deck_seed = str(deck_seed_val)
    else:
        deck_seed = None

    players = getattr(state, "players", []) or []
    active_seats = _infer_active_seats_from_players(players)
    n_players = len(active_seats)

    # Per-seat stack / committed information (best-effort)
    seat_stacks, seat_committed = _extract_stacks_and_committed_from_players(players)

    hero_seat_int = int(hero_seat)
    hero_cards = _extract_hero_hole_cards_from_players(players, hero_seat_int)

    button = int(getattr(table, "button", 0) if table is not None else 0)
    sb_seat = int(getattr(table, "sb_seat", 0) if table is not None else 0)
    bb_seat = int(getattr(table, "bb_seat", 0) if table is not None else 0)

    last_action = _normalize_last_action(getattr(state, "last_action", None))

    hero_stack = seat_stacks.get(hero_seat_int)
    hero_committed = seat_committed.get(hero_seat_int)

    return DecisionContext(
        hand_id=hand_id_str,
        idx=int(idx),
        street=street,
        hero_seat=hero_seat_int,
        n_players=n_players,
        active_seats=active_seats,
        board=board,
        pot_total=pot_total,
        to_call=to_call,
        min_raise=min_raise,
        allowed_buckets=allowed_buckets,
        deck_seed=deck_seed,
        hero_hole_cards=hero_cards,
        button=button,
        sb_seat=sb_seat,
        bb_seat=bb_seat,
        terminal=terminal,
        last_action=last_action,
        raw_state=state,
        seat_stacks=seat_stacks,
        seat_committed=seat_committed,
        hero_stack=hero_stack,
        hero_committed=hero_committed,
    )
