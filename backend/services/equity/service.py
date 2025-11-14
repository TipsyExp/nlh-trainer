# backend/services/equity/service.py
from __future__ import annotations

import os
from typing import Optional, Sequence, Tuple

from .base import Card, EquityBackend, EquityResult, PlayerSpec
from .pbots_backend import PbotsBackend
from .pokerkit_backend import PokerKitBackend
from .henry_backend import HenryBackend


class EquityService:
    """
    High-level orchestrator for equity calculations.

    Responsibilities:
      - Instantiate available backends (pbots_calc, henry, pokerkit).
      - Select a backend according to EQUITY_BACKEND_POLICY and input shape.
      - Provide a single `calc_equity` entry point for callers (API/CLI/coach).
      - Offer small convenience helpers (e.g. hero vs villain range equity).
    """

    def __init__(self) -> None:
        # Policy: how we choose which backend to use.
        #   auto     -> first compatible backend (pbots -> henry -> pokerkit)
        #   pbots    -> force pbots_calc
        #   henry    -> force Henry backend
        #   pokerkit -> force PokerKit fallback
        self._policy = os.getenv("EQUITY_BACKEND_POLICY", "auto").lower()

        backends: list[EquityBackend] = []

        # Order matters for `auto` fallback.
        # pbots_calc (ranges + hands; MC or exact; multiway)
        try:
            backends.append(PbotsBackend())
        except Exception:
            # pbots_calc may be unavailable; that's fine, we fall back.
            pass

        # HenryRLee C evaluator (placeholder; hands-only; HU exact preferred)
        try:
            backends.append(HenryBackend())
        except Exception:
            # Missing/failed native lib is allowed; we still have other backends.
            pass

        # Pure-Python fallback (hands-only; exact on tiny trees, else MC)
        backends.append(PokerKitBackend())

        self._backends: list[EquityBackend] = backends

    def _choose(self, wants_ranges: bool) -> EquityBackend:
        """
        Pick a backend consistent with the configured policy and input shape.
        """
        # Forced policies first with friendly errors.
        if self._policy == "pbots":
            for b in self._backends:
                if getattr(b, "name", "") == "pbots_calc":
                    return b
            raise RuntimeError("Policy 'pbots' selected but pbots_calc is unavailable")

        if self._policy == "henry":
            for b in self._backends:
                if getattr(b, "name", "") == "henry":
                    return b
            raise RuntimeError(
                "Policy 'henry' selected but Henry backend is unavailable"
            )

        if self._policy == "pokerkit":
            for b in self._backends:
                if getattr(b, "name", "") == "pokerkit":
                    return b
            raise RuntimeError(
                "Policy 'pokerkit' selected but PokerKit backend missing"
            )

        # Auto: walk configured backends in order, skipping those that
        # can't handle the requested input style (e.g. ranges).
        for backend in self._backends:
            if wants_ranges and not backend.supports_ranges():
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
          - seat 1: villain pbots-style range string

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
