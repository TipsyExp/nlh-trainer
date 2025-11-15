# backend/api/routes/equity.py
from __future__ import annotations

import re
from typing import List, Literal, Optional, Tuple, cast

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...logger import log_equity_snapshot
from ...services.equity.base import Card, PlayerSpec
from ...services.equity.service import EquityService

router = APIRouter(tags=["equity"])
_service = EquityService()

_CARD_RE = re.compile(r"^[2-9TJQKA][cdhs]$")


class PlayerIn(BaseModel):
    """
    Single player input for an equity query.

    Exactly one of `hand` or `range` must be provided:
      - hand:  ["Ah", "Ad"]
      - range: "JJ+,AKs,AKo" or "random"
    """

    hand: Optional[Tuple[Card, Card]] = None
    range: Optional[str] = None


class EquityRequest(BaseModel):
    """
    Request body for /api/equity.

    - players: list of PlayerIn (2+ entries).
    - board:   optional list of board cards like ["As","Kd","2c"].
    - dead:    optional list of dead cards like ["7h","7d"].
    - iters:   optional iteration count for Monte Carlo backends.
    - exact:   request exact enumeration where supported.
    - timeout_ms: optional soft timeout hint for backends that support it.
    """

    players: List[PlayerIn]
    board: List[Card] = Field(default_factory=list)
    dead: List[Card] = Field(default_factory=list)
    iters: Optional[int] = None
    exact: bool = False
    timeout_ms: Optional[int] = None


class PlayerOut(BaseModel):
    """
    Per-player equity result.

    - win:    number of winning outcomes.
    - tie:    number of tying outcomes.
    - equity: estimated equity in [0.0, 1.0].
    """

    win: int
    tie: int
    equity: float


class EquityResponse(BaseModel):
    """
    Normalized equity response.

    Mirrors the EquityResult structure from the service layer.
    """

    ok: bool
    backend: str
    mode: Literal["hands", "ranges"]
    n_players: int
    board: List[Card]
    dead: List[Card]
    exact: bool
    iters: Optional[int]
    players: List[PlayerOut]
    raw: Optional[dict] = None


def _validate_card_list(name: str, cards: List[Card]) -> None:
    if len(cards) > 5 and name == "board":
        raise HTTPException(
            status_code=400, detail="board cannot have more than 5 cards"
        )
    if len(cards) != len(set(cards)):
        raise HTTPException(status_code=400, detail=f"duplicate cards in `{name}`")
    for c in cards:
        if not isinstance(c, str) or not _CARD_RE.match(c):
            raise HTTPException(
                status_code=400, detail=f"invalid card in `{name}`: {c!r}"
            )


def _validate_players(players: List[PlayerIn]) -> None:
    if len(players) < 2:
        raise HTTPException(status_code=400, detail="at least two players are required")
    for idx, p in enumerate(players):
        has_hand = p.hand is not None
        has_range = p.range is not None and p.range.strip() != ""
        if has_hand == has_range:
            raise HTTPException(
                status_code=400,
                detail=f"player {idx}: provide exactly one of `hand` or `range`",
            )
        if has_hand:
            hand = p.hand
            assert hand is not None and len(hand) == 2
            for c in hand:
                if not _CARD_RE.match(c):
                    raise HTTPException(
                        status_code=400,
                        detail=f"player {idx}: bad card {c!r} in `hand`",
                    )


def _validate_no_collisions_if_fixed_hands(
    players: List[PlayerIn],
    board: List[Card],
    dead: List[Card],
) -> None:
    """When everyone supplies fixed hands, ensure no duplicates across all inputs."""
    if all(p.hand is not None for p in players):
        seen: set[str] = set()

        def _add(c: str, where: str) -> None:
            if c in seen:
                raise HTTPException(
                    status_code=400, detail=f"duplicate card {c!r} across {where}"
                )
            seen.add(c)

        for i, p in enumerate(players):
            assert p.hand is not None
            for c in p.hand:
                _add(c, f"players/board/dead (player {i} hand)")
        for c in board:
            _add(c, "players/board/dead (board)")
        for c in dead:
            _add(c, "players/board/dead (dead)")


@router.post("/equity", response_model=EquityResponse)
def calc_equity(
    req: EquityRequest,
    hand_id: Optional[str] = None,
    idx: Optional[int] = None,
) -> EquityResponse:
    """
    POST /api/equity

    Compute equities for either explicit hands or pbots-style ranges.

    Optional query parameters:
      - hand_id: engine hand identifier (e.g. "H1"), used only for logging.
      - idx:     decision index within the hand, used only for logging.

    When both are provided and logging is enabled, a normalized snapshot
    of the request/response is attached to the corresponding decision row
    in the log database.
    """
    # Validate inputs defensively.
    _validate_players(req.players)
    _validate_card_list("board", req.board)
    _validate_card_list("dead", req.dead)
    if set(req.board) & set(req.dead):
        raise HTTPException(
            status_code=400, detail="a card cannot be both on `board` and in `dead`"
        )
    _validate_no_collisions_if_fixed_hands(req.players, req.board, req.dead)

    player_specs = [PlayerSpec(hand=p.hand, range=p.range) for p in req.players]

    try:
        result = _service.calc_equity(
            players=player_specs,
            board=req.board,
            dead=req.dead,
            iters=req.iters,
            exact=req.exact,
            timeout_ms=req.timeout_ms,
        )
    except Exception as e:
        # Normalize backend errors to a 400 with a readable message.
        raise HTTPException(status_code=400, detail=str(e))

    # Cast for mypy to satisfy Literal type
    mode_literal: Literal["hands", "ranges"] = cast(
        Literal["hands", "ranges"], result.mode
    )

    players_out = [PlayerOut(**p) for p in result.per_player]

    response = EquityResponse(
        ok=True,
        backend=result.backend,
        mode=mode_literal,  # "hands" or "ranges"
        n_players=result.n_players,
        board=list(result.board),
        dead=list(result.dead),
        exact=result.exact,
        iters=result.iters,
        players=players_out,
        raw=result.raw,
    )

    # Best-effort snapshot logging when the equity call is tied to a hand/decision.
    if hand_id is not None and idx is not None:
        try:
            snapshot = {
                "backend": result.backend,
                "mode": result.mode,
                "policy": getattr(_service, "_policy", "auto"),
                "n_players": result.n_players,
                "board": list(result.board),
                "dead": list(result.dead),
                "exact": result.exact,
                "iters": result.iters,
                "per_player": result.per_player,
                "raw": result.raw,
                "inputs": {
                    "players": [p.dict() for p in req.players],
                    "board": list(req.board),
                    "dead": list(req.dead),
                },
            }
            log_equity_snapshot(hand_id=str(hand_id), idx=int(idx), snapshot=snapshot)
        except Exception:
            # Never let logging failures affect the API response.
            pass

    return response
