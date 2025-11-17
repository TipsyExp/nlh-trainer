# backend/services/equity/backends/pokerkit_backend.py
from __future__ import annotations

import random
import time
from typing import Dict, List, Optional, Sequence, Tuple

from ..base import Card, EquityResult, PlayerSpec

Rank = int  # 2..14
CardS = str  # "As", "Td", ...


def _rank_val(r: str) -> Rank:
    return "  23456789TJQKA".index(r)


def _all_deck() -> List[CardS]:
    ranks = "23456789TJQKA"
    suits = "cdhs"
    return [f"{r}{s}" for r in ranks for s in suits]


def _cards_by_suit(cards: Sequence[CardS]) -> Dict[str, List[Rank]]:
    by: Dict[str, List[Rank]] = {"c": [], "d": [], "h": [], "s": []}
    for cs in cards:
        by[cs[1]].append(_rank_val(cs[0]))
    for s in by:
        by[s].sort(reverse=True)
    return by


def _straight_high(rs: List[int]) -> int | None:
    uniq = sorted(set(rs), reverse=True)
    if 14 in uniq:
        uniq.append(1)  # wheel
    run = 1
    for i in range(len(uniq) - 1):
        if uniq[i] - 1 == uniq[i + 1]:
            run += 1
            if run >= 5:
                return uniq[i - 3]
        else:
            run = 1
    return None


def _best5_rank_7(cards7: Sequence[CardS]) -> Tuple[int, Tuple[int, ...]]:
    # category: 8 SF, 7 Quads, 6 FH, 5 Flush, 4 Straight, 3 Trips, 2 TwoPair, 1 Pair, 0 High
    ranks = [_rank_val(c[0]) for c in cards7]
    ranks.sort(reverse=True)
    counts: Dict[int, int] = {}
    for r in ranks:
        counts[r] = counts.get(r, 0) + 1
    freq = sorted(counts.items(), key=lambda x: (x[1], x[0]), reverse=True)

    by_suit = _cards_by_suit(cards7)
    flush_suit = next((s for s, lst in by_suit.items() if len(lst) >= 5), None)

    # Straight flush
    if flush_suit:
        sh = _straight_high(by_suit[flush_suit])
        if sh is not None:
            return (8, (sh,))

    # Quads
    if freq[0][1] == 4:
        quad = freq[0][0]
        kicker = max(r for r in ranks if r != quad)
        return (7, (quad, kicker))

    # Full house
    trips = [r for r, c in counts.items() if c == 3]
    pairs = [r for r, c in counts.items() if c == 2]
    if trips:
        t = max(trips)
        rem_trips = [x for x in trips if x != t]
        if rem_trips:
            return (6, (t, max(rem_trips)))
        if pairs:
            return (6, (t, max(pairs)))

    # Flush
    if flush_suit:
        top5 = tuple(sorted(by_suit[flush_suit], reverse=True)[:5])
        return (5, top5)

    # Straight
    sh = _straight_high(ranks)
    if sh is not None:
        return (4, (sh,))

    # Trips
    if trips:
        t = max(trips)
        kickers = [r for r in ranks if r != t][:2]
        return (3, (t, *kickers))

    # Two pair
    if len(pairs) >= 2:
        p1, p2 = sorted(pairs, reverse=True)[:2]
        kicker = max(r for r in ranks if r != p1 and r != p2)
        return (2, (p1, p2, kicker))

    # One pair
    if pairs:
        p = max(pairs)
        kickers = [r for r in ranks if r != p][:3]
        return (1, (p, *kickers))

    # High card
    return (0, tuple(ranks[:5]))


class PokerKitBackend:
    """Hands-only, pure-Python MC fallback used to keep 'pokerkit' policy alive in tests."""

    name: str = "pokerkit"

    def is_available(self) -> bool:
        return True  # no external deps

    def supports_ranges(self) -> bool:
        return False  # hands-only

    def calc_equity(
        self,
        players: Sequence[PlayerSpec],
        board: Sequence[Card] = (),
        dead: Sequence[Card] = (),
        iters: Optional[int] = None,
        exact: bool = False,
        timeout_ms: Optional[int] = None,
    ) -> EquityResult:
        if len(players) < 2:
            raise ValueError("need at least two players")
        if any(p.range is not None for p in players):
            raise RuntimeError("pokerkit backend only supports fixed hands")

        board_s = [str(c) for c in board]
        dead_s = [str(c) for c in dead]
        if len(board_s) not in (0, 3, 4, 5):
            raise ValueError("board must be 0, 3, 4, or 5 cards")

        fixed: List[Tuple[str, str]] = []
        used: set[str] = set(board_s) | set(dead_s)
        for p in players:
            if p.hand is None:
                raise RuntimeError("missing fixed hand")
            c1, c2 = str(p.hand[0]), str(p.hand[1])
            if c1 == c2:
                raise ValueError("duplicate cards in a player's hand")
            if c1 in used or c2 in used:
                raise ValueError("duplicate cards across players/board/dead")
            fixed.append((c1, c2))
            used.update((c1, c2))

        need_board = 5 - len(board_s)
        iters = int(iters or 2000)
        rng = random.Random(0xC0FFEE)
        wins = [0] * len(players)
        ties = [0] * len(players)
        eq_share = [0.0] * len(players)
        samples = 0
        start = time.perf_counter()
        deck_all = _all_deck()

        for _ in range(iters):
            remaining = [c for c in deck_all if c not in used]
            if len(remaining) < need_board:
                break
            drawn = rng.sample(remaining, need_board) if need_board > 0 else []
            full_board = board_s + drawn

            scores = []
            for h in fixed:
                seven = [h[0], h[1], *full_board]
                scores.append(_best5_rank_7(seven))

            best = max(scores)
            winners = [i for i, s in enumerate(scores) if s == best]
            k = len(winners)
            if k == 1:
                wins[winners[0]] += 1
                eq_share[winners[0]] += 1.0
            else:
                for i in winners:
                    ties[i] += 1
                    eq_share[i] += 1.0 / k
            samples += 1

        per_player = []
        denom = float(samples or 1)
        for i in range(len(players)):
            per_player.append(
                {
                    "win": int(wins[i]),
                    "tie": int(ties[i]),
                    "equity": float(eq_share[i] / denom),
                }
            )

        raw = {
            "simulations": samples,
            "sim_type": "mc",
            "time_ms": round((time.perf_counter() - start) * 1000.0, 3),
            "mode": "hands",
        }

        return EquityResult(
            backend=self.name,
            mode="hands",
            n_players=len(players),
            board=tuple(board_s),
            dead=tuple(dead_s),
            exact=False,
            iters=iters,
            per_player=per_player,
            raw=raw,
        )


__all__ = ["PokerKitBackend"]
