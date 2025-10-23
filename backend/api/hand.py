"""Hand API for the NLH trainer.

This module exposes endpoints to start a new hand, query the current
state and apply actions.  It wraps the PokerKit adapter and
incorporates per‑decision logging via the shared SQLite logger.  Each
action taken by the human or bots is recorded in the ``actions`` table
with an incrementing index.  When a hand completes the full
``GameState`` is serialised and stored in the logger.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.adapters.engines import get_adapter
from backend.api.session import get_session_state
from backend.logger import get_logger
from backend.models import (
    GameState,
    TableState,
    PlayerState,
    SeatType,
    PlayerStatus,
    ActionRecord,
    Street,
    ActionType,
)

# NOTE: no prefix here; app/main.py includes this router with prefix="/api".
router = APIRouter(tags=["hand"])


# ---------- Per‑hand indexing ----------

# Maintain a mapping from hand_id to the next action index.  This allows
# actions to be logged in order even when bots act between human
# decisions.
_ACTION_IDX: Dict[str, int] = {}


# ---------- Models ----------

class StartHandResponse(BaseModel):
    hand_id: str


class ActionRequest(BaseModel):
    seat: int
    action: str
    amount: Optional[int] = None


class ActionResponse(BaseModel):
    ok: bool
    bots_applied: List[Dict[str, Any]]
    state: Dict[str, Any]


class StateResponse(BaseModel):
    state: Dict[str, Any]
    actor: Optional[Dict[str, Any]] = None


# ---------- Helpers ----------

def _la_to_dict(la: Any) -> Optional[Dict[str, Any]]:
    """
    Adapter's last_action may be a dataclass or dict.  Normalize to dict or None.
    """
    if la is None:
        return None
    if isinstance(la, dict):
        return la
    # Dataclass‑like: try to read expected fields
    out: Dict[str, Any] = {}
    for k in (
        "seat",
        "type",
        "requested",
        "committed",
        "snapped",
        "bucket_label",
        "allowed_buckets",
    ):
        if hasattr(la, k):
            out[k] = getattr(la, k)
    return out


def _to_public_state(human_seat: int) -> Dict[str, Any]:
    """
    Convert adapter.state() dataclasses to a JSON‑friendly dict snapshot.

    Hide opponents' hole cards (mask to 'XX').
    """
    adapter = get_adapter()
    s = adapter.state()  # dataclasses: table, players, street, deck_seed, last_action, pot_total
    tbl = s.table

    # Players: mask everyone except human_seat
    players: List[Dict[str, Any]] = []
    for i, p in enumerate(s.players):
        if i == human_seat:
            players.append({"seat": i, "hole_cards": list(p.hole_cards)})
        else:
            players.append({"seat": i, "hole_cards": ["XX", "XX"]})

    resp = {
        "table": {
            "seats": int(tbl.seats),
            "sb": int(tbl.sb),
            "bb": int(tbl.bb),
            "ante": int(tbl.ante),
            "button": int(tbl.button),
            "sb_seat": int(tbl.sb_seat),
            "bb_seat": int(tbl.bb_seat),
        },
        "players": players,
        "street": s.street,
        "deck_seed": s.deck_seed,
        # Surface the pot
        "pot_total": int(getattr(s, "pot_total", 0)),
        "last_action": _la_to_dict(getattr(s, "last_action", None)),
    }
    return resp


def _pick_bot_action(actor: Dict[str, Any]) -> Tuple[str, Optional[int]]:
    """
    Naive heuristic for M0:
      - if to_call == 0: "check"
      - else: "call"
    """
    to_call = int(actor.get("to_call", 0))
    if to_call <= 0:
        return "check", None
    return "call", None


def _log_action(hand_id: str, seat: int, action: str, amount: Optional[int]) -> None:
    """Internal helper to record an action to the logger.

    This function updates the per‑hand action index and writes a row to
    the actions table.  It extracts additional metadata from the adapter's
    last_action snapshot to populate fields such as bucket, snapped and
    allowed buckets.
    """
    logger = get_logger()
    adapter = get_adapter()
    # Determine index; initialise if necessary
    idx = _ACTION_IDX.get(hand_id, 0)
    # Grab current street and pot
    snap = adapter.state()
    street = snap.street
    # Extract last action metadata if available
    la = snap.last_action
    bucket_label: Optional[str] = None
    snapped: Optional[int] = None
    meta_json: Optional[str] = None
    if la is not None:
        # 'bucket_label' may not exist on check/call actions
        bucket_label = getattr(la, "bucket_label", None)
        snap_flag = getattr(la, "snapped", None)
        if snap_flag is not None:
            snapped = 1 if snap_flag else 0
        allowed = getattr(la, "allowed_buckets", None)
        if allowed is not None:
            # store as JSON string
            import json as _json
            meta_json = _json.dumps({"allowed_buckets": allowed})
    # Persist the action
    logger.log_action(
        hand_id=hand_id,
        idx=idx,
        street=street,
        actor_seat=seat,
        type=action.lower(),
        amount=amount,
        bucket=bucket_label,
        to_call_after=None,
        pot_after=getattr(snap, "pot_total", None),
        time_ms=None,
        rng_seed=snap.deck_seed,
        snapped=snapped,
        meta=meta_json,
    )
    # Increment the index for next action
    _ACTION_IDX[hand_id] = idx + 1


def _auto_advance_bots(hand_id: str, human_seat: int) -> List[Dict[str, Any]]:
    """
    Loop while it's a bot's turn.  Returns a list of bot actions taken.

    Each bot action is applied to the engine and recorded via the logger.
    """
    adapter = get_adapter()
    actions_taken: List[Dict[str, Any]] = []
    # safety to avoid infinite loops
    for _ in range(100):
        actor = adapter.next_actor()
        if not actor:
            break
        if int(actor["seat"]) == human_seat:
            break
        action, amount = _pick_bot_action(actor)
        adapter.apply_action(actor["seat"], action, amount)
        # Log the bot action
        _log_action(hand_id, actor["seat"], action, amount)
        actions_taken.append({"seat": actor["seat"], "action": action, "amount": amount})
    return actions_taken


# ---------- Routes ----------

@router.post("/hand/start", response_model=StartHandResponse)
def start_hand() -> StartHandResponse:
    """Begin a new hand and auto‑advance bots until the first human decision."""
    adapter = get_adapter()
    try:
        hand_id = adapter.start_hand()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"start_hand failed: {e}") from e
    # Reset index for this hand
    _ACTION_IDX[hand_id] = 0
    # Auto‑advance bots immediately to first human decision (if any)
    human_seat = get_session_state().human_seat
    _auto_advance_bots(hand_id, human_seat)
    return StartHandResponse(hand_id=hand_id)


@router.get("/hand/state", response_model=StateResponse)
def get_state() -> StateResponse:
    adapter = get_adapter()
    human_seat = get_session_state().human_seat
    snap = _to_public_state(human_seat)
    actor = adapter.next_actor()
    return StateResponse(state=snap, actor=actor)


@router.post("/hand/action", response_model=ActionResponse)  # <-- FIXED PATH
def post_action(req: ActionRequest) -> ActionResponse:
    """Apply a human action and auto‑advance bots.

    The human's action is applied to the engine, logged via the logger
    and then bots are auto‑advanced.  If the hand completes as a result
    of the action sequence the final GameState is persisted.
    """
    adapter = get_adapter()
    human_seat = get_session_state().human_seat

    # Only the configured human seat may act
    if req.seat != human_seat:
        raise HTTPException(status_code=400, detail="Only the configured human seat may post actions.")
    # Determine current hand id from the adapter (prefixed 'H')
    hand_id = getattr(adapter, "hand_id", None)
    # In the PokerKitAdapter the public identifier includes the prefix; if
    # unavailable, fallback to the last started id from our index map
    if not hand_id:
        if not _ACTION_IDX:
            raise HTTPException(status_code=400, detail="no hand in progress")
        # use most recent key
        hand_id = next(reversed(_ACTION_IDX.keys()))
    # Apply the human action
    try:
        adapter.apply_action(req.seat, req.action, req.amount)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"apply_action failed: {e}") from e
    # Log the human action
    _log_action(hand_id, req.seat, req.action, req.amount)
    # Snapshot immediately after the human action
    pre_bot_state = _to_public_state(human_seat)
    # For bet/raise: return pre‑bot snapshot so snapping details are visible.
    action_l = (req.action or "").lower().strip()
    if action_l in ("bet", "raise"):
        return ActionResponse(ok=True, bots_applied=[], state=pre_bot_state)
    # Auto‑advance bots and return post‑bot snapshot (e.g. HU SB‑call -> BB‑check -> flop).
    bots = _auto_advance_bots(hand_id, human_seat)
    post_bot_state = _to_public_state(human_seat)
    # If no further actions are available (hand complete) persist the GameState
    if adapter.next_actor() is None:
        _persist_hand(hand_id)
    return ActionResponse(ok=True, bots_applied=bots, state=post_bot_state)


def _persist_hand(hand_id: str) -> None:
    """Build a GameState from the adapter snapshot and log it via SQLite.

    This helper reconstructs a minimal :class:`GameState` instance from
    the current engine snapshot and the logged action history.  It
    populates only the fields required by the state schema and uses
    sensible defaults for missing metadata (e.g., aliases and stacks).
    The resulting state is persisted along with the session identifier
    associated with the current session.
    """
    # Build GameState
    adapter = get_adapter()
    s = adapter.state()
    # Table configuration
    tbl = s.table
    table_state = TableState(
        seat_count=int(tbl.seats),
        sb=int(tbl.sb),
        bb=int(tbl.bb),
        ante=int(tbl.ante),
    )
    # Players: assign human/bot types based on session's human seat
    ss = get_session_state()
    players: List[PlayerState] = []
    for seat_idx in range(int(tbl.seats)):
        p_type = SeatType.human if seat_idx == ss.human_seat else SeatType.bot
        alias = "Hero" if p_type == SeatType.human else f"Bot{seat_idx}"
        stack = ss.stacks[seat_idx] if seat_idx < len(ss.stacks) else 0
        players.append(
            PlayerState(
                seat=seat_idx,
                type=p_type,
                alias=alias,
                stack=stack,
                status=PlayerStatus.active,
            )
        )
    # Actions: fetch from logger
    logger = get_logger()
    action_rows = list(logger.fetch_hand_actions(hand_id))
    action_history: List[ActionRecord] = []
    for row in action_rows:
        action_history.append(
            ActionRecord(
                idx=row["idx"],
                street=Street(row["street"]),
                actor_seat=row["actor_seat"],
                type=ActionType(row["type"]),
                amount=row["amount"],
                bucket=row["bucket"],
                to_call_after=row["to_call_after"],
                pot_after=row["pot_after"],
                time_ms=row["time_ms"],
                rng_seed=row["rng_seed"],
                snapped=bool(row["snapped"]) if row["snapped"] is not None else None,
                meta=None,
            )
        )
    # Determine dealer, SB and BB seats from snapshot
    dealer_seat = int(tbl.button)
    sb_seat = int(tbl.sb_seat)
    bb_seat = int(tbl.bb_seat)
    # Build final GameState
    state = GameState(
        hand_id=hand_id,
        deck_seed=s.deck_seed,
        table=table_state,
        dealer_seat=dealer_seat,
        sb_seat=sb_seat,
        bb_seat=bb_seat,
        street=Street(s.street),
        players=players,
        action_history=action_history,
    )
    # Persist the hand with engine/evaluator names and session id
    logger.log_hand(state, engine="PokerKit", evaluator="PokerKit", session_id=get_session_state().logger_session_id)
