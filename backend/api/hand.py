"""Hand API for the NLH trainer.

This module exposes endpoints to start a new hand, query the current
state and apply actions. It wraps the PokerKit adapter and
incorporates per-decision logging via the shared SQLite logger. Each
action taken by the human or bots is recorded in the ``actions`` table
with an incrementing index. A snapshot ``GameState`` is upserted into
the ``hands`` table after every action so that exports work mid-hand.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.adapters.engines import get_adapter
from backend.api.session import get_session_state
from backend.logger import get_logger
from backend.policy.bot_profiles import CallCheckBot, TagBot, BaseBotPolicy
from backend.policy.rng import bot_rng
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

# ---------- Per-hand indexing ----------

# Maintain a mapping from hand_id to the next action index. This allows
# actions to be logged in order even when bots act between human
# decisions.
_ACTION_IDX: Dict[str, int] = {}


def _get_next_db_idx(hand_id: str) -> int:
    """Read the current max idx for this hand from DB and return the next value.
    This prevents UNIQUE(idx) collisions when process state drifts or after errors.
    """
    logger = get_logger()
    cur = logger.conn.cursor()  # type: ignore[attr-defined]
    row = cur.execute(
        "SELECT COALESCE(MAX(idx), -1) + 1 AS next_idx FROM actions WHERE hand_id = ?",
        (hand_id,),
    ).fetchone()
    return int(row["next_idx"] if row and "next_idx" in row.keys() else 0)


# ---------- Bot policy selection ----------

def _select_bot_policy() -> BaseBotPolicy:
    """Select a bot policy based on environment. Default remains CALL/CHECK."""
    name = os.environ.get("BOT_PROFILE", "CALLCHECK").strip().upper()
    if name == "TAG":
        return TagBot()
    # default
    return CallCheckBot()


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


def _hand_id_str(h: Any) -> str:
    """Coerce adapter hand id to string form (e.g., 1 -> 'H1')."""
    if isinstance(h, str):
        return h
    if isinstance(h, int):
        return f"H{h}"
    return str(h)


def _la_to_dict(la: Any) -> Optional[Dict[str, Any]]:
    """
    Adapter's last_action may be a dataclass or dict. Normalize to dict or None.
    """
    if la is None:
        return None
    if isinstance(la, dict):
        return la
    # Dataclass-like: try to read expected fields
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
    Convert adapter.state() dataclasses to a JSON-friendly dict snapshot.
    Hide opponents' hole cards (mask to 'XX').
    """
    adapter = get_adapter()
    s = (
        adapter.state()
    )  # dataclasses: table, players, street, deck_seed, last_action, pot_total
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
        "pot_total": int(getattr(s, "pot_total", 0)),  # surface the pot
        "last_action": _la_to_dict(getattr(s, "last_action", None)),
    }
    return resp


def _build_actor_ctx_for_policy(actor: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble context the policy needs (street, IP flag, first-action-this-street, etc.)."""
    adapter = get_adapter()
    s = adapter.state()
    tbl = s.table
    seat = int(actor.get("seat", -1))
    # Postflop IP heuristic in HU: button acts last on flop/turn/river
    is_postflop = str(s.street) in ("flop", "turn", "river")
    in_position = is_postflop and (seat == int(tbl.button))
    # "First action on this street" ≈ to_call==0 and last_action is not bet/raise
    la = getattr(s, "last_action", None)
    last_type = getattr(la, "type", None) if la else None
    first_action_this_street = (int(actor.get("to_call", 0)) == 0) and (last_type not in ("bet", "raise"))

    ctx = {
        "seat": seat,
        "street": str(s.street),
        "bb": int(tbl.bb),
        "to_call": int(actor.get("to_call", 0)),
        "min_raise": int(actor.get("min_raise", 0)),
        "allowed_buckets": list(actor.get("allowed_buckets", [])),
        "in_position": bool(in_position),
        "first_action_this_street": bool(first_action_this_street),
        # raw bits the policy might find handy
        "button": int(tbl.button),
        "sb_seat": int(tbl.sb_seat),
        "bb_seat": int(tbl.bb_seat),
    }
    return ctx


def _log_action(hand_id: str, seat: int, action: str, amount: Optional[int]) -> None:
    """Internal helper to record an action to the logger.

    Updates the per-hand action index and writes a row to the actions table.
    Extracts metadata from the adapter snapshot to populate bucket/snapped/etc.
    Also computes pot_after and to_call_after based on the *post-action* state.
    """
    hand_id = _hand_id_str(hand_id)

    logger = get_logger()
    adapter = get_adapter()
    # Determine index robustly from DB to avoid UNIQUE collisions.
    # Keep the in-memory counter in sync afterwards.
    try:
        idx = _get_next_db_idx(hand_id)
    except Exception:
        # Fallback to in-memory counter if DB read fails
        idx = _ACTION_IDX.get(hand_id, 0)

    # Grab a post-action snapshot of state (caller must call this AFTER apply_action)
    snap = adapter.state()
    street = snap.street

    # Extract last action metadata if available
    la = getattr(snap, "last_action", None)
    bucket_label: Optional[str] = None
    snapped_val: Optional[int] = None
    meta_json: Optional[str] = None
    if la is not None:
        bucket_label = getattr(la, "bucket_label", None)
        snap_flag = getattr(la, "snapped", None)
        if snap_flag is not None:
            snapped_val = 1 if snap_flag else 0
        allowed = getattr(la, "allowed_buckets", None)
        if allowed is not None:
            import json as _json

            meta_json = _json.dumps({"allowed_buckets": allowed})

    # Post-action pot
    pot_after = (
        int(getattr(snap, "pot_total", 0))
        if getattr(snap, "pot_total", None) is not None
        else None
    )

    # Post-action to_call (for the *next* actor, if any)
    to_call_after: Optional[int] = None
    next_actor = adapter.next_actor()
    if next_actor:
        try:
            to_call_after = int(next_actor.get("to_call", 0))
        except Exception:
            to_call_after = None
    else:
        # Hand likely complete; nothing to call
        to_call_after = 0

    # Persist the action with full provenance
    logger.log_action(
        hand_id=hand_id,
        idx=idx,
        street=street,
        actor_seat=seat,
        type=(action or "").lower().strip(),
        amount=amount,
        bucket=bucket_label,
        to_call_after=to_call_after,
        pot_after=pot_after,
        time_ms=None,  # could be added later if timing is recorded
        rng_seed=snap.deck_seed,
        snapped=snapped_val,
        meta=meta_json,
        engine="PokerKit",
        evaluator="PokerKit",
    )

    # Increment the index for next action
    _ACTION_IDX[hand_id] = idx + 1


def _auto_advance_bots(hand_id: str, human_seat: int) -> List[Dict[str, Any]]:
    """
    Loop while it's a bot's turn. Returns a list of bot actions taken.
    Each bot action is applied to the engine and recorded via the logger.
    """
    adapter = get_adapter()
    hand_id = _hand_id_str(hand_id)

    actions_taken: List[Dict[str, Any]] = []
    policy = _select_bot_policy()

    # safety to avoid infinite loops
    for _ in range(100):
        actor = adapter.next_actor()
        if not actor:
            break
        if int(actor["seat"]) == human_seat:
            break

        # Build deterministic RNG for this exact decision
        ss = get_session_state()
        next_idx = _get_next_db_idx(hand_id)
        rng = bot_rng([ss.base_seed or "", ss.logger_session_id, hand_id, next_idx, int(actor["seat"]), "bot"])

        # Build policy context and get decision
        ctx = _build_actor_ctx_for_policy(actor)
        decision = policy.decide(ctx, rng)
        action = str(decision.get("action", "check")).lower().strip()
        amount = decision.get("amount")

        # Apply
        adapter.apply_action(actor["seat"], action, amount)
        # Log the bot action (post-apply)
        _log_action(hand_id, actor["seat"], action, amount)
        actions_taken.append(
            {"seat": actor["seat"], "action": action, "amount": amount}
        )
    return actions_taken


def _persist_snapshot(hand_id: str) -> None:
    """Build a GameState from the adapter snapshot and persist to ``hands``.

    We INSERT on first write, and UPDATE thereafter to avoid REPLACE's
    delete-then-insert behavior (which breaks FKs mid-hand).
    """
    hand_id = _hand_id_str(hand_id)

    adapter = get_adapter()
    logger = get_logger()
    s = adapter.state()
    tbl = s.table

    # Build TableState
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

    # Actions: reconstruct from DB so state JSON reflects full history
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

    # Seats
    dealer_seat = int(tbl.button)
    sb_seat = int(tbl.sb_seat)
    bb_seat = int(tbl.bb_seat)

    # Build snapshot
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

    # Insert or update without breaking FKs
    cur = logger.conn.cursor()  # type: ignore[attr-defined]
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    # Check if hand row exists
    exists = cur.execute(
        "SELECT 1 FROM hands WHERE hand_id = ? LIMIT 1", (hand_id,)
    ).fetchone()
    if exists is None:
        # First write: insert a fresh parent row
        cur.execute(
            """
            INSERT INTO hands (hand_id, session_id, deck_seed, engine, evaluator, created_at, state_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hand_id,
                ss.logger_session_id,
                s.deck_seed,
                "PokerKit",
                "PokerKit",
                now_iso,
                state.model_dump_json(),
            ),
        )
    else:
        # Subsequent writes: update in place (no REPLACE)
        cur.execute(
            """
            UPDATE hands
               SET session_id = ?,
                   deck_seed   = ?,
                   engine      = ?,
                   evaluator   = ?,
                   created_at  = ?,
                   state_json  = ?
             WHERE hand_id     = ?
            """,
            (
                ss.logger_session_id,
                s.deck_seed,
                "PokerKit",
                "PokerKit",
                now_iso,
                state.model_dump_json(),
                hand_id,
            ),
        )
    logger.conn.commit()  # type: ignore[attr-defined]


# ---------- Routes ----------


@router.post("/hand/start", response_model=StartHandResponse)
def start_hand() -> StartHandResponse:
    """Begin a new hand and auto-advance bots until the first human decision."""
    adapter = get_adapter()
    try:
        hand_id = adapter.start_hand()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"start_hand failed: {e}") from e

    # Reset index for this hand
    _ACTION_IDX[hand_id] = 0
    # Also ensure DB-derived next idx starts at 0 by not relying on previous hand rows

    # Ensure a parent hand row exists *before* any actions are logged
    _persist_snapshot(hand_id)

    # Auto-advance bots immediately to first human decision (if any)
    human_seat = get_session_state().human_seat
    _auto_advance_bots(hand_id, human_seat)

    # Refresh snapshot so exports can see the post-bot state
    _persist_snapshot(hand_id)

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
    """Apply a human action and auto-advance bots.

    The human's action is applied to the engine, logged via the logger
    and then bots are auto-advanced. We upsert a hand snapshot after
    each action so exports work mid-hand.
    """
    adapter = get_adapter()
    human_seat = get_session_state().human_seat

    # Only the configured human seat may act
    if req.seat != human_seat:
        raise HTTPException(
            status_code=400, detail="Only the configured human seat may post actions."
        )

    # Determine current hand id from the adapter (internal counter is an int); normalize.
    hand_id_any = getattr(adapter, "hand_id", None)
    if hand_id_any:
        hand_id = _hand_id_str(hand_id_any)
    else:
        if not _ACTION_IDX:
            raise HTTPException(status_code=400, detail="no hand in progress")
        # use most recent key
        hand_id = next(reversed(_ACTION_IDX.keys()))

    # Ensure the parent hand row exists *before* inserting an action
    logger = get_logger()
    if logger.fetch_hand_state_json(hand_id) is None:
        _persist_snapshot(hand_id)

    # Apply the human action
    try:
        adapter.apply_action(req.seat, req.action, req.amount)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"apply_action failed: {e}") from e

    # Log the human action (post-apply)
    _log_action(hand_id, req.seat, req.action, req.amount)

    # Persist snapshot immediately after human action
    _persist_snapshot(hand_id)

    # Snapshot to return in bet/raise case (pre-bot view for snapping visibility)
    human_pre_bot_state = _to_public_state(human_seat)

    # For bet/raise: return pre-bot snapshot so snapping details are visible.
    action_l = (req.action or "").lower().strip()
    if action_l in ("bet", "raise"):
        return ActionResponse(ok=True, bots_applied=[], state=human_pre_bot_state)

    # Auto-advance bots and return post-bot snapshot (e.g., HU SB-call -> BB-check -> flop).
    bots = _auto_advance_bots(hand_id, human_seat)

    # Persist snapshot after bot auto-advance as well
    _persist_snapshot(hand_id)

    post_bot_state = _to_public_state(human_seat)
    return ActionResponse(ok=True, bots_applied=bots, state=post_bot_state)
