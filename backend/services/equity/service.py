# backend/services/equity/service.py
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

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

    def multiway_equity_for_coach(
        self,
        *,
        hero_seat: int,
        hero_hand: Tuple[Card, Card],
        villain_ranges: Dict[int, str],
        board: Sequence[Card] = (),
        dead: Sequence[Card] = (),
        iters: Optional[int] = None,
        exact: bool = False,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Convenience helper: multiway hero-vs-ranges equity tailored for coach use.

        This helper is designed for postflop multiway coaching. It:

          * Builds a players array from hero + villain ranges.
          * Calls `calc_equity` with a ranges-capable backend.
          * Returns a simplified structure that can be mapped directly onto
            AdviceV1.equity.{hero,players,vs_field}.

        Args:
            hero_seat:
                Logical hero seat index (as per DecisionContext.hero_seat).

            hero_hand:
                Hero's exact two-card hand as (Card, Card).

            villain_ranges:
                Mapping from villain seat index -> range string. Seats should be
                consistent with the DecisionContext.active_seats set; hero_seat
                must **not** be in this mapping.

            board, dead, iters, exact, timeout_ms:
                Passed through to the underlying equity engine.

        Returns:
            dict with keys:
                - "hero_seat": int
                - "hero_equity": float
                - "players_equity": List[{"seat": int, "equity": float}]
                - "vs_field_equity": float

        Raises:
            RuntimeError if no suitable backend is available or if the result
            shape is inconsistent.
        """
        if hero_seat in villain_ranges:
            raise ValueError("hero_seat must not appear in villain_ranges")

        # Stable ordering of seats so we can reconstruct seat↔result mapping.
        seats: List[int] = sorted({int(hero_seat), *[int(s) for s in villain_ranges]})

        players: List[PlayerSpec] = []
        hero_index: Optional[int] = None

        for seat in seats:
            if seat == int(hero_seat):
                players.append(PlayerSpec(hand=hero_hand))
                hero_index = len(players) - 1
            else:
                rng = villain_ranges.get(seat)
                if rng is None:
                    raise ValueError(f"missing range for villain seat {seat}")
                players.append(PlayerSpec(range=rng))

        if hero_index is None:
            raise RuntimeError("internal error: hero_index not set in multiway build")

        try:
            result = self.calc_equity(
                players=players,
                board=board,
                dead=dead,
                iters=iters,
                exact=exact,
                timeout_ms=timeout_ms,
            )
        except Exception as e:  # pragma: no cover - defensive mapping
            # Wrap backend errors in a clearer message so coach logic can map
            # them to status='unsupported' or similar.
            raise RuntimeError(f"multiway ranges equity unavailable: {e}") from e

        per = result.per_player or []
        if len(per) != len(seats):
            raise RuntimeError(
                "equity result length mismatch in multiway_equity_for_coach: "
                f"expected {len(seats)}, got {len(per)}"
            )

        # Extract hero equity from the known hero_index.
        hero_entry = per[hero_index]
        hero_equity = float(hero_entry.get("equity", 0.0))

        players_equity: List[Dict[str, float]] = []
        for seat, rec in zip(seats, per):
            eq = float(rec.get("equity", 0.0))
            players_equity.append({"seat": int(seat), "equity": eq})

        # In standard equity engines, hero equity is already vs "the field".
        vs_field_equity = hero_equity

        return {
            "hero_seat": int(hero_seat),
            "hero_equity": hero_equity,
            "players_equity": players_equity,
            "vs_field_equity": vs_field_equity,
        }

    # ------------------------------------------------------------------ #
    # Capability helper
    # ------------------------------------------------------------------ #

    def capabilities(self) -> dict:
        """
        Return a lightweight snapshot of this service's capabilities.

        This helper selects a backend using the same policy that would be
        applied to a normal equity calculation (excluding range inputs) and
        reports its basic characteristics.  The frontend can call this
        endpoint once to decide how to render UI elements without issuing
        costly trial equity requests.

        Returns:
            dict: A dictionary with keys ``backend``, ``supports_ranges``, and
            ``max_players``.  ``backend`` is the normalized name of the
            selected backend (e.g. ``"ompeval"``, ``"eval7"``, ``"pokerkit"``).
            ``supports_ranges`` is a conservative boolean indicating whether
            range notation is supported.  ``max_players`` reflects the
            maximum number of players the backend can handle efficiently.
        """
        # Choose a backend as we would for a hand-only equity call.  Using
        # ``wants_ranges=False`` ensures that backends incapable of ranges
        # aren't inadvertently skipped when the policy forces them.
        try:
            backend = self._choose(wants_ranges=False)
        except Exception:
            # If no backend is available, report unknown capabilities.
            return {
                "backend": "unknown",
                "supports_ranges": False,
                "max_players": 0,
            }

        # Determine the backend name.  Prefer the declared ``name`` attribute;
        # fall back to the class name without the "Backend" suffix.  Lowercase
        # for consistency.
        backend_name = (
            getattr(backend, "name", None)
            or backend.__class__.__name__.replace("Backend", "").lower()
        )

        # Conservatively advertise range support.  Many backends expose
        # ``supports_ranges()`` but default to False if unimplemented.  If
        # the method raises, assume ranges are unsupported.
        supports_ranges = False
        try:
            supports_ranges = bool(
                backend_name in ("ompeval", "eval7", "pokerkit")
                and getattr(backend, "supports_ranges", lambda: False)()
            )
        except Exception:
            supports_ranges = False

        # Multiway support.  OMPEval supports up to 6 players by default.
        # Other engines are conservatively limited to 2 (heads-up).  These
        # values can be refined later if backends evolve.
        max_players = 2
        if backend_name == "ompeval":
            max_players = 6

        return {
            "backend": backend_name,
            "supports_ranges": supports_ranges,
            "max_players": max_players,
        }
