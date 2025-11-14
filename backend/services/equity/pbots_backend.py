# backend/services/equity/pbots_backend.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from .base import Card, PlayerSpec, EquityResult  # type: ignore[unused-import]


def _import_pbots() -> Any:
    """
    Import pbots_calc lazily so environments without it can still run other
    backends. Raises a RuntimeError with a clear message if unavailable.
    """
    try:
        import pbots_calc  # type: ignore[import-not-found]

        return pbots_calc
    except Exception as e:  # pragma: no cover - depends on host environment
        raise RuntimeError(
            "pbots_calc is not available. Install with `pip install pbots_calc` "
            "or disable this backend (EQUITY_BACKEND_POLICY / service wiring)."
        ) from e


class PbotsBackend:
    """
    pbots_calc-backed equity engine.

    - Supports both fixed hands and pbots-style ranges (including multiway).
    - Can run in exact mode (enumeration) or Monte Carlo mode.
    - Expects cards in 'AhAd', 'AsKd2c', etc. pbots_calc formats.
    """

    name = "pbots_calc"

    def __init__(self) -> None:
        self._pb = _import_pbots()

    def supports_ranges(self) -> bool:
        # Full range support is the main reason to use this backend.
        return True

    @staticmethod
    def _hand_to_str(hand: Tuple[Card, Card]) -> str:
        """
        Convert a 2-card hand tuple to the pbots string format.

        Example:
            ("Ah", "Ad") -> "AhAd"
        """
        return f"{hand[0]}{hand[1]}"

    def _players_to_desc(self, players: Sequence[PlayerSpec]) -> str:
        """
        Build the pbots_calc player description string.

        Examples:
          - Two fixed hands:  "AhAd:KhQh"
          - Two ranges:       "JJ+:random"
          - Mixed:            "AhAd:JJ+"
        """
        parts: List[str] = []
        for p in players:
            if p.hand is not None:
                parts.append(self._hand_to_str(p.hand))
            elif p.range is not None:
                parts.append(p.range)
            else:
                raise ValueError("Each PlayerSpec must have either `hand` or `range`")
        return ":".join(parts)

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
        Compute equities via pbots_calc.

        - Supports 2+ players, hands and/or ranges.
        - `exact=True` -> pbots exact mode (iterations set to 0).
        - `exact=False` -> Monte Carlo with `iters` samples (default ~20k).
        """
        if len(players) < 2:
            raise ValueError("Need at least 2 players for equity calculation")
        if len(board) > 5:
            raise ValueError("Board cannot have more than 5 cards")
        if len(board) != len(set(board)):
            raise ValueError("Duplicate cards in `board`")
        if len(dead) != len(set(dead)):
            raise ValueError("Duplicate cards in `dead`")
        if set(board) & set(dead):
            raise ValueError("A card cannot be on `board` and in `dead`")

        # When all players have fixed hands, ensure no collisions across inputs.
        if all(p.hand is not None for p in players):
            known: List[Card] = []
            for p in players:
                assert p.hand is not None
                known.extend(list(p.hand))
            known.extend(list(board))
            known.extend(list(dead))
            if len(known) != len(set(known)):
                raise ValueError("Duplicate cards detected across hands/board/dead")

        # pbots_calc uses an `exact` flag; exact mode uses 0 iterations.
        if exact:
            iters = 0
        if iters is None:
            iters = 20_000

        hands_desc = self._players_to_desc(players)
        board_str = "".join(board)  # e.g. ["As","Kd","2c"] -> "AsKd2c"
        dead_str = "".join(dead)  # e.g. ["7h","7d"]      -> "7h7d"

        # pbots_calc.calc(hands, board, dead, iters, exact)
        res = self._pb.calc(hands_desc, board_str, dead_str, iters, exact)

        # res.hands is a sequence of objects with .ev, .wins, .ties
        per_player: List[Dict[str, Any]] = []
        for h in res.hands:
            per_player.append(
                {
                    "win": int(getattr(h, "wins", 0)),
                    "tie": int(getattr(h, "ties", 0)),
                    "equity": float(getattr(h, "ev", 0.0)),
                }
            )

        # If every player has a fixed hand, label as "hands", otherwise "ranges".
        mode = "hands" if all(p.hand is not None for p in players) else "ranges"

        return EquityResult(
            backend=self.name,
            mode=mode,
            n_players=len(players),
            board=tuple(board),
            dead=tuple(dead),
            exact=bool(exact),
            iters=None if exact else iters,
            per_player=per_player,
            raw={
                # Some pbots builds expose .iters or similar; capture if present.
                "simulations": getattr(res, "iters", None),
            },
        )
