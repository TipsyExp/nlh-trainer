# backend/services/equity/base.py
from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Protocol,
    Sequence,
    Tuple,
)

Card = str  # e.g. "Ah", "Td", "2c" (uppercase rank + lowercase suit)


@dataclass(frozen=True)
class PlayerSpec:
    """
    Specification for a single player in an equity query.

    Exactly one of `hand` or `range` must be provided:
      - `hand`: a fixed two-card hand like ("Ah", "Ad").
      - `range`: a pbots_calc-style range string, e.g. "JJ+,AKs,AKo" or "random".
    """

    hand: Optional[Tuple[Card, Card]] = None
    range: Optional[str] = None  # pbots_calc syntax ranges or "random"

    def __post_init__(self) -> None:
        # Exactly one of hand/range must be provided
        has_hand = self.hand is not None
        has_range = self.range is not None
        if has_hand == has_range:
            raise ValueError("PlayerSpec: provide exactly one of `hand` or `range`")


@dataclass
class EquityResult:
    """
    Normalized result returned by all equity backends.

    Fields:
      - backend: which backend produced this result ("pbots_calc" | "henry" | "pokerkit").
      - mode:    "hands" if all players have fixed hands, otherwise "ranges".
      - n_players: number of players in the query.
      - board:   tuple of board cards.
      - dead:    tuple of dead/excluded cards.
      - exact:   True if result is from an exact enumerator, False if Monte Carlo.
      - iters:   number of iterations used in MC mode (None for exact).
      - per_player: list of dicts such as:
            {"win": int, "tie": int, "equity": float, ...}
      - raw:     backend-specific extras (optional).
    """

    backend: str  # "pbots_calc" | "henry" | "pokerkit"
    mode: str  # "hands" | "ranges"
    n_players: int
    board: Tuple[Card, ...]
    dead: Tuple[Card, ...]
    exact: bool
    iters: Optional[int]
    per_player: List[Dict[str, Any]]
    raw: Optional[Dict[str, Any]] = None  # backend-specific extras


class EquityBackend(Protocol):
    """
    Protocol that all equity backends must implement.
    """

    name: str

    def supports_ranges(self) -> bool:
        """
        Return True if this backend can handle ranged inputs (pbots-style),
        False if it only supports fixed hands.
        """
        ...

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
        Compute equities for the given players and board/dead cards.

        Implementations may:
          - Use exact enumeration when `exact=True` and the game tree is small enough.
          - Fall back to Monte Carlo otherwise, honoring `iters` and `timeout_ms`
            as best-effort knobs.

        Must return an EquityResult with normalized fields.
        """
        ...
