# backend/tests/test_equity_ompeval_multiway.py
from __future__ import annotations

import pytest

from backend.services.equity.base import PlayerSpec
from backend.services.equity.service import EquityService

# NOTE: These tests are placeholders until the OMPEval backend is wired into EquityService.
# They mirror the old pbots multiway tests but expect the backend name "ompeval".
pytestmark = pytest.mark.skip(
    reason="Enable after wiring OMPEval backend into EquityService and policy."
)


def _ompeval_service(monkeypatch: pytest.MonkeyPatch) -> EquityService:
    """
    Helper to construct an EquityService that targets the OMPEval backend.

    Once OMPEval is registered under EQUITY_BACKEND_POLICY, this sets the policy
    and returns a service instance. If the backend is not available at runtime
    (e.g., native library not built), tests should remain skipped via module-level
    marker above.
    """
    monkeypatch.setenv("EQUITY_BACKEND_POLICY", "ompeval")
    return EquityService()


def test_ompeval_multiway_ranges_three_way(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    3-way ranges: shape + sanity checks.

    Expected once wired:
      - backend == "ompeval"
      - mode == "ranges"
      - equities in [0, 1] and sum ~ 1.0
    """
    svc = _ompeval_service(monkeypatch)

    res = svc.calc_equity(
        players=[
            PlayerSpec(range="JJ+"),
            PlayerSpec(range="TT+"),
            PlayerSpec(range="random"),
        ],
        board=[],
        dead=[],
        exact=False,
        iters=10_000,
    )

    assert res.backend == "ompeval"
    assert res.mode == "ranges"
    assert res.n_players == 3
    assert len(res.per_player) == 3

    equities = [float(p.get("equity", 0.0)) for p in res.per_player]
    for e in equities:
        assert 0.0 <= e <= 1.0

    total = sum(equities)
    assert abs(total - 1.0) <= 1e-3


def test_ompeval_multiway_ranges_four_way(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    4-way ranges: shape + sanity checks.
    """
    svc = _ompeval_service(monkeypatch)

    res = svc.calc_equity(
        players=[
            PlayerSpec(range="JJ+"),
            PlayerSpec(range="TT+"),
            PlayerSpec(range="99+"),
            PlayerSpec(range="random"),
        ],
        board=[],
        dead=[],
        exact=False,
        iters=10_000,
    )

    assert res.backend == "ompeval"
    assert res.mode == "ranges"
    assert res.n_players == 4
    assert len(res.per_player) == 4

    equities = [float(p.get("equity", 0.0)) for p in res.per_player]
    for e in equities:
        assert 0.0 <= e <= 1.0

    total = sum(equities)
    assert abs(total - 1.0) <= 1e-3


def test_ompeval_multiway_hands_duplicate_cards_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Duplicate card detection for fixed-hands multiway inputs.
    """
    svc = _ompeval_service(monkeypatch)

    with pytest.raises(ValueError):
        svc.calc_equity(
            players=[
                PlayerSpec(hand=("Ah", "Ad")),
                PlayerSpec(hand=("Ah", "Kh")),  # overlaps "Ah"
                PlayerSpec(hand=("Qh", "Qd")),
            ],
            board=["2c", "3d", "4h"],
            dead=[],
            exact=False,
            iters=1_000,
        )
