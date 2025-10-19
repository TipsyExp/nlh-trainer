"""
Pydantic models representing the training simulator state.

The classes defined in this module encapsulate the mutable state of a
poker hand as well as immutable configuration data such as table
blind sizes and player metadata.  They are intentionally simple for
milestone M0 but provide enough structure to serialise and
deserialise complete hand histories for logging and replay.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SeatType(str, Enum):
    """Enumeration of player seat types."""

    human = "human"
    bot = "bot"


class PlayerStatus(str, Enum):
    """Enumeration of player statuses."""

    active = "active"
    folded = "folded"
    all_in = "all_in"


class Street(str, Enum):
    """Enumeration of game streets."""

    preflop = "preflop"
    flop = "flop"
    turn = "turn"
    river = "river"


class ActionType(str, Enum):
    """Enumeration of action types."""

    check = "check"
    call = "call"
    bet = "bet"
    raise_ = "raise"  # 'raise' is a reserved keyword in Python
    fold = "fold"
    post_blind = "post_blind"

    def __str__(self) -> str:
        return self.value


class TableState(BaseModel):
    """Static table configuration for a session."""

    seat_count: int = Field(..., alias="seats")
    sb: int
    bb: int
    ante: int = 0


class PlayerState(BaseModel):
    """Metadata for an individual player at the table."""

    seat: int
    type: SeatType
    alias: str
    stack: int
    status: PlayerStatus = PlayerStatus.active


class ActionRecord(BaseModel):
    """Record of a single action in the hand history."""

    idx: int
    street: Street
    actor_seat: int
    type: ActionType
    amount: Optional[int] = None
    bucket: Optional[str] = None
    to_call_after: Optional[int] = None
    pot_after: Optional[int] = None
    time_ms: Optional[int] = None
    rng_seed: Optional[str] = None
    snapped: Optional[bool] = None
    meta: Optional[Dict[str, Any]] = None


class GameState(BaseModel):
    """Top‑level state representation for a poker hand."""

    hand_id: str
    deck_seed: Optional[str] = None
    table: TableState
    dealer_seat: int
    sb_seat: int
    bb_seat: int
    street: Street = Street.preflop
    players: List[PlayerState]
    action_history: List[ActionRecord] = Field(default_factory=list)

    class Config:
        use_enum_values = True
        json_encoders = {
            ActionType: lambda v: v.value if isinstance(v, Enum) else v,
            SeatType: lambda v: v.value if isinstance(v, Enum) else v,
            PlayerStatus: lambda v: v.value if isinstance(v, Enum) else v,
            Street: lambda v: v.value if isinstance(v, Enum) else v,
        }


def export_json(state: GameState) -> str:
    """Serialise a GameState into a JSON string.

    This wrapper calls Pydantic’s ``model_dump_json`` method.  It is
    provided for API compatibility with M0 documentation.
    """
    return state.model_dump_json()


def import_json(data: str) -> GameState:
    """Deserialize a JSON string back into a GameState.

    Args:
        data: The JSON string representing a ``GameState``.

    Returns:
        A new ``GameState`` instance reconstructed from the provided
        JSON.
    """
    return GameState.model_validate_json(data)