"""
Pydantic models representing the canonical state schema.

These classes mirror the JSON structure described in ``docs/STATE-SCHEMA.md``.  They
are used to validate and serialize game state and action history.  By
providing a strict schema we ensure that engines and frontends agree
on the shape of the data exchanged.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field


class Street(str, Enum):
    preflop = "preflop"
    flop = "flop"
    turn = "turn"
    river = "river"
    showdown = "showdown"
    complete = "complete"


class ActionType(str, Enum):
    post_blind = "post_blind"
    fold = "fold"
    check = "check"
    call = "call"
    bet = "bet"
    raise_ = "raise"
    all_in = "all_in"
    deal = "deal"


class SeatType(str, Enum):
    human = "human"
    bot = "bot"
    empty = "empty"


class PlayerStatus(str, Enum):
    active = "active"
    folded = "folded"
    all_in = "all_in"


class Position(str, Enum):
    BTN = "BTN"
    SB = "SB"
    BB = "BB"
    UTG = "UTG"
    UTG1 = "UTG1"
    MP = "MP"
    HJ = "HJ"
    CO = "CO"


class PotSide(BaseModel):
    """Side pot representation."""

    size: int
    contestants: List[int]


class Pots(BaseModel):
    """Pot breakdown for a hand."""

    main: int
    sides: List[PotSide] = Field(default_factory=list)


class LegalActions(BaseModel):
    can_fold: bool = False
    can_check: bool = False
    to_call: int = 0
    min_raise_to: int = 0
    allowed_buckets: List[str] = Field(default_factory=list)


class PlayerState(BaseModel):
    seat: int
    type: SeatType
    alias: str
    stack: int
    stack_bb: Optional[float] = None
    committed_street: int = 0
    committed_total: int = 0
    status: PlayerStatus
    position: Optional[Position] = None
    hole_cards: Optional[List[str]] = None


class ActionRecord(BaseModel):
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


class TableState(BaseModel):
    seat_count: int
    sb: int
    bb: int
    ante: int = 0
    rake: Dict[str, Any] = Field(default_factory=lambda: {"enabled": False, "type": "none"})


class GameState(BaseModel):
    """Top level state for a single hand."""

    hand_id: str
    deck_seed: str
    table: TableState
    dealer_seat: int
    sb_seat: int
    bb_seat: int
    street: Street
    community: Dict[str, List[str]] = Field(default_factory=lambda: {"preflop": [], "flop": [], "turn": [], "river": []})
    pots: Pots = Field(default_factory=lambda: Pots(main=0, sides=[]))
    players: List[PlayerState] = Field(default_factory=list)
    to_act: Optional[int] = None
    legal_actions: LegalActions = Field(default_factory=LegalActions)
    spr: Optional[float] = None
    effective_stacks: List[Dict[str, Any]] = Field(default_factory=list)
    action_history: List[ActionRecord] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True


def export_json(state: GameState) -> str:
    """Serialize a GameState to JSON string with stable field order.

    Args:
        state: The GameState instance.

    Returns:
        A JSON string representation.
    """
    return state.model_dump_json(indent=2, by_alias=True)


def import_json(data: str) -> GameState:
    """Deserialize a JSON string into a GameState.

    Args:
        data: The JSON string.

    Returns:
        A GameState instance.
    """
    return GameState.model_validate_json(data)