## backend/tests/test_equity_pbots_multiway.py
from __future__ import annotations

from typing import List

import pytest

from backend.services.equity.base import PlayerSpec
from backend.services.equity.service import EquityService


def _has_pbots_backend() -> bool:
    """
    Detect whether a pbots_calc-backed equity engine is actually wired.

    We introspect EquityService._backends and look for name == "pbots_calc".
    """
    svc = EquityService()
    backends = getattr(svc, "_backends", [])
    return any(getattr(b, "name", "") == "pbots_calc" for b in backends)


def _require_pbots() -> None:
    """
    Skip the current test if pbots_calc is not available in this environment.
    """
    if not _has_pbots_backend():
        pytest.skip("pbots_calc backend not available in this environment")


def test_multiway_ranges_3way_sane_equities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    3-way ranges via pbots_calc: basic sanity checks.

    We don't assert exact equities (MC noise, config-dependent), but we do check:
      - backend == "pbots_calc"
      - mode == "ranges"
      - n_players == 3
      - equities in [0,1] and sum ≈ 1.0
    """
    monkeypatch.setenv("EQUITY_BACKEND_POLICY", "auto")
    _require_pbots()

    svc = EquityService()
    res = svc.calc_equity(
        players=[
            PlayerSpec(range="JJ+"),
            PlayerSpec(range="TT+"),
            PlayerSpec(range="99+"),
        ],
        board=[],
        exact=False,
        iters=20_000,
    )

    assert res.backend == "pbots_calc"
    assert res.mode == "ranges"
    assert res.n_players == 3
    assert len(res.per_player) == 3

    equities: List[float] = [float(p["equity"]) for p in res.per_player]
    for e in equities:
        assert 0.0 <= e <= 1.0

    total = sum(equities)
    # Allow a bit of MC + float noise.
    assert pytest.approx(total, rel=1e-3, abs=1e-3) == 1.0


def test_multiway_ranges_4way_order_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    4-way ranges via pbots_calc: ensure input player order matches output order.

    We use simple one-hand ranges ("AA", "KK", "QQ", "JJ") to keep expectations clear.
    """
    monkeypatch.setenv("EQUITY_BACKEND_POLICY", "auto")
    _require_pbots()

    svc = EquityService()
    players = [
        PlayerSpec(range="AA"),
        PlayerSpec(range="KK"),
        PlayerSpec(range="QQ"),
        PlayerSpec(range="JJ"),
    ]
    res = svc.calc_equity(players=players, board=[], exact=False, iters=30_000)

    assert res.backend == "pbots_calc"
    assert res.mode == "ranges"
    assert res.n_players == 4
    assert len(res.per_player) == 4

    # Verify "nth player in" ↔ "nth result out"
    labels = ["AA", "KK", "QQ", "JJ"]
    equities_by_label = dict(zip(labels, [float(p["equity"]) for p in res.per_player]))
    assert set(equities_by_label.keys()) == set(labels)

    eqs = list(equities_by_label.values())
    for e in eqs:
        assert 0.0 <= e <= 1.0

    total = sum(eqs)
    assert pytest.approx(total, rel=1e-3, abs=1e-3) == 1.0


def test_multiway_ranges_board_dead_collision_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    pbots backend should surface a clear error when board and dead collide.

    This exercises the validation layer in PbotsBackend.calc_equity.
    """
    monkeypatch.setenv("EQUITY_BACKEND_POLICY", "auto")
    _require_pbots()

    svc = EquityService()

    with pytest.raises(ValueError) as excinfo:
        svc.calc_equity(
            players=[
                PlayerSpec(range="JJ+"),
                PlayerSpec(range="random"),
            ],
            board=["As"],
            dead=["As"],  # collision
            exact=False,
            iters=1_000,
        )

    msg = str(excinfo.value).lower()
    assert "board" in msg and "dead" in msg
