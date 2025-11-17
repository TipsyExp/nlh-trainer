# backend/services/equity/service.py
from __future__ import annotations

import os
from typing import Optional, Sequence, Tuple

from .base import Card, EquityBackend, EquityResult, PlayerSpec
from .backends.ompeval_backend import OmpevalBackend
from .backends.eval7_backend import Eval7Backend
from .backends.pokerkit_backend import PokerKitBackend


class EquityService:
    """
    High-level orchestrator for equity calculations.

    Responsibilities:
      - Instantiate available backends (ompeval, eval7, pokerkit).
      - Select a backend according to EQUITY_BACKEND_POLICY and input shape.
      - Provide a single `calc_equity` entry point for callers (API/CLI/coach).
      - Offer small convenience helpers (e.g. hero vs villain range equity).
    """

    def __init__(self) -> None:
        # Policy: how we choose which backend to use.
        #   auto     -> first compatible backend (ompeval -> eval7 -> pokerkit)
        #   ompeval  -> force OMPEval backend
        #   eval7    -> force Eval7 backend
        #   pokerkit -> force PokerKit fallback
        self._policy = os.getenv("EQUITY_BACKEND_POLICY", "auto").lower()

        backends: list[EquityBackend] = []

        def _maybe_add(backend_ctor) -> None:
            try:
                b = backend_ctor()
            except Exception:
                return
            # Only register if the backend reports itself as available.
            try:
                if hasattr(b, "is_available") and b.is_available():
                    backends.append(b)
            except Exception:
                # Defensive: if availability check itself errors, skip it.
                return

        # Order matters for `auto` fallback.
        _maybe_add(OmpevalBackend)  # OMPEval (ranges + hands; MC or exact; multiway)
        _maybe_add(Eval7Backend)  # Eval7 (pure-Python/Cython; ranges via MC)
        _maybe_add(PokerKitBackend)  # Compatibility fallback (hands-only wrapper)

        self._backends: list[EquityBackend] = backends

    def _choose(self, wants_ranges: bool) -> EquityBackend:
        """
        Pick a backend consistent with the configured policy and input shape.
        """

        def _find(name: str) -> EquityBackend | None:
            for b in self._backends:
                if (
                    getattr(b, "name", "") == name
                    and getattr(b, "is_available", lambda: False)()
                ):
                    return b
            return None

        # Forced policies first with friendly errors (only if actually available).
        if self._policy == "ompeval":
            b = _find("ompeval")
            if b is None:
                raise RuntimeError(
                    "Policy 'ompeval' selected but OMPEval is unavailable"
                )
            if wants_ranges and not b.supports_ranges():
                raise RuntimeError(
                    "Policy 'ompeval' selected but it does not support ranges"
                )
            return b

        if self._policy == "eval7":
            b = _find("eval7")
            if b is None:
                raise RuntimeError(
                    "Policy 'eval7' selected but Eval7 backend is unavailable"
                )
            if wants_ranges and not b.supports_ranges():
                raise RuntimeError(
                    "Policy 'eval7' selected but it does not support ranges"
                )
            return b

        if self._policy == "pokerkit":
            b = _find("pokerkit")
            if b is None:
                raise RuntimeError(
                    "Policy 'pokerkit' selected but PokerKit backend is unavailable"
                )
            if wants_ranges and not b.supports_ranges():
                raise RuntimeError(
                    "Policy 'pokerkit' selected but it does not support ranges"
                )
            return b

        # Auto: walk configured backends in order, skipping those that can't handle
        # the requested input style (e.g. ranges) or are unavailable.
        for backend in self._backends:
            try:
                if wants_ranges and not backend.supports_ranges():
                    continue
            except Exception:
                # If backend can't even answer supports_ranges, skip it.
                continue
            # is_available() already enforced at registration time, but keep defensive.
            if hasattr(backend, "is_available") and not backend.is_available():
                continue
            return backend

        # If we get here, nothing can satisfy the request.
        raise RuntimeError("No equity backend available for requested mode")

    def calc_equity(
        self,
        players: Sequence[PlayerSpec],
        board: Sequence[Card] = (),
        dead: Sequence[Card] = (),
        iters: Optional[int] = None,
        exact: bool = False,
        timeout_ms: Optional[int] = None,
    ) -> EquityResult:
        """
        Compute equity for the given players and board/dead cards.

        This simply selects an appropriate backend and delegates the call.
        """
        wants_ranges = any(p.range is not None for p in players)
        backend = self._choose(wants_ranges)
        return backend.calc_equity(
            players=players,
            board=board,
            dead=dead,
            iters=iters,
            exact=exact,
            timeout_ms=timeout_ms,
        )

    # ------------------------------------------------------------------ #
    # Convenience helpers
    # ------------------------------------------------------------------ #

    def hero_vs_range_equity(
        self,
        hero_hand: Tuple[Card, Card],
        villain_range: str,
        board: Sequence[Card] = (),
        dead: Sequence[Card] = (),
        iters: Optional[int] = None,
        exact: bool = False,
        timeout_ms: Optional[int] = None,
    ) -> float:
        """
        Convenience helper: compute hero's equity vs a single villain range.

        This is primarily intended for preflop advisor / HU defend rules.
        Assumes:
          - seat 0: hero fixed hand
          - seat 1: villain range string

        Returns:
          Hero equity as a float in [0.0, 1.0].

        Raises:
          Whatever `calc_equity` would raise, e.g. RuntimeError if no
          ranges-capable backend is available under the current policy.
        """
        result = self.calc_equity(
            players=[
                PlayerSpec(hand=hero_hand),
                PlayerSpec(range=villain_range),
            ],
            board=board,
            dead=dead,
            iters=iters,
            exact=exact,
            timeout_ms=timeout_ms,
        )
        if not result.per_player:
            raise RuntimeError("equity result contained no players")
        hero = result.per_player[0]
        return float(hero.get("equity", 0.0))
