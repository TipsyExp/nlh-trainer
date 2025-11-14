## backend/tests/test_equity_service.py
from __future__ import annotations

import pytest

from backend.services.equity.base import PlayerSpec
from backend.services.equity.service import EquityService


@pytest.mark.parametrize("exact", [False, True])
@pytest.mark.parametrize("backend_policy", ["auto", "pokerkit", "henry", "pbots"])
def test_equity_hu_hands_runs_for_policies(
    backend_policy: str,
    exact: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Sanity check: HU hand-vs-hand equity runs for each backend policy.

    - auto:      picks first compatible backend.
    - pokerkit:  forces PokerKit fallback.
    - henry:     forces Henry placeholder backend.
    - pbots:     forces pbots_calc backend (skipped if pbots_calc unavailable).
    """
    monkeypatch.setenv("EQUITY_BACKEND_POLICY", backend_policy)

    svc = EquityService()

    # If we explicitly request pbots but the backend isn't wired (e.g. pbots_calc
    # not installed), skip rather than failing the suite.
    if backend_policy == "pbots":
        backends = getattr(svc, "_backends", [])
        has_pbots = any(getattr(b, "name", "") == "pbots_calc" for b in backends)
        if not has_pbots:
            pytest.skip("pbots_calc backend not available in this environment")

    res = svc.calc_equity(
        players=[
            PlayerSpec(hand=("Ah", "Ad")),
            PlayerSpec(hand=("Kh", "Qh")),
        ],
        board=["As", "Kd", "2c"],
        exact=exact,
        iters=2_000,
    )

    assert res.n_players == 2
    assert len(res.per_player) == 2
    # Basic sanity: equities are in [0, 1].
    for p in res.per_player:
        assert 0.0 <= p["equity"] <= 1.0


def test_equity_ranges_if_pbots_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    When pbots_calc is available, ranges should be supported and mode == 'ranges'.

    If pbots_calc (and thus the pbots backend) is not available, the test
    skips cleanly instead of failing.
    """
    monkeypatch.setenv("EQUITY_BACKEND_POLICY", "auto")

    svc = EquityService()

    # Detect whether a pbots backend is actually present.
    backends = getattr(svc, "_backends", [])
    has_pbots = any(getattr(b, "name", "") == "pbots_calc" for b in backends)
    if not has_pbots:
        pytest.skip("pbots_calc backend not available in this environment")

    res = svc.calc_equity(
        players=[
            PlayerSpec(range="JJ+"),
            PlayerSpec(range="random"),
        ],
        board=[],
        exact=False,
        iters=5_000,
    )

    assert res.mode == "ranges"
    assert res.n_players == 2
