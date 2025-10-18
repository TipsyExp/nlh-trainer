from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.adapters.engines import get_adapter
from .session import get_session_state

# NOTE: no prefix here; app/main.py likely includes this router with prefix="/api".
router = APIRouter(tags=["hand"])


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
    Adapter's last_action may be a dataclass or dict. Normalize to dict or None.
    """
    if la is None:
        return None
    if isinstance(la, dict):
        return la
    # Dataclass-like: try to read expected fields
    out = {}
    for k in ("seat", "type", "requested", "committed", "snapped", "bucket_label", "allowed_buckets"):
        if hasattr(la, k):
            out[k] = getattr(la, k)
    return out


def _to_public_state(human_seat: int) -> Dict[str, Any]:
    """
    Convert adapter.state() dataclasses to a JSON-friendly dict snapshot.
    Hide opponents' hole cards (mask to 'XX').
    """
    adapter = get_adapter()
    s = adapter.state()  # dataclasses: table, players, street, deck_seed, last_action
    tbl = s.table

    # Players: mask everyone except human_seat
    players = []
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


def _auto_advance_bots(human_seat: int) -> List[Dict[str, Any]]:
    """
    Loop while it's a bot's turn. Returns a list of bot actions taken.
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
        actions_taken.append({"seat": actor["seat"], "action": action, "amount": amount})
    return actions_taken


# ---------- Routes ----------

@router.post("/hand/start", response_model=StartHandResponse)
def start_hand() -> StartHandResponse:
    adapter = get_adapter()
    try:
        hand_id = adapter.start_hand()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"start_hand failed: {e}") from e

    # Auto-advance bots immediately to first human decision (if any)
    human_seat = get_session_state().human_seat
    _auto_advance_bots(human_seat)

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
    adapter = get_adapter()
    human_seat = get_session_state().human_seat

    if req.seat != human_seat:
        raise HTTPException(status_code=400, detail="Only the configured human seat may post actions.")

    # Apply the human action
    try:
        adapter.apply_action(req.seat, req.action, req.amount)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"apply_action failed: {e}") from e

    # Snapshot immediately after the human action
    pre_bot_state = _to_public_state(human_seat)

    # For bet/raise: return pre-bot snapshot so snapping details are visible.
    # For call/check: auto-advance bots and return post-bot snapshot (e.g. HU SB-call -> BB-check -> flop).
    action_l = (req.action or "").lower().strip()
    if action_l in ("bet", "raise"):
        return ActionResponse(ok=True, bots_applied=[], state=pre_bot_state)

    bots = _auto_advance_bots(human_seat)
    post_bot_state = _to_public_state(human_seat)
    return ActionResponse(ok=True, bots_applied=bots, state=post_bot_state)
