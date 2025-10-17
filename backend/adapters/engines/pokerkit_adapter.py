from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any, List

# Enforce PokerKit presence (Option A only)
import pokerkit as pk  # noqa: F401


@dataclass
class _TableCfg:
    seats: int
    stacks: List[int]
    sb: int
    bb: int
    ante: int
    seed: Optional[int]


class PokerKitAdapter:
    """
    Thin adapter around PokerKit exposing a stable stepper API:

      start_table(seats, stacks, sb, bb, ante=0, seed=None) -> None
      start_hand(seed=None) -> None
      next_actor() -> (seat_index, legal_flags_dict)
      apply_action(seat, action, amount=None) -> None
      state() -> JSON-serialisable dict

    Keep all poker rules inside PokerKit; this class just translates.
    """

    def __init__(self) -> None:
        self._table: Optional[_TableCfg] = None
        self._hand_no: int = 0
        self._pk_table = None
        self._pk_hand = None

    def start_table(
        self,
        *,
        seats: int,
        stacks: List[int],
        sb: int,
        bb: int,
        ante: int = 0,
        seed: Optional[int] = None,
    ) -> None:
        if seats < 2:
            raise ValueError("Need at least 2 seats")
        if len(stacks) != seats:
            raise ValueError("stacks length must equal seats")
        self._table = _TableCfg(seats, stacks, sb, bb, ante, seed)
        self._hand_no = 0
        # TODO: build PokerKit table/game objects here

    def start_hand(self, seed: Optional[int] = None) -> None:
        if not self._table:
            raise RuntimeError("start_table first")
        self._hand_no += 1
        hand_seed = seed if seed is not None else self._table.seed
        # TODO: rotate dealer, post blinds/antes, deal via PokerKit; keep hand_seed deterministic

    def next_actor(self) -> Tuple[int, Dict[str, Any]]:
        if not self._pk_hand:
            raise RuntimeError("start_hand first")
        # TODO: query current actor + legal options from PokerKit
        seat_index = 0
        legal = {
            "to_call": 0,
            "min_raise_to": 0,
            "can_check": True,
            "can_call": False,
            "can_bet": True,
            "can_raise": False,
            "can_fold": True,
        }
        return seat_index, legal

    def apply_action(self, seat: int, action: str, amount: Optional[int] = None) -> None:
        if not self._pk_hand:
            raise RuntimeError("start_hand first")
        # TODO: map {"fold","check","call","bet","raise","all_in"} to PokerKit calls
        # amount is a *target total* for bet/raise; allow short all-ins that don't reopen.
        raise NotImplementedError

    def state(self) -> Dict[str, Any]:
        if not self._table or not self._pk_hand:
            raise RuntimeError("No active hand")
        # TODO: build snapshot from PokerKit
        return {
            "hand_id": self._hand_no,
            "rng_seed": self._table.seed,
            "table": {"seats": self._table.seats, "sb": self._table.sb, "bb": self._table.bb, "ante": self._table.ante},
            "positions": {"button": None, "sb": None, "bb": None},
            "street": "preflop",
            "board": {"flop": [], "turn": None, "river": None},
            "pots": {"main": 0, "side": []},
            "players": [],
            "next_to_act": None,
            "legal_actions": {},
            "history": [],
        }


# Optional convenience singleton
_engine_singleton: Optional[PokerKitAdapter] = None
def get_engine() -> PokerKitAdapter:
    global _engine_singleton
    if _engine_singleton is None:
        _engine_singleton = PokerKitAdapter()
    return _engine_singleton
