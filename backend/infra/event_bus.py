# backend/infra/event_bus.py
"""
Central event emitter / bus for debug & dev instrumentation.

Goals:
- Read a request ID from context (middleware-provided); never fabricate one.
- Never infer actor_before from current engine state; require the caller
  to pass actor_before that was captured **before** any mutations.
- Compute deltas vs. previous events and keep a ring buffer for quick inspection.
- Be hand-aware so simple invariants (like pot monotonicity) are checked per hand.

Usage (from an engine or API layer):

    from backend.infra.event_bus import bus, set_request_id, RequestIdContextMiddleware

    # In FastAPI app setup:
    app.add_middleware(RequestIdContextMiddleware)

    # In a request handler, if you already have a req_id, set it (optional; middleware does this):
    token = set_request_id(req_id)  # keep token to reset if needed

    # Emitting an action event after applying state changes:
    bus.emit(
        kind="action",
        actor_before=actor_before_captured_pre_mutation,
        actor_after=current_next_to_act,
        street=current_street,
        price=current_price,
        pot=current_pot,
        committed=current_committed_list,
        extras={
            "hand_id": hand_id,    # helps per-hand invariants
            "seat": seat,          # actor seat for convenience
            "action": "raise",     # any payload
            "next_actor": current_next_to_act,
            # ... anything else you want to carry
        },
    )

    # To fetch recent events (dev-only surfaces):
    events = bus.get_events_since(since=0, limit=200)
"""

from __future__ import annotations

import hashlib
import os
import time
from collections import deque
from contextlib import contextmanager
from typing import Any, Deque, Dict, List, Optional

import contextvars
from starlette.types import ASGIApp, Receive, Scope, Send

# Enable/disable emission globally (mirrors engine flag to keep behavior consistent)
DEBUG_EVENTS_ENABLED = os.getenv("ENGINE_DEBUG_HTTP", "0").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# -----------------------------------------------------------------------------
# Request ID context propagation (never fabricate; we only read what middleware sets)

_REQUEST_ID: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)


def get_request_id() -> Optional[str]:
    """Return the current request id set by middleware or None if unset."""
    return _REQUEST_ID.get()


def set_request_id(req_id: Optional[str]):
    """
    Set current req_id for the context. Returns a token you can use to reset.
    NOTE: We do NOT fabricate IDs here; pass None to clear.
    """
    return _REQUEST_ID.set(req_id)


def reset_request_id(token) -> None:
    """Reset the request id context to a previous token."""
    try:
        _REQUEST_ID.reset(token)
    except Exception:
        # Never let reset failures break the request
        pass


@contextmanager
def request_id_context(req_id: Optional[str]):
    """Convenience context manager to set/restore request id."""
    token = set_request_id(req_id)
    try:
        yield
    finally:
        reset_request_id(token)


class RequestIdContextMiddleware:
    """
    Starlette/FastAPI middleware to attach a request ID to the context.
    Reads from `X-Request-ID` header (preferred) or `request.state.req_id` if present.
    IMPORTANT: we do NOT generate a new id when none is present; that avoids fabricating req_id.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin1"): v.decode("latin1") for k, v in scope.get("headers", [])
        }
        req_id = headers.get("x-request-id")
        # Starlette sticks state on scope under 'state' only after request object creation,
        # so we can't reliably read scope['state'] here. We only honor header here.
        token = set_request_id(req_id)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_request_id(token)


# -----------------------------------------------------------------------------
# Event bus


class EventBus:
    """
    Minimal central event bus with:
      - ring buffer of recent events
      - per-hand previous-state snapshot for delta/invariant checks
      - explicit actor_before/actor_after handling
    """

    def __init__(self, ring_max: int = 300) -> None:
        self._ring: Deque[Dict[str, Any]] = deque(maxlen=ring_max)
        self._seq: int = 0
        # Track previous state per-stream. Use hand_id as stream key when available; fallback to "global".
        self._prev_state_by_stream: Dict[str, Dict[str, Any]] = {}

    # -------------------
    # Public API
    # -------------------

    def emit(
        self,
        *,
        kind: str,
        actor_before: Optional[int],
        actor_after: Optional[int],
        street: str,
        price: int,
        pot: int,
        committed: List[int],
        extras: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Emit an event. Caller is responsible for capturing actor_before **pre-mutation**.
        We will NOT derive actor_before from any mutable state to avoid fabrication.

        `actor_after` should reflect the post-mutation next-to-act (or None).
        `extras` can include any additional structured fields; recommended keys:
            - hand_id: str
            - next_actor: Optional[int] (should match actor_after)
            - seat, action, requested, committed_total, snapped, bucket, etc.
        """
        if not DEBUG_EVENTS_ENABLED:
            return

        extras = dict(extras or {})

        # Resolve a stream key for per-hand deltas/invariants
        hand_id = str(extras.get("hand_id") or "global")

        # Increment sequence & capture ts
        self._seq += 1
        ts_ms = int(time.time() * 1000)

        # Build "current state" (post-mutation). `to_act` is actor_after by definition.
        current_state: Dict[str, Any] = {
            "street": str(street),
            "price": int(price),
            "pot": int(pot),
            "to_act": None if actor_after is None else int(actor_after),
            "committed": [int(x) for x in committed],
        }

        # Compute a cheap hash of the essential state (post-mutation)
        state_hash_input = (
            current_state["street"],
            current_state["price"],
            current_state["pot"],
            current_state["to_act"],
            tuple(current_state["committed"]),
        )
        state_hash = hashlib.sha256(str(state_hash_input).encode("utf-8")).hexdigest()[
            :8
        ]

        # Delta vs previous for this stream
        prev_state = self._prev_state_by_stream.get(hand_id)
        delta: Dict[str, Any] = {}
        if prev_state is not None:
            for key in ("street", "price", "pot", "to_act"):
                old = prev_state.get(key)
                new = current_state[key]
                if old != new:
                    delta[key] = {"from": old, "to": new}
            if prev_state.get("committed") != current_state["committed"]:
                delta["committed"] = {
                    "from": prev_state.get("committed"),
                    "to": current_state["committed"],
                }

        # Basic invariants (advisory only)
        pot_non_decreasing = True
        try:
            if prev_state is not None:
                prev_pot = int(prev_state.get("pot", 0))
                pot_non_decreasing = int(current_state["pot"]) >= prev_pot
        except Exception:
            # Never fail emission on invariant computation
            pass

        # Assemble final record. We DO NOT fabricate req_id or actor_before.
        evt: Dict[str, Any] = {
            "ts_ms": ts_ms,
            "seq": self._seq,
            "kind": kind,
            "street": current_state["street"],
            "pot": current_state["pot"],
            "price": current_state["price"],
            "to_act": actor_before,  # for compatibility with previous UIs (actor at time of action)
            "actor_before": actor_before,
            "actor_after": actor_after,
            "delta": delta,
            "state_hash": state_hash,
            "req_id": get_request_id(),  # may be None if middleware didn't set a header
            "invariants": {
                "pot_non_decreasing": pot_non_decreasing,
            },
            **extras,
        }

        self._ring.append(evt)
        # Update previous post-mutation state for this stream
        self._prev_state_by_stream[hand_id] = current_state

    def get_events_since(
        self, *, since: int = 0, limit: int = 200
    ) -> List[Dict[str, Any]]:
        """Fetch events with seq > since (dev-only convenience)."""
        if not DEBUG_EVENTS_ENABLED:
            return []
        items: List[Dict[str, Any]] = list(self._ring)
        out: List[Dict[str, Any]] = []
        for e in items:
            try:
                s = int(e.get("seq", 0))
            except Exception:
                continue
            if s > since:
                out.append(e)
        if limit > 0:
            out = out[-int(limit) :]
        return out

    def clear(self) -> None:
        """Clear ring and prev-state map (dev-only)."""
        self._ring.clear()
        self._prev_state_by_stream.clear()


# Singleton bus
bus = EventBus()
