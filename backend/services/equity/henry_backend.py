# backend/services/equity/henry_backend.py
from __future__ import annotations

import os
import ctypes
import random as _random
from typing import Any, Dict, List, Optional, Sequence

from .base import Card, PlayerSpec, EquityResult


RANKS = "23456789TJQKA"
SUITS = "cdhs"


def _all_deck() -> List[Card]:
    return [f"{r}{s}" for r in RANKS for s in SUITS]


def _remove(cards: List[Card], *to_remove: Card) -> List[Card]:
    blocked = set(to_remove)
    return [c for c in cards if c not in blocked]


class HenryBackend:
    """
    Placeholder backend for the HenryRLee C evaluator.

    - Intended to wrap a native C library via ctypes.
    - Hands-only: does not support ranges.
    - Prefers exact enumeration for small HU trees.
    - Falls back to Monte Carlo otherwise.
    - If the native lib is not loaded, uses a naive Python scoring function so the
      infrastructure can still be exercised.
    """

    name = "henry"

    def __init__(self, lib_path: Optional[str] = None) -> None:
        """
        Attempt to load the HenryRLee evaluator.

        The path can be provided explicitly or via the HREVAL_LIB_PATH env var.
        If loading fails, we keep running with a Python-only fallback.
        """
        self._lib: Optional[ctypes.CDLL] = None

        lib_path = lib_path or os.getenv("HREVAL_LIB_PATH")
        if lib_path:
            try:
                self._lib = ctypes.CDLL(lib_path)
            except OSError as e:  # pragma: no cover - depends on host environment
                raise RuntimeError(
                    f"Failed to load HenryRLee evaluator at {lib_path}: {e}"
                ) from e

    def supports_ranges(self) -> bool:
        # This backend only supports fixed hands, not ranges.
        return False

    def _score_7(self, cards7: Sequence[Card]) -> int:
        """
        Score a 7-card hand via the native library (when wired) or a fallback.

        TODO: Replace the fallback with actual marshalling into the HenryRLee
        evaluator, and call the appropriate C function here.
        """
        if self._lib is not None:  # pragma: no cover - requires native lib
            # Placeholder for future C call.
            pass

        # Fallback: naive hash. NOT poker-correct; only relative ordering matters.
        return hash(tuple(sorted(cards7)))

    def calc_equity(
        self,
        players: Sequence[PlayerSpec],
        board: Sequence[Card] = (),
        dead: Sequence[Card] = (),
        iters: Optional[int] = None,
        exact: bool = False,
        timeout_ms: Optional[int] = None,  # noqa: ARG002 - reserved for future use
    ) -> EquityResult:
        """
        Compute equities for fixed-hand players on the given board.

        - Raises if any player uses a range.
        - Requires at least two players.
        - Uses exact enumeration when:
            * exact=True, or
            * len(players) == 2 and number of missing board cards <= 2.
          Otherwise falls back to Monte Carlo.
        """
        if any(p.range is not None for p in players):
            raise ValueError("HenryBackend only supports fixed hands for now")

        if len(players) < 2:
            raise ValueError("Need at least 2 players for equity calculation")

        if len(board) > 5:
            raise ValueError("Board cannot have more than 5 cards")

        # Collect all known cards (player hands + board + explicit dead)
        known: List[Card] = []
        for p in players:
            if p.hand is None:
                raise ValueError("All players must have fixed hands in HenryBackend")
            known.extend(list(p.hand))
        known.extend(list(board))
        known.extend(list(dead))

        deck = _remove(_all_deck(), *known)

        n_players = len(players)
        wins = [0] * n_players
        ties = [0] * n_players

        draw_count = 5 - len(board)
        if draw_count < 0:
            raise ValueError("Board has too many cards")

        # Henry backend is meant for *exact* HU/small draws; prefer exact when feasible.
        do_exact = bool(exact or (n_players == 2 and draw_count <= 2))

        trials = 0

        if do_exact:
            from itertools import combinations

            for rest in combinations(deck, draw_count):
                final_board = list(board) + list(rest)
                scores: List[int] = []
                for p in players:
                    assert p.hand is not None
                    cards7 = list(p.hand) + final_board
                    scores.append(self._score_7(cards7))

                best = max(scores)
                winners = [i for i, s in enumerate(scores) if s == best]

                if len(winners) == 1:
                    wins[winners[0]] += 1
                else:
                    for w in winners:
                        ties[w] += 1

                trials += 1
        else:
            # Monte Carlo fallback
            if iters is None:
                iters = 20_000

            for _ in range(iters):
                sample_cards = _random.sample(deck, draw_count)
                final_board = list(board) + sample_cards

                scores = []
                for p in players:
                    assert p.hand is not None
                    cards7 = list(p.hand) + final_board
                    scores.append(self._score_7(cards7))

                best = max(scores)
                winners = [i for i, s in enumerate(scores) if s == best]

                if len(winners) == 1:
                    wins[winners[0]] += 1
                else:
                    for w in winners:
                        ties[w] += 1

                trials += 1

        per_player: List[Dict[str, Any]] = []
        total_trials = max(1, trials)

        for i in range(n_players):
            n_tie_players = len([j for j in range(n_players) if ties[j] > 0]) or 1
            ev = (wins[i] + ties[i] / n_tie_players) / total_trials
            per_player.append(
                {
                    "win": wins[i],
                    "tie": ties[i],
                    "equity": float(ev),
                }
            )

        return EquityResult(
            backend=self.name,
            mode="hands",
            n_players=n_players,
            board=tuple(board),
            dead=tuple(dead),
            exact=do_exact,
            iters=None if do_exact else iters,
            per_player=per_player,
            raw={"trials": trials},
        )
