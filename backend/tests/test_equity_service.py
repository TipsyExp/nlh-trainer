## backend/tests/test_equity_service.py
from __future__ import annotations

import pytest

from backend.services.equity.base import PlayerSpec
from backend.services.equity.service import EquityService


@pytest.mark.parametrize("exact", [False, True])
@pytest.mark.parametrize("backend_policy", ["auto", "pokerkit", "eval7", "ompeval"])
def test_equity_hu_hands_runs_for_policies(
    backend_policy: str,
    exact: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Sanity check: HU hand-vs-hand equity runs for each backend policy.

    - auto:      picks first compatible backend.
    - pokerkit:  forces PokerKit fallback.
    - eval7:     forces Eval7 backend (skip if not available).
    - ompeval:   forces OMPEval backend (skip if not available).
    """
    monkeypatch.setenv("EQUITY_BACKEND_POLICY", backend_policy)

    svc = EquityService()

    # Skip if a forced backend isn't actually available in this environment.
    if backend_policy in {"ompeval", "eval7"}:
        backends = getattr(svc, "_backends", [])
        has_forced = any(getattr(b, "name", "") == backend_policy for b in backends)
        if not has_forced:
            pytest.skip(f"{backend_policy} backend not available in this environment")

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


def test_equity_ranges_if_backend_supports_ranges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    When a ranges-capable backend is available (ompeval or eval7), ranges should be
    supported and mode == 'ranges'. Otherwise the test skips.
    """
    monkeypatch.setenv("EQUITY_BACKEND_POLICY", "auto")

    svc = EquityService()

    # Detect whether any backend supports ranges.
    backends = getattr(svc, "_backends", [])
    has_ranges_backend = any(
        getattr(b, "supports_ranges", None) and b.supports_ranges() for b in backends
    )
    if not has_ranges_backend:
        pytest.skip("No ranges-capable backend available (need ompeval or eval7)")

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
