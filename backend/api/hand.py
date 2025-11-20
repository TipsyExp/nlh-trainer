# backend/api/hand.py
"""Hand API for the NLH trainer.

This module exposes endpoints to start a new hand, query the current
state and apply actions. It wraps the PokerKit adapter and
incorporates per-decision logging via the shared SQLite logger. Each
action taken by the human or bots is recorded in the ``actions`` table
with an incrementing index. A snapshot ``GameState`` is upserted into
the ``hands`` table after every action so that exports work mid-hand.

This patched version consolidates configuration by importing all
runtime flags from ``backend.config``. In particular:

* ``HAND_AUTO_ENABLED`` controls both exposure of the ``POST /api/hand/auto``
  endpoint and whether bots automatically advance after a human action.
* ``BOT_MAX_STEPS`` and ``BOT_TIME_BUDGET_MS`` define autoplay limits and
  decision timeouts respectively.
* ``BOT_PROFILE`` selects the bot policy (CALLCHECK or TAG).

The previous ``ALLOW_DEV_AUTO`` flag has been removed – any auto-advance
behaviour is now governed solely by ``HAND_AUTO_ENABLED``.
"""

from __future__ import annotations

import concurrent.futures
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.adapters.engines import get_adapter
from backend.api.session import get_session_state
from backend.logger import get_logger
from backend.models import (
    ActionRecord,
    ActionType,
    GameState,
    PlayerState,
    PlayerStatus,
    SeatType,
    Street,
    TableState,
)
from backend.policy.bot_profiles import BaseBotPolicy, CallCheckBot, TagBot
from backend.policy.rng import bot_rng

# Pull configuration from a single source of truth.  These imports expose
# parsed environment variables as constants.  See backend/config.py for details.
from backend.config import (
    BOT_MAX_STEPS,
    BOT_PROFILE,
    BOT_TIME_BUDGET_MS,
    HAND_AUTO_ENABLED,
)

# NOTE: no prefix here; app/main.py includes this router with prefix="/api".
router = APIRouter(tags=["hand"])

log = logging.getLogger(__name__)

# ---------- Per-hand indexing ----------

# Maintain a mapping from hand_id to the next action index. This allows
# actions to be logged in order even when bots act between human
# decisions.
_ACTION_IDX: Dict[str, int] = {}


def _hand_auto_enabled() -> bool:
    """
    Determine whether hand auto-advance is enabled.

    Priority:
      1. Explicit HAND_AUTO_ENABLED environment variable (for tests / runtime overrides).
      2. backend.config.HAND_AUTO_ENABLED (loaded from .env at startup).
    """
    env_val = os.environ.get("HAND_AUTO_ENABLED")
    if env_val is not None:
        v = env_val.strip().lower()
        return v in {"1", "true", "yes", "on"}
    return bool(HAND_AUTO_ENABLED)


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
    """Select a bot policy based on configuration. Default remains CALL/CHECK."""
    name = BOT_PROFILE.strip().upper()
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

    Rules:
      - Reveal human_seat hole cards; mask others with ["XX","XX"].
      - On showdown, reveal all hole cards.
      - Board flows straight from engine snapshot.
      - Include actor/allowed context derived from engine.next_actor().
    """
    adapter = get_adapter()
    s = adapter.state()
    tbl = s.table

    # Reveal policy
    reveal_all = str(s.street) == "showdown"

    # Players: reveal for human, mask others (unless showdown)
    players: List[Dict[str, Any]] = []
    for i, p in enumerate(s.players):
        if reveal_all or i == human_seat:
            players.append({"seat": i, "hole_cards": list(p.hole_cards)})
        else:
            players.append({"seat": i, "hole_cards": ["XX", "XX"]})

    # Current actor / allowed
    actor = adapter.next_actor()
    to_act: Optional[int] = int(actor["seat"]) if actor else None
    allowed: Optional[Dict[str, Any]] = None
    if actor:
        allowed = {
            "to_call": int(actor.get("to_call", 0)),
            "min_raise": int(actor.get("min_raise", 0)),
            "allowed_buckets": list(actor.get("allowed_buckets", [])),
        }

    # Board: pass-through from engine (fallback to empty shape preflop)
    board = getattr(s, "board", None) or {"flop": [], "turn": [], "river": []}

    resp: Dict[str, Any] = {
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
        "street": str(s.street),
        "board": board,
        "deck_seed": s.deck_seed,
        "pot_total": int(getattr(s, "pot_total", 0)),
        "to_act": to_act,
        "allowed": allowed,
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
    first_action_this_street = (int(actor.get("to_call", 0)) == 0) and (
        last_type not in ("bet", "raise")
    )

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


# ---------- Bot decision helpers (timeout + validation + fallback) ----------


def _safe_fallback(actor: Dict[str, Any]) -> Tuple[str, Optional[int]]:
    """Return a conservative legal fallback given actor context."""
    to_call = int(actor.get("to_call", 0) or 0)
    if to_call > 0:
        return "call", None
    return "check", None


def _decide_with_timeout(
    policy: BaseBotPolicy, ctx: Dict[str, Any], rng, timeout_ms: int
) -> Optional[Dict[str, Any]]:
    """Run policy.decide with a time budget; return None on timeout/error."""

    def _run():
        return policy.decide(ctx, rng)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_run)
            return fut.result(timeout=timeout_ms / 1000.0)
    except concurrent.futures.TimeoutError:
        log.warning("Bot decision timed out after %sms; using fallback", timeout_ms)
        return None
    except Exception as e:
        log.exception("Bot decision errored: %s; using fallback", e)
        return None


def _validate_decision(
    decision: Dict[str, Any], actor: Dict[str, Any]
) -> Optional[Tuple[str, Optional[int]]]:
    """Lightweight legality checks before handing to engine (engine still authoritative)."""
    if not decision:
        return None
    action = str(decision.get("action", "")).lower().strip()
    amount = decision.get("amount")
    to_call = int(actor.get("to_call", 0) or 0)

    if action not in {"fold", "check", "call", "bet", "raise"}:
        return None
    if action == "fold" and to_call == 0:
        return None  # illegal to fold when free to check
    if action == "check" and to_call > 0:
        return None  # illegal to check when facing a bet
    if action in {"bet", "raise"} and amount is None:
        return None  # amount required

    # Bucket/amount exact legality is enforced by engine snap; we only prevent obvious illegals.
    return action, amount


def _apply_bot_action_with_fallback(
    hand_id: str,
    actor: Dict[str, Any],
    policy: BaseBotPolicy,
    timeout_ms: int,
) -> Tuple[str, Optional[int]]:
    """Decide and apply a bot action with timeout and safe fallback on error."""
    # Deterministic RNG for this exact decision
    ss = get_session_state()
    next_idx = _get_next_db_idx(hand_id)
    rng = bot_rng(
        [
            ss.base_seed or "",
            ss.logger_session_id,
            hand_id,
            next_idx,
            int(actor["seat"]),
            "bot",
        ]
    )

    ctx = _build_actor_ctx_for_policy(actor)
    decision = _decide_with_timeout(policy, ctx, rng, timeout_ms)
    validated = _validate_decision(decision or {}, actor)
    if not validated:
        action, amount = _safe_fallback(actor)
        return action, amount
    action, amount = validated

    adapter = get_adapter()
    try:
        adapter.apply_action(actor["seat"], action, amount)
        return action, amount
    except Exception as e:
        # If the engine rejects (e.g., snap/legality mismatch), degrade to safe fallback.
        log.warning(
            "Engine rejected bot action %s/%s: %s; using fallback", action, amount, e
        )
        # Try fallback exactly once
        fb_action, fb_amount = _safe_fallback(actor)
        adapter.apply_action(actor["seat"], fb_action, fb_amount)
        return fb_action, fb_amount


def _auto_advance_bots(hand_id: str, human_seat: int) -> List[Dict[str, Any]]:
    """
    Loop while it's a bot's turn. Returns a list of bot actions taken.
    Each bot action is applied to the engine and recorded via the logger.
    Emits an error if the loop guard is exceeded.
    """
    adapter = get_adapter()
    hand_id = _hand_id_str(hand_id)

    actions_taken: List[Dict[str, Any]] = []
    policy = _select_bot_policy()

    hit_cap = True  # assume worst; set False when we break normally
    for step_idx in range(BOT_MAX_STEPS):
        actor = adapter.next_actor()
        if not actor or int(actor["seat"]) == human_seat:
            hit_cap = False
            break

        # Decide+apply with timeout and fallback.
        action, amount = _apply_bot_action_with_fallback(
            hand_id=hand_id,
            actor=actor,
            policy=policy,
            timeout_ms=BOT_TIME_BUDGET_MS,
        )

        # Log the bot action (post-apply)
        _log_action(hand_id, int(actor["seat"]), action, amount)
        actions_taken.append(
            {"seat": int(actor["seat"]), "action": action, "amount": amount}
        )

    if hit_cap:
        # Guard fired; surface loudly and make diagnoseable
        msg = (
            f"auto-advance bot loop cap exceeded "
            f"(max={BOT_MAX_STEPS}, hand_id={hand_id})"
        )
        log.error(msg)
        raise RuntimeError(msg)

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

    # Reset index for this hand (normalize key to string to avoid int vs str collisions)
    hid = _hand_id_str(hand_id)
    _ACTION_IDX[hid] = 0
    # Also ensure DB-derived next idx starts at 0 by not relying on previous hand rows

    # Ensure a parent hand row exists *before* any actions are logged
    _persist_snapshot(hand_id)

    # Auto-advance bots immediately to first human decision (if any)
    ss = get_session_state()
    human_seat = ss.human_seat
    if getattr(ss, "bot_mode", "heuristic") != "none":
        try:
            _auto_advance_bots(hid, human_seat)
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    # Refresh snapshot so exports can see the post-bot state
    _persist_snapshot(hand_id)

    return StartHandResponse(hand_id=_hand_id_str(hand_id))


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
    ss = get_session_state()
    human_seat = ss.human_seat

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

    # Build the snapshot to return (reflects the human's move).
    state_pre = _to_public_state(human_seat)

    # NOTE:
    # We intentionally do NOT auto-advance bots here. Callers that want to
    # advance to the next human decision should use POST /api/hand/auto`,
    # which is gated by HAND_AUTO_ENABLED via `_hand_auto_enabled()`.
    bots: List[Dict[str, Any]] = []

    return ActionResponse(ok=True, bots_applied=bots, state=state_pre)


@router.post("/hand/auto", response_model=ActionResponse)
def auto_advance() -> ActionResponse:
    """
    Dev helper: advance all bot actions until it's the human's turn (or hand ends).
    Returns the updated state and a list of bot actions applied.
    """
    if not _hand_auto_enabled():
        # Consistent with coach gating, return a clear 501 that the UI can label as "disabled"
        raise HTTPException(status_code=501, detail="hand auto endpoint disabled")

    adapter = get_adapter()
    human_seat = get_session_state().human_seat

    # Determine current hand id
    hand_id_any = getattr(adapter, "hand_id", None)
    if not hand_id_any:
        # If we have no recorded actions and no adapter hand_id, there's no hand.
        if not _ACTION_IDX:
            raise HTTPException(status_code=400, detail="no hand in progress")
        hand_id = next(reversed(_ACTION_IDX.keys()))
    else:
        hand_id = _hand_id_str(hand_id_any)

    # Advance bots
    try:
        bots = _auto_advance_bots(hand_id, human_seat)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    # Persist and return state
    _persist_snapshot(hand_id)
    state = _to_public_state(human_seat)
    return ActionResponse(ok=True, bots_applied=bots, state=state)
