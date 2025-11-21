# backend/tests/test_decision_context.py
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from backend.coach.decision_context import (
    DecisionContext,
    _extract_hero_hole_cards_from_players,
    _infer_active_seats_from_players,
    _normalize_board_any,
    build_decision_context,
    build_decision_context_from_state,
)


def test_normalize_board_any_from_dict() -> None:
    board_obj: Dict[str, List[str]] = {
        "flop": ["Ah", "Kd", "3s"],
        "turn": ["7c"],
        "river": ["2d"],
    }
    cards = _normalize_board_any(board_obj)
    assert cards == ["Ah", "Kd", "3s", "7c", "2d"]


def test_normalize_board_any_from_list() -> None:
    board_obj = ["Ah", "Kd", "3s", "7c"]
    cards = _normalize_board_any(board_obj)
    assert cards == ["Ah", "Kd", "3s", "7c"]


def test_infer_active_seats_from_players_status() -> None:
    players: List[Dict[str, Any]] = [
        {"status": "active"},
        {"status": "folded"},
        {"status": "SITOUT"},
        {"status": None},
    ]
    # Uses list index as seat; marks fold/out/sitout as inactive.
    active = _infer_active_seats_from_players(players)
    assert active == [0, 3]


def test_extract_hero_hole_cards_from_players() -> None:
    players: List[Dict[str, Any]] = [
        {"hole_cards": ["As", "Kh"]},
        {"hole_cards": ["Qc", "Qd"]},
    ]
    hero_cards = _extract_hero_hole_cards_from_players(players, hero_seat=0)
    villain_cards = _extract_hero_hole_cards_from_players(players, hero_seat=1)
    out_of_range = _extract_hero_hole_cards_from_players(players, hero_seat=2)

    assert hero_cards == ["As", "Kh"]
    assert villain_cards == ["Qc", "Qd"]
    assert out_of_range is None


def test_build_decision_context_from_state_basic_flop() -> None:
    state: Dict[str, Any] = {
        "street": "flop",
        "board": {
            "flop": ["Ah", "Kd", "3s"],
            "turn": [],
            "river": [],
        },
        "pot_total": 100,
        "allowed": {
            "to_call": 50,
            "min_raise": 200,
            "allowed_buckets": ["fold", "call", "2.5xR"],
        },
        "deck_seed": "seed123",
        "table": {"button": 0, "sb_seat": 0, "bb_seat": 1},
        "players": [
            {"hole_cards": ["As", "Kh"]},
            {"hole_cards": ["Qc", "Qd"]},
        ],
        "to_act": 0,
        "last_action": {"seat": 1, "type": "bet", "committed": 50},
    }

    ctx = build_decision_context_from_state(
        state=state,
        hand_id="H1",
        idx=3,
        hero_seat=0,
    )

    assert isinstance(ctx, DecisionContext)
    assert ctx.hand_id == "H1"
    assert ctx.idx == 3
    assert ctx.street == "flop"

    # Board + pot / price
    assert ctx.board == ["Ah", "Kd", "3s"]
    assert ctx.pot_total == 100
    assert ctx.to_call == 50
    assert ctx.min_raise == 200
    assert ctx.allowed_buckets == ["fold", "call", "2.5xR"]

    # Seats / hero cards
    assert ctx.hero_seat == 0
    assert ctx.hero_hole_cards == ["As", "Kh"]
    assert ctx.n_players == 2
    assert ctx.active_seats == [0, 1]

    # Table anchors
    assert ctx.button == 0
    assert ctx.sb_seat == 0
    assert ctx.bb_seat == 1

    # Deck + terminal / last_action
    assert ctx.deck_seed == "seed123"
    assert ctx.terminal is False
    assert ctx.last_action is not None
    assert ctx.last_action["seat"] == 1
    assert ctx.last_action["type"] == "bet"

    # Raw state is the input dict for from_state builder.
    assert ctx.raw_state is state


def test_build_decision_context_from_state_terminal_when_to_act_missing() -> None:
    state: Dict[str, Any] = {
        "street": "river",
        "board": ["Ah", "Kd", "3s", "7c", "2d"],
        "pot_total": 250,
        # no "to_act" key at all
        "allowed": {"to_call": 0, "allowed_buckets": []},
        "players": [{"hole_cards": ["As", "Kh"]}],
        "table": {"button": 0, "sb_seat": 0, "bb_seat": 0},
    }

    ctx = build_decision_context_from_state(
        state=state,
        hand_id="H2",
        idx=5,
        hero_seat=0,
    )

    assert ctx.terminal is True
    assert ctx.to_call == 0
    assert ctx.allowed_buckets == []


def test_build_decision_context_from_state_terminal_when_to_act_none() -> None:
    state: Dict[str, Any] = {
        "street": "river",
        "board": ["Ah", "Kd", "3s", "7c", "2d"],
        "pot_total": 250,
        "to_act": None,
        "allowed": {"to_call": 0, "allowed_buckets": []},
        "players": [{"hole_cards": ["As", "Kh"]}],
        "table": {"button": 0, "sb_seat": 0, "bb_seat": 0},
    }

    ctx = build_decision_context_from_state(
        state=state,
        hand_id="H3",
        idx=6,
        hero_seat=0,
    )

    assert ctx.terminal is True
    assert ctx.to_call == 0
    assert ctx.allowed_buckets == []


def test_build_decision_context_from_state_active_seats_respects_status() -> None:
    state: Dict[str, Any] = {
        "street": "turn",
        "board": ["Ah", "Kd", "3s", "7c"],
        "pot_total": 150,
        "allowed": {"to_call": 10, "min_raise": 40, "allowed_buckets": ["call"]},
        "players": [
            {"hole_cards": ["As", "Kh"], "status": "active"},
            {"hole_cards": ["Qh", "Qs"], "status": "folded"},
            {"hole_cards": ["9c", "9d"], "status": "SITOUT"},
            {"hole_cards": ["Tc", "Td"], "status": "in"},
        ],
        "table": {"button": 0, "sb_seat": 0, "bb_seat": 1},
        "to_act": 0,
    }

    ctx = build_decision_context_from_state(
        state=state,
        hand_id="H4",
        idx=4,
        hero_seat=0,
    )

    # Seats with non-fold/out/sitout statuses should be active.
    assert ctx.active_seats == [0, 3]
    assert ctx.n_players == 2


# ---------------------------------------------------------------------------
# Engine-backed builder tests (build_decision_context)
# ---------------------------------------------------------------------------


class _StubState:
    def __init__(self) -> None:
        self.street = "turn"
        self.board = {
            "flop": ["Ah", "Kd", "3s"],
            "turn": ["7c"],
            "river": [],
        }
        self.pot_total = 123
        self.deck_seed = "engine-seed"
        self.players = [
            SimpleNamespace(status="in", hole_cards=["As", "Kh"]),
            SimpleNamespace(status="folded", hole_cards=["Qh", "Qs"]),
            SimpleNamespace(status="in", hole_cards=["9c", "9d"]),
        ]
        self.table = SimpleNamespace(button=1, sb_seat=0, bb_seat=2)
        self.last_action = SimpleNamespace(seat=2, type="bet", committed=50)


class _StubAdapter:
    def __init__(self) -> None:
        self.hand_id = 42
        self._state = _StubState()
        self._actor: Dict[str, Any] = {
            "seat": 0,
            "to_call": 10,
            "min_raise": 40,
            "allowed_buckets": ["fold", "call", "2.5xR"],
        }

    def state(self) -> _StubState:
        return self._state

    def next_actor(self) -> Dict[str, Any]:
        return dict(self._actor)


class _StubSessionState:
    def __init__(self, hero_seat: int) -> None:
        self.human_seat = hero_seat


def test_build_decision_context_from_engine_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _StubAdapter()
    session_state = _StubSessionState(hero_seat=0)

    monkeypatch.setattr(
        "backend.coach.decision_context.get_adapter",
        lambda: adapter,
        raising=True,
    )
    monkeypatch.setattr(
        "backend.coach.decision_context.get_session_state",
        lambda: session_state,
        raising=True,
    )

    ctx = build_decision_context(hand_id="H42", idx=7)

    assert ctx.hand_id == "H42"
    assert ctx.idx == 7
    assert ctx.street == "turn"

    # Seats / hero
    assert ctx.hero_seat == 0
    assert ctx.hero_hole_cards == ["As", "Kh"]
    assert ctx.active_seats == [0, 2]
    assert ctx.n_players == 2

    # Board + pot / price
    assert ctx.board == ["Ah", "Kd", "3s", "7c"]
    assert ctx.pot_total == 123
    assert ctx.to_call == 10
    assert ctx.min_raise == 40
    assert ctx.allowed_buckets == ["fold", "call", "2.5xR"]

    # Table anchors
    assert ctx.button == 1
    assert ctx.sb_seat == 0
    assert ctx.bb_seat == 2

    # Terminal flag from next_actor presence
    assert ctx.terminal is False

    # Last action normalized
    assert ctx.last_action is not None
    assert ctx.last_action["seat"] == 2
    assert ctx.last_action["type"] == "bet"


def test_build_decision_context_raises_when_no_active_hand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _AdapterNoHand:
        hand_id = None

        def state(self) -> Any:  # pragma: no cover - should not be called
            raise RuntimeError("should not be called")

        def next_actor(self) -> Any:  # pragma: no cover - should not be called
            raise RuntimeError("should not be called")

    monkeypatch.setattr(
        "backend.coach.decision_context.get_adapter",
        lambda: _AdapterNoHand(),
        raising=True,
    )
    monkeypatch.setattr(
        "backend.coach.decision_context.get_session_state",
        lambda: _StubSessionState(0),
        raising=True,
    )

    with pytest.raises(RuntimeError):
        build_decision_context(hand_id="H999", idx=0)


def test_build_decision_context_raises_on_hand_id_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _StubAdapter()
    session_state = _StubSessionState(hero_seat=0)

    monkeypatch.setattr(
        "backend.coach.decision_context.get_adapter",
        lambda: adapter,
        raising=True,
    )
    monkeypatch.setattr(
        "backend.coach.decision_context.get_session_state",
        lambda: session_state,
        raising=True,
    )

    # Engine hand id is "H42"; requesting a different one should error.
    with pytest.raises(ValueError):
        build_decision_context(hand_id="H7", idx=0)
