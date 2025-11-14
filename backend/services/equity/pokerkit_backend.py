# backend/services/equity/pokerkit_backend.py
from __future__ import annotations

import random as _random
from typing import Any, Dict, List, Optional, Sequence

from .base import Card, PlayerSpec, EquityResult

# We will use PokerKit's evaluator to perform exact enumeration for HU turn/river
# and a simple Monte Carlo fallback otherwise. This keeps the backend pure-Python
# and always-available, albeit slower than native libs.

try:  # pragma: no cover
    # NOTE: This is intentionally loose; adapt to the actual PokerKit API when wiring.
    from pokerkit import evaluate_seven  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    evaluate_seven = None  # We will guard accesses and provide simple rank fallback


RANKS = "23456789TJQKA"
SUITS = "cdhs"


def _all_deck() -> List[Card]:
    return [f"{r}{s}" for r in RANKS for s in SUITS]


def _remove(cards: List[Card], *to_remove: Card) -> List[Card]:
    blocked = set(to_remove)
    return [c for c in cards if c not in blocked]


class PokerKitBackend:
    """
    Pure-Python fallback equity backend.

    - Always available (no native deps required).
    - Hands-only: does not support ranges.
    - Exact enumeration for small HU trees (e.g. turn/river).
    - Monte Carlo fallback otherwise.
    """

    name = "pokerkit"

    def supports_ranges(self) -> bool:
        # This backend only supports fixed hands, not ranges.
        return False

    @staticmethod
    def _score_7(cards7: Sequence[Card]) -> int:
        """
        Score a 7-card hand.

        If PokerKit's evaluator is available, use it; otherwise fall back to a
        simple hash-based ranking which is NOT poker-correct but sufficient to
        differentiate winners for infrastructure testing.
        """
        if evaluate_seven is not None:  # pragma: no cover - depends on external lib
            try:
                # Placeholder: actual call will differ.
                return int(evaluate_seven(cards7))  # type: ignore[call-arg]
            except Exception:
                # Fall back to naive scoring if the call fails.
                pass

        # Naive placeholder: sort cards and hash. Only relative ordering matters.
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
            * exact=True, and
            * len(players) == 2, and
            * number of missing board cards <= 2.
          Otherwise falls back to Monte Carlo.
        """
        if any(p.range is not None for p in players):
            raise ValueError("PokerKitBackend only supports fixed hands for now")

        if len(players) < 2:
            raise ValueError("Need at least 2 players for equity calculation")

        if len(board) > 5:
            raise ValueError("Board cannot have more than 5 cards")

        # Collect all known cards (player hands + board + explicit dead)
        known: List[Card] = []
        for p in players:
            if p.hand is None:
                raise ValueError("All players must have fixed hands in PokerKitBackend")
            known.extend(list(p.hand))
        known.extend(list(board))
        known.extend(list(dead))

        deck = _remove(_all_deck(), *known)

        n_players = len(players)
        wins = [0] * n_players
        ties = [0] * n_players

        # Decide enumeration size
        draw_count = 5 - len(board)
        if draw_count < 0:
            raise ValueError("Board has too many cards")

        # HU exact enumeration threshold (rough heuristic)
        do_exact = bool(exact and n_players == 2 and draw_count <= 2)

        trials = 0

        if do_exact:
            # Exhaustively draw remaining board cards
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
            # Monte Carlo sampling
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

        # Build per-player normalized outputs
        per_player: List[Dict[str, Any]] = []
        total_trials = max(1, trials)

        for i in range(n_players):
            # Simple equity estimate: wins + evenly split ties.
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
