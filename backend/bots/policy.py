from __future__ import annotations

from typing import Any, List, Mapping, Optional, Protocol, TypedDict, Literal


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


def validate_bot_action(
    move: BotAction,
    *,
    to_call: int,
    allowed_buckets: List[str],
) -> BotAction:
    """Best-effort guard to ensure 'amount' exists for bet/raise.

    We *don’t* know the adapter's bucket targets here; we rely on engine snapping.
    So if amount is missing, we set it to at least 'to_call' so the engine
    can snap to a valid raise/bet bucket.

    Note: Some engines may not accept 'fold'. If you need to hard-coerce folds,
    do it at the call site (e.g., replace with 'check' when to_call == 0).
    """
    act = move.get("action", "check")
    if act in ("bet", "raise"):
        amt = move.get("amount")
        if amt is None:
            move = {"action": act, "amount": max(0, int(to_call))}
    return move


__all__ = ["BotAction", "EngineStateView", "BotPolicy", "validate_bot_action"]
