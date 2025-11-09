# backend/tests/test_hand_state_board_and_verbs.py
from __future__ import annotations

from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from backend.main import app


def _post(client: TestClient, path: str, json: Dict[str, Any] | None = None):
    r = client.post(path, json=json)
    assert r.status_code == 200, f"POST {path} failed: {r.status_code} {r.text}"
    return r.json()


def _get(client: TestClient, path: str):
    r = client.get(path)
    assert r.status_code == 200, f"GET {path} failed: {r.status_code} {r.text}"
    return r.json()


def _create_session(
    client: TestClient,
    *,
    human_seat: int,
    base_seed: str = "TEST-BOARD",
    bot_mode: str = "heuristic",
    seats: int = 2,
    sb: int = 50,
    bb: int = 100,
    ante: int = 0,
    stacks: List[int] | None = None,
):
    if stacks is None:
        stacks = [10000, 10000]
    return _post(
        client,
        "/api/session",
        {
            "seats": seats,
            "sb": sb,
            "bb": bb,
            "ante": ante,
            "stacks": stacks,
            "base_seed": base_seed,
            "human_seat": human_seat,
            "bot_mode": bot_mode,
        },
    )


@pytest.fixture()
def client():
    # Fresh TestClient per test keeps API state isolated enough for these flows.
    return TestClient(app)


def test_state_flop_board_and_holecard_policy(client: TestClient):
    """
    Flow (human is BB):
      - /api/session (human_seat=1)
      - /api/hand/start (auto-advances SB bot to first human decision)
      - human BB 'check' (after SB calls) -> flop is dealt
      - verify board flop has 3 cards; hero revealed, villain masked.
    """
    _create_session(client, human_seat=1, base_seed="TEST-FLOP-A")
    _post(client, "/api/hand/start")

    # It's now human's turn (BB). Check preflop to see the flop.
    st0 = _get(client, "/api/hand/state")
    actor = st0.get("actor") or {}
    assert actor.get("seat") == 1, f"Expected BB (1) to act; got {actor}"

    _post(
        client,
        "/api/hand/action",
        {
            "seat": 1,
            "action": "check",
        },
    )

    # On flop: board should show 3 cards; hero seat revealed, villain masked.
    st1 = _get(client, "/api/hand/state")
    s = st1["state"]
    assert s["street"] == "flop", f"Expected flop; got {s['street']}"
    board = s["board"]
    assert isinstance(board, dict)
    assert len(board.get("flop", [])) == 3, f"Missing flop cards: {board}"
    assert len(board.get("turn", [])) == 0
    assert len(board.get("river", [])) == 0

    # Hole-card reveal policy: human_seat=1 revealed, seat 0 masked
    players = s["players"]
    p0, p1 = players[0], players[1]
    assert p0["hole_cards"] == ["XX", "XX"], f"Villain should be masked: {p0}"
    assert p1["hole_cards"] != ["XX", "XX"], f"Hero should be revealed: {p1}"


def test_facing_raise_uses_R_buckets(client: TestClient):
    """
    Flow (human is SB):
      - /api/session (human_seat=0)
      - /api/hand/start
      - human SB raises sized (2.2x -> 220)
      - verify BB actor has only 'R' sizes (e.g., '2.5xR','3.0xR') in allowed_buckets
        (plus fold/call/jam)
    """
    _create_session(client, human_seat=0, base_seed="TEST-R-BUCKETS")
    _post(client, "/api/hand/start")

    st0 = _get(client, "/api/hand/state")
    actor = st0.get("actor") or {}
    assert actor.get("seat") == 0, f"Expected SB (0) to act first; got {actor}"
    # Raise to 220 (2.2x) — engine will accept and show R-sizes to the BB.
    _post(
        client,
        "/api/hand/action",
        {
            "seat": 0,
            "action": "raise",  # allowed to send 'raise'; engine normalizes only when to_call==0
            "amount": 220,
        },
    )

    st1 = _get(client, "/api/hand/state")
    bb_actor = st1.get("actor") or {}
    assert bb_actor.get("seat") == 1, f"Expected BB (1) to act; got {bb_actor}"
    allowed = bb_actor.get("allowed_buckets") or []
    # Facing a raise: must include 'fold','call','jam' and 'R' sizes; must NOT include open sizes.
    assert "fold" in allowed and "call" in allowed and "jam" in allowed, allowed
    assert any(lbl.endswith("xR") for lbl in allowed), f"No R-sizes found in {allowed}"
    assert not any(lbl in {"2.2x", "2.5x", "3.0x"} for lbl in allowed), allowed


def test_normalizes_bet_vs_raise_when_to_call_zero(client: TestClient):
    """
    On a street where to_call==0, sending action='raise' with an amount should be
    recorded in last_action as type='bet'.
    """
    _create_session(client, human_seat=1, base_seed="TEST-BET-NORM")
    _post(client, "/api/hand/start")

    # Preflop: SB bot will act (likely call); human BB checks to go to flop.
    st0 = _get(client, "/api/hand/state")
    assert (st0.get("actor") or {}).get("seat") == 1
    _post(client, "/api/hand/action", {"seat": 1, "action": "check"})

    # On flop, human (BB) acts first with to_call==0. Send 'raise' verb and ensure engine records 'bet'.
    st1 = _get(client, "/api/hand/state")
    actor = st1.get("actor") or {}
    assert actor.get("seat") == 1, "Human should act first on flop (HU OOP)."
    assert actor.get("to_call") == 0, f"Expected to_call==0 on flop; got {actor}"

    resp = _post(
        client,
        "/api/hand/action",
        {
            "seat": 1,
            "action": "raise",  # deliberately send 'raise' when to_call==0
            "amount": 200,
        },
    )
    # For bet/raise, the API returns pre-bot snapshot; last_action should be present.
    last_action = (resp.get("state") or {}).get("last_action") or {}
    assert (
        last_action.get("type") == "bet"
    ), f"Expected normalization to 'bet'; got {last_action}"
    assert last_action.get("requested") == 200
