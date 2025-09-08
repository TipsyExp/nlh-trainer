"""
PokerKit engine adapter (stub).

This module defines a minimal stub for the PokerKit adapter expected by
the NLH training simulator.  In milestone M0 we do not implement a
full game engine; instead these functions are placeholders which
conform to the required interface.  Future milestones will replace
these stubs with real logic backed by the PokerKit library.

Functions:
    start_table(seats, blinds, stacks, seed):
        Create a new table with a given number of seats, blind
        structure, initial stacks and random seed.

    start_hand():
        Begin a new hand at the current table.  Hands are tracked
        internally by the adapter.

    next_actor() -> tuple[int, dict, int, int]:
        Determine which seat is to act next and return the legal
        actions along with to‑call and min‑raise information.

    apply_action(seat, action, amount):
        Apply an action on behalf of a seat.  The action should be
        validated by the caller.

    state() -> dict:
        Return the current game state as a dict conforming to the
        ``docs/STATE-SCHEMA.md`` specification.  In this stub
        implementation a minimal placeholder state is returned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TableConfig:
    """Configuration parameters for a PokerKit table."""

    seat_count: int
    sb: int
    bb: int
    ante: int
    stacks: List[int]
    seed: Optional[str] = None


@dataclass
class PokerKitAdapter:
    """Minimal stub adapter for the PokerKit engine."""

    table_config: Optional[TableConfig] = None
    hand_counter: int = 0

    def start_table(self, seats: int, blinds: Dict[str, int], stacks: List[int], seed: Optional[str] = None) -> None:
        """Configure a new table.

        Args:
            seats: Number of seats (2/3/6/9/10).
            blinds: Dict with keys ``sb``, ``bb`` and ``ante`` specifying blind amounts.
            stacks: List of starting stack sizes for each seat.
            seed: Optional RNG seed for deterministic dealing.
        """
        self.table_config = TableConfig(
            seat_count=seats,
            sb=blinds.get("sb", 0),
            bb=blinds.get("bb", 0),
            ante=blinds.get("ante", 0),
            stacks=stacks,
            seed=seed,
        )
        self.hand_counter = 0

    def start_hand(self) -> None:
        """Start a new hand.

        For the stub implementation this simply increments an internal counter.
        """
        if self.table_config is None:
            raise RuntimeError("Table has not been started. Call start_table() first.")
        self.hand_counter += 1

    def next_actor(self) -> Tuple[int, Dict[str, Any], int, int]:
        """Return the next seat to act and associated legal action information.

        Returns:
            A tuple of (seat_index, legal_actions, to_call, min_raise).

        Note:
            This stub always returns seat 0 with an empty set of legal actions.
            Real implementations will compute legal actions based on game state.
        """
        # In a real adapter this would inspect the engine state; here we return
        # a fixed placeholder.
        seat = 0
        legal_actions: Dict[str, bool] = {"can_fold": False, "can_check": False, "can_call": False, "can_raise": False}
        to_call = 0
        min_raise = 0
        return seat, legal_actions, to_call, min_raise

    def apply_action(self, seat: int, action: str, amount: Optional[int] = None) -> None:
        """Apply an action to the current hand.

        Args:
            seat: The seat index performing the action.
            action: The action type (e.g. ``fold``, ``call``, ``raise``).
            amount: Optional chip amount for bet/raise actions.
        """
        # The stub does not track actions; this method is a no‑op.
        return None

    def state(self) -> Dict[str, Any]:
        """Return a minimal placeholder game state.

        In a real implementation this would transform PokerKit's internal state
        into the canonical schema defined in ``docs/STATE-SCHEMA.md``.  For now
        we return a skeleton with only a hand id and empty fields.

        Returns:
            A dict representing the current hand state.
        """
        if self.table_config is None:
            raise RuntimeError("Table has not been started. Call start_table() first.")
        return {
            "hand_id": f"hand-{self.hand_counter}",
            "deck_seed": self.table_config.seed or "",  # may be empty if not set
            "table": {
                "seat_count": self.table_config.seat_count,
                "sb": self.table_config.sb,
                "bb": self.table_config.bb,
                "ante": self.table_config.ante,
                "rake": {"enabled": False, "type": "none"},
            },
            "dealer_seat": 0,
            "sb_seat": 1 if self.table_config.seat_count > 1 else 0,
            "bb_seat": 2 if self.table_config.seat_count > 2 else 0,
            "street": "preflop",
            "community": {"preflop": [], "flop": [], "turn": [], "river": []},
            "pots": {"main": 0, "sides": []},
            "players": [],
            "to_act": None,
            "legal_actions": {},
            "spr": 0.0,
            "effective_stacks": [],
            "action_history": [],
        }


# A module level instance can be used by the API to manage a single table.
_DEFAULT_ADAPTER: PokerKitAdapter | None = None


def get_adapter() -> PokerKitAdapter:
    """Return a singleton instance of the PokerKitAdapter.

    This helper ensures that there is a consistent adapter instance used
    across the API for a single user session.
    """
    global _DEFAULT_ADAPTER
    if _DEFAULT_ADAPTER is None:
        _DEFAULT_ADAPTER = PokerKitAdapter()
    return _DEFAULT_ADAPTER


def start_table(seats: int, blinds: Dict[str, int], stacks: List[int], seed: Optional[str] = None) -> None:
    """Thin wrapper around the adapter's start_table method."""
    get_adapter().start_table(seats, blinds, stacks, seed)


def start_hand() -> None:
    """Thin wrapper around the adapter's start_hand method."""
    get_adapter().start_hand()


def next_actor() -> Tuple[int, Dict[str, Any], int, int]:
    """Thin wrapper around the adapter's next_actor method."""
    return get_adapter().next_actor()


def apply_action(seat: int, action: str, amount: Optional[int] = None) -> None:
    """Thin wrapper around the adapter's apply_action method."""
    get_adapter().apply_action(seat, action, amount)


def state() -> Dict[str, Any]:
    """Thin wrapper around the adapter's state method."""
    return get_adapter().state()