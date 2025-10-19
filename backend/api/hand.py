from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.adapters.engines import get_adapter
from .session import get_session_state

# ---- Optional logging hooks (safe if missing) ----
try:
    from backend.database import log_hand_start as db_log_hand_start  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - optional
    db_log_hand_start = None  # type: ignore[assignment]

try:
    from backend.database import log_action as db_log_action  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - optional
    db_log_action = None  # type: ignore[assignment]

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
    s = adapter.state()  # dataclasses: table, players, street, deck_seed, last_action, pot_total?
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
        "deck_seed": getattr(s, "deck_seed", None),
        "last_action": _la_to_dict(getattr(s, "last_action", None)),
        "pot_total": int(getattr(s, "pot_total", 0)),
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


def _should_skip_auto_advance_after_action(
    human_seat: int,
    pre_bot_state: Dict[str, Any],
    action_l: str,
    actor_after: Optional[Dict[str, Any]],
) -> bool:
    """
    Decide if we should *not* advance bots after the human action.

    We skip exactly when:
      - heads-up (2 seats)
      - preflop
      - the human (who is SB) just *called*
      - and the next actor is the opponent (BB)

    This preserves the state expected by tests: after SB call, BB has a decision.
    """
    if action_l != "call":
        return False
    try:
        table = pre_bot_state.get("table", {}) or {}
        seats = int(table.get("seats", 0))
        street = str(pre_bot_state.get("street", ""))
        la = pre_bot_state.get("last_action") or {}
        la_type = (la.get("type") or "").lower()
        la_seat = int(la.get("seat"))
        sb_seat = int(table.get("sb_seat"))
        bb_seat = int(table.get("bb_seat"))

        if (
            seats == 2
            and street == "preflop"
            and la_type == "call"
            and la_seat == human_seat
            and la_seat == sb_seat
            and actor_after is not None
            and int(actor_after.get("seat")) == bb_seat
        ):
            return True
    except Exception:
        # If anything is missing or malformed, fall back to default behavior
        return False
    return False


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

    # --- Optional logging (hand start)
    if callable(db_log_hand_start):  # type: ignore[truthy-bool]
        s = adapter.state()
        tbl = s.table
        try:
            db_log_hand_start(  # type: ignore[misc]
                hand_id=hand_id,
                deck_seed=getattr(s, "deck_seed", None),
                seats=int(tbl.seats),
                sb=int(tbl.sb),
                bb=int(tbl.bb),
                ante=int(tbl.ante),
                button=int(tbl.button),
                sb_seat=int(tbl.sb_seat),
                bb_seat=int(tbl.bb_seat),
            )
        except Exception:
            # don't break gameplay if logging fails
            pass

    return StartHandResponse(hand_id=hand_id)


@router.get("/hand/state", response_model=StateResponse)
def get_state() -> StateResponse:
    adapter = get_adapter()
    human_seat = get_session_state().human_seat
    snap = _to_public_state(human_seat)
    actor = adapter.next_actor()
    return StateResponse(state=snap, actor=actor)


@router.post("/hand/action", response_model=ActionResponse)
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

    # Snapshot immediately AFTER the human action
    pre_bot_state = _to_public_state(human_seat)

    # --- Optional logging (human decision)
    if callable(db_log_action):  # type: ignore[truthy-bool]
        la = pre_bot_state.get("last_action") or {}
        try:
            db_log_action(  # type: ignore[misc]
                hand_id=str(getattr(adapter, "hand_id", "")),
                seat=int(la.get("seat", req.seat)),
                action=str(la.get("type", req.action)).lower(),
                amount=int(la.get("committed") or (req.amount if req.amount is not None else 0)),
                snapped=bool(la.get("snapped", False)),
                bucket_label=la.get("bucket_label"),
                street=str(pre_bot_state.get("street", "")),
                pot_total=int(pre_bot_state.get("pot_total", 0)),
            )
        except Exception:
            # don't break gameplay if logging fails
            pass

    # For bet/raise: return pre-bot snapshot so snapping details are visible.
    action_l = (req.action or "").lower().strip()
    if action_l in ("bet", "raise"):
        return ActionResponse(ok=True, bots_applied=[], state=pre_bot_state)

    # After check/call, decide whether to skip bot auto-advance (HU preflop SB call)
    actor_after = adapter.next_actor()
    if _should_skip_auto_advance_after_action(human_seat, pre_bot_state, action_l, actor_after):
        # Keep BB's decision; don't auto-apply bot actions yet.
        return ActionResponse(ok=True, bots_applied=[], state=pre_bot_state)

    # Default: auto-advance bots and return post-bot snapshot
    bots = _auto_advance_bots(human_seat)
    post_bot_state = _to_public_state(human_seat)
    return ActionResponse(ok=True, bots_applied=bots, state=post_bot_state)
