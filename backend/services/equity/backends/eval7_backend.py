# backend/services/equity/backends/eval7_backend.py
from __future__ import annotations

import random
import time
from typing import Any, Iterable, List, Optional, Sequence, Tuple

from ..base import Card, EquityResult, PlayerSpec


def _try_import_eval7():
    try:
        import eval7  # type: ignore[import-not-found]

        return eval7
    except Exception:
        return None


_EVAL7 = _try_import_eval7()


class Eval7Backend:
    """
    Lightweight equity backend using the `eval7` library.

    - Pure Python/Cython installable via `pip install eval7`.
    - Supports multiway equities with a Monte Carlo sampler.
    - Accepts either explicit hands or PokerStove-style ranges (via eval7.HandRange).

    Notes:
      * Exact enumeration is not implemented; we will fall back to Monte Carlo even if `exact=True`.
      * Range matching uses eval7.HandRange to parse, then we MC-sample non-overlapping combos.
      * This backend is intended as a portability fallback when native engines (e.g., OMPEval) are unavailable.
    """

    name: str = "eval7"

    # Reasonable cap for safety; eval7 itself can handle more,
    # but we align with our typical multiway targets.
    MAX_PLAYERS: int = 9

    def is_available(self) -> bool:
        return _EVAL7 is not None

    def supports_ranges(self) -> bool:
        return True

    # ---------------------------
    # Public entrypoint
    # ---------------------------
    def calc_equity(
        self,
        players: Sequence[PlayerSpec],
        board: Sequence[Card] = (),
        dead: Sequence[Card] = (),
        iters: Optional[int] = None,
        exact: bool = False,
        timeout_ms: Optional[int] = None,
    ) -> EquityResult:
        if not self.is_available():
            raise RuntimeError("eval7 is not installed")

        if len(players) < 2:
            raise ValueError("need at least two players")

        if len(players) > self.MAX_PLAYERS:
            raise ValueError(
                f"too many players (>{self.MAX_PLAYERS}) for eval7 backend"
            )

        # We ignore `exact=True` and always MC sample in this backend.
        # (Kept for interface parity.)
        iters = int(iters or 20_000)
        if iters <= 0:
            raise ValueError("iters must be a positive integer")

        eval7 = _EVAL7  # type: ignore[assignment]
        assert eval7 is not None

        rng = random.Random()
        start = time.perf_counter()
        deadline = (start + (timeout_ms / 1000.0)) if timeout_ms else None

        # Prepare board/dead sets (strings like "As", "Td")
        board_s = [str(c) for c in board]
        dead_s = [str(c) for c in dead]

        fixed_hands: List[Optional[Tuple[str, str]]] = []
        range_specs: List[Optional[Any]] = []

        all_fixed = True
        used_initial: set[str] = set(board_s) | set(dead_s)

        for p in players:
            if p.hand is not None and p.range is not None:
                raise ValueError("player must specify exactly one of hand or range")
            if p.hand is not None:
                c1, c2 = p.hand
                h = (str(c1), str(c2))
                if len(set(h)) != 2:
                    raise ValueError("duplicate cards in a player's hand")
                fixed_hands.append(h)
                range_specs.append(None)
                used_initial.update(h)
            elif p.range:
                # Parse range (PokerStove-like). "random" -> accept anything.
                fixed_hands.append(None)
                range_specs.append(self._parse_range(eval7, p.range))
                all_fixed = False
            else:
                raise ValueError("player must specify a hand or a range")

        # MC accumulators
        n_players = len(players)
        wins = [0] * n_players
        ties = [0] * n_players
        equity_shares = [0.0] * n_players
        samples = 0

        # Precompute how many board cards we need to draw
        if len(board_s) not in (0, 3, 4, 5):
            raise ValueError("board must be 0, 3, 4, or 5 cards")
        need_board = 5 - len(board_s)

        # Main MC loop
        for _ in range(iters):
            if deadline and time.perf_counter() > deadline:
                break

            # Fresh set of used cards each iteration to fill ranges + board.
            used = set(used_initial)

            # Sample or accept hand for each player
            iter_hands: List[Tuple[str, str]] = []
            ok = True
            for i in range(n_players):
                fh = fixed_hands[i]
                if fh is not None:
                    # Fixed hand: ensure still collision-free with initial sets.
                    if fh[0] in used or fh[1] in used:
                        ok = False
                        break
                    iter_hands.append(fh)
                    used.update(fh)
                else:
                    # Range: pick any valid non-overlapping combo
                    hr = range_specs[i]
                    try:
                        combo = self._pick_combo_from_range(eval7, hr, used, rng)
                    except RuntimeError:
                        ok = False
                        break
                    iter_hands.append(combo)
                    used.update(combo)
            if not ok:
                continue

            # Build full board
            full_board = list(board_s)
            if need_board > 0:
                full_board.extend(self._draw_from_deck(eval7, used, need_board, rng))
                used.update(full_board[-need_board:])

            # Evaluate everyone
            scores: List[int] = []
            # Convert to eval7.Card objects once per player
            board_cards = [eval7.Card(s) for s in full_board]
            for c1s, c2s in iter_hands:
                seven = [eval7.Card(c1s), eval7.Card(c2s), *board_cards]
                scores.append(eval7.evaluate(seven))

            # Decide winners / ties
            max_score = max(scores)
            winners = [i for i, s in enumerate(scores) if s == max_score]
            k = len(winners)
            if k == 1:
                wins[winners[0]] += 1
                equity_shares[winners[0]] += 1.0
            else:
                for i in winners:
                    ties[i] += 1
                    equity_shares[i] += 1.0 / k

            samples += 1

        # Build per-player payload
        per_player = []
        denom = float(samples) if samples > 0 else 1.0
        for i in range(n_players):
            per_player.append(
                {
                    "win": int(wins[i]),
                    "tie": int(ties[i]),
                    "equity": float(equity_shares[i] / denom),
                }
            )

        # Determine mode string
        mode = "hands" if all_fixed else "ranges"

        # Raw metadata (useful upstream)
        raw = {
            "simulations": samples,
            "mode": mode,
            "sim_type": "mc",
            "time_ms": round((time.perf_counter() - start) * 1000.0, 3),
        }

        return EquityResult(
            backend=self.name,
            mode=mode,  # type: ignore[arg-type]
            n_players=n_players,
            board=tuple(board_s),
            dead=tuple(dead_s),
            exact=False,
            iters=iters,
            per_player=per_player,
            raw=raw,
        )

    # ---------------------------
    # Helpers
    # ---------------------------

    def _parse_range(self, eval7_mod: Any, s: str) -> Any:
        s = (s or "").strip()
        if not s:
            raise ValueError("empty range")
        # Accept common synonyms
        if s.lower() in {"xx", "random", "any"}:
            return "RANDOM_ANY"
        try:
            return eval7_mod.HandRange(s)
        except Exception as e:
            raise ValueError(f"bad range string: {s!r}: {e}")

    def _pick_combo_from_range(
        self,
        eval7_mod: Any,
        hr: Any,
        used: set[str],
        rng: random.Random,
        max_tries: int = 200,
    ) -> Tuple[str, str]:
        """
        Sample a non-overlapping 2-card combo from the player's range.
        - If hr == "RANDOM_ANY", we accept any two cards.
        - Otherwise, we filter combos produced by eval7.HandRange against `used`.
        """
        # Fast path: allow any two remaining cards
        if hr == "RANDOM_ANY":
            cards = self._remaining_deck(eval7_mod, used)
            if len(cards) < 2:
                raise RuntimeError("no cards left to sample")
            c1, c2 = rng.sample(cards, 2)
            return (c1, c2)

        # Try random sampling method first for speed.
        for _ in range(max_tries):
            cards = self._remaining_deck(eval7_mod, used)
            if len(cards) < 2:
                break
            c1, c2 = rng.sample(cards, 2)
            if self._pair_in_range(hr, c1, c2):
                return (c1, c2)

        # Fallback: build allowed combo list and sample uniformly
        allowed = self._allowed_combos_from_range(hr, used)
        if not allowed:
            raise RuntimeError("no valid combos in range after blocking")
        return rng.choice(allowed)

    def _pair_in_range(self, hr: Any, c1s: str, c2s: str) -> bool:
        """
        Membership test against eval7.HandRange.hands (list of ((Card, Card), weight)).
        We canonicalize to sorted 2-char strings for comparison.
        """
        try:
            combos = getattr(hr, "hands", None)
            if not combos:
                return False
            a, b = sorted((c1s, c2s))
            for (c1, c2), w in combos:
                if w <= 0:
                    continue
                x, y = sorted((str(c1), str(c2)))
                if x == a and y == b:
                    return True
            return False
        except Exception:
            # If hr doesn't have expected structure, err on the safe side.
            return False

    def _allowed_combos_from_range(
        self, hr: Any, used: set[str]
    ) -> List[Tuple[str, str]]:
        out: List[Tuple[str, str]] = []
        try:
            combos = getattr(hr, "hands", None)
            if not combos:
                return out
            for (c1, c2), w in combos:
                if w <= 0:
                    continue
                s1, s2 = str(c1), str(c2)
                if s1 in used or s2 in used or s1 == s2:
                    continue
                out.append((s1, s2))
        except Exception:
            # If parsing fails, return empty -> caller will handle.
            return []
        return out

    def _remaining_deck(self, eval7_mod: Any, used: set[str]) -> List[str]:
        # Build the remaining deck as 2-char strings ("As", "Td", ...)
        deck = [str(eval7_mod.Card(s)) for s in self._ALL_CARDS(eval7_mod)]
        return [s for s in deck if s not in used]

    def _draw_from_deck(
        self,
        eval7_mod: Any,
        used: set[str],
        n: int,
        rng: random.Random,
    ) -> List[str]:
        cards = self._remaining_deck(eval7_mod, used)
        if len(cards) < n:
            raise RuntimeError("not enough cards to draw remaining board")
        return rng.sample(cards, n)

    def _ALL_CARDS(self, eval7_mod: Any) -> Iterable[str]:
        # Enumerate standard 52-card deck strings
        ranks = "23456789TJQKA"
        suits = "cdhs"
        for r in ranks:
            for s in suits:
                yield f"{r}{s}"
