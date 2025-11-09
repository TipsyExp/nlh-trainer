# backend/bots/policy.py

from __future__ import annotations

import logging
import os
import concurrent.futures
from typing import Any, List, Mapping, Optional, Protocol, TypedDict, Literal, cast

from backend.policy.rng import bot_rng  # reuse existing deterministic RNG helper

log = logging.getLogger(__name__)

# Default per-decision budget (ms); can be overridden by env.
DEFAULT_BOT_TIME_BUDGET_MS = int(os.environ.get("BOT_TIME_BUDGET_MS", "150"))


class BotAction(TypedDict, total=False):
    """Action returned by a bot policy.

    - For 'bet'/'raise', 'amount' is the *total commitment* target (call + raise).
      The engine will snap this to its nearest allowed bucket.
    """

    action: Literal["check", "call", "bet", "raise", "fold"]
    amount: Optional[int]


class EngineStateView(TypedDict, total=False):
    """Minimal context a policy may use (all optional for flexibility)."""

    seat: int
    street: str
    bb: int
    to_call: int
    min_raise: int
    allowed_buckets: List[str]
    in_position: bool
    first_action_this_street: bool


class BotPolicy(Protocol):
    """Policy interface: choose a legal action given context + RNG."""

    def decide(self, ctx: Mapping[str, Any], rng: Any) -> BotAction: ...


# ------------------------- Core helpers (RNG / validation / timeout) ------------------------- #


def make_policy_rng(seed_parts: List[Any]) -> Any:
    """Create a deterministic RNG for policy decisions based on stable seed parts.

    Typical seed parts:
      [ base_seed, session_id, hand_id, decision_idx, seat, "bot" ]
    """
    norm = [str(p) for p in seed_parts]
    return bot_rng(norm)


def _safe_fallback(to_call: int) -> BotAction:
    """Conservative fallback that is always legal."""
    if int(to_call or 0) > 0:
        return {"action": "call"}
    return {"action": "check"}


def validate_bot_action(
    move: BotAction,
    *,
    to_call: int,
    allowed_buckets: List[str],
) -> Optional[BotAction]:
    """Best-effort pre-engine legality guard.

    - Prevent fold when to_call == 0 (must check).
    - Prevent check when to_call > 0 (must call/fold/raise).
    - Ensure amount present for bet/raise (engine will snap).
    - If there are no raise/bet buckets and action is bet/raise, degrade.
    """
    if not move:
        return None

    act_raw = move.get("action")
    act = str(act_raw or "").lower().strip()
    amt = move.get("amount")

    if act not in {"check", "call", "bet", "raise", "fold"}:
        return None

    # Basic legality by facing bet
    if act == "fold" and int(to_call or 0) == 0:
        return None
    if act == "check" and int(to_call or 0) > 0:
        return None

    # Bet/Raise must have an amount; engine snaps to nearest bucket.
    if act in {"bet", "raise"}:
        # If policy omitted amount, provide a minimal target so snapping can succeed.
        if amt is None:
            if act == "bet":
                move = {"action": "bet", "amount": max(0, int(to_call or 0))}
            else:
                move = {"action": "raise", "amount": max(0, int(to_call or 0))}
        # If no raise/bet buckets are available, degrade.
        if not allowed_buckets:
            return None

    return move


def decide_action_with_timeout(
    policy: BotPolicy,
    ctx: Mapping[str, Any],
    *,
    seed_parts: List[Any],
    timeout_ms: Optional[int] = None,
) -> BotAction:
    """Run a policy decision under a time budget, validate, and fallback if needed.

    Returns a *legalized* action (check/call fallback on timeout/error/invalid).
    """
    timeout = int(timeout_ms or DEFAULT_BOT_TIME_BUDGET_MS)
    rng = make_policy_rng(seed_parts)

    def _run():
        return policy.decide(ctx, rng)

    # Try to obtain a policy move within the time budget.
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_run)
            move = fut.result(timeout=timeout / 1000.0)
    except concurrent.futures.TimeoutError:
        log.warning("Policy decision timed out after %sms; using fallback", timeout)
        move = None
    except Exception as e:
        log.exception("Policy decision errored: %s; using fallback", e)
        move = None

    to_call = int(ctx.get("to_call") or 0)
    allowed_buckets = list(ctx.get("allowed_buckets") or [])

    if move is None or not isinstance(move, dict):
        return _safe_fallback(to_call)

    legal = validate_bot_action(
        cast(BotAction, move), to_call=to_call, allowed_buckets=allowed_buckets
    )
    if not legal:
        return _safe_fallback(to_call)

    return legal


__all__ = [
    "BotAction",
    "EngineStateView",
    "BotPolicy",
    "validate_bot_action",
    "make_policy_rng",
    "decide_action_with_timeout",
]
