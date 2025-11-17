## backend/tests/test_equity_api_multiway.py
from __future__ import annotations

from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def _require_ompeval() -> None:
    """
    Skip the calling test if the OMPEval native module is not available.

    Keeps the default CI job (no native build) green, while exercising
    multiway/range behaviour in environments where OMPEval is built.
    """
    try:
        import ompeval  # type: ignore[import-not-found]  # noqa: F401
    except Exception:
        pytest.skip(
            "ompeval extension not installed; skipping multiway /api/equity tests."
        )


def test_equity_api_multiway_ranges_three_way() -> None:
    """
    3-way ranges via /api/equity using the OMPEval backend.

    We assert:
      - HTTP 200
      - backend == "ompeval"
      - mode == "ranges"
      - n_players == 3
      - per-player equities in [0, 1]
      - sum of equities ~ 1.0 (within a small tolerance)
    """
    _require_ompeval()

    payload: Dict[str, Any] = {
        "players": [
            {"range": "JJ+"},
            {"range": "TT+"},
            {"range": "random"},
        ],
        "board": [],
        "dead": [],
        "iters": 10_000,
        "exact": False,
    }

    r = client.post("/api/equity", json=payload)
    assert r.status_code == 200

    body = r.json()
    assert body.get("ok") is True
    assert body.get("backend") == "ompeval"
    assert body.get("mode") == "ranges"
    assert body.get("n_players") == 3

    players: List[Dict[str, Any]] = body.get("players") or []
    assert len(players) == 3

    equities = [float(p.get("equity", 0.0)) for p in players]
    for e in equities:
        assert 0.0 <= e <= 1.0

    total = sum(equities)
    assert abs(total - 1.0) <= 1e-3


def test_equity_api_multiway_ranges_four_way() -> None:
    """
    4-way ranges via /api/equity using the OMPEval backend.

    Same checks as the 3-way case, but with four players.
    """
    _require_ompeval()

    payload: Dict[str, Any] = {
        "players": [
            {"range": "JJ+"},
            {"range": "TT+"},
            {"range": "99+"},
            {"range": "random"},
        ],
        "board": [],
        "dead": [],
        "iters": 10_000,
        "exact": False,
    }

    r = client.post("/api/equity", json=payload)
    assert r.status_code == 200

    body = r.json()
    assert body.get("ok") is True
    assert body.get("backend") == "ompeval"
    assert body.get("mode") == "ranges"
    assert body.get("n_players") == 4

    players: List[Dict[str, Any]] = body.get("players") or []
    assert len(players) == 4

    equities = [float(p.get("equity", 0.0)) for p in players]
    for e in equities:
        assert 0.0 <= e <= 1.0

    total = sum(equities)
    assert abs(total - 1.0) <= 1e-3


def test_equity_api_board_dead_collision_400() -> None:
    """
    /api/equity should reject inputs where a card appears on both board and dead.

    This exercises the HTTP-level validation and error mapping for collisions.
    """
    payload = {
        "players": [
            {"hand": ["Ah", "Ad"]},
            {"hand": ["Kh", "Qh"]},
        ],
        # "As" appears in both board and dead
        "board": ["As", "Kd", "2c"],
        "dead": ["As"],
        "exact": False,
    }

    r = client.post("/api/equity", json=payload)
    assert r.status_code == 400

    body = r.json()
    detail = str(body.get("detail", "")).lower()
    assert "board" in detail and "dead" in detail
    assert "card" in detail or "cards" in detail


def test_equity_api_player_must_choose_hand_or_range() -> None:
    """
    Each player must provide exactly one of `hand` or `range`.

    Supplying both should yield HTTP 400 with a clear message.
    """
    payload = {
        "players": [
            {
                "hand": ["Ah", "Ad"],
                "range": "JJ+",
            },
            {
                "hand": ["Kh", "Qh"],
            },
        ],
        "board": [],
        "dead": [],
        "exact": False,
    }

    r = client.post("/api/equity", json=payload)
    assert r.status_code == 400

    body = r.json()
    detail = str(body.get("detail", "")).lower()
    assert "exactly one" in detail
    assert "hand" in detail and "range" in detail
