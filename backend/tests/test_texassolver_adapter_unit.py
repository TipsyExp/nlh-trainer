import os
from pathlib import Path
import pytest

from backend.adapters.solver.texassolver_adapter import (
    TexasSolverAdapter,
    SolveRequest,
    CoachDisabledError,
    UnsupportedSpotError,
    _require_solver_enabled,
)


def _srp_req() -> SolveRequest:
    return SolveRequest(
        street="flop",
        board=["Qs", "Jh", "2h"],
        pot=300,
        ip_stack=9900,
        oop_stack=9900,
        ip_range="AA,KK,QQ,JJ,TT,AKs,AQs",
        oop_range="AA,KK,QQ,JJ,TT,AKs,AQo",
        bucket_labels=["33%", "66%", "jam"],
        spot="SRP",
    )


def test_env_gate_disabled():
    # COACH off should raise before anything else
    monkey_env = dict(os.environ)
    try:
        os.environ["COACH_ENABLED"] = "false"
        with pytest.raises(CoachDisabledError):
            _require_solver_enabled()
    finally:
        os.environ.clear()
        os.environ.update(monkey_env)


def test_env_gate_missing_path():
    monkey_env = dict(os.environ)
    try:
        os.environ["COACH_ENABLED"] = "true"
        if "TEXASSOLVER_PATH" in os.environ:
            del os.environ["TEXASSOLVER_PATH"]
        with pytest.raises(CoachDisabledError):
            _require_solver_enabled()
    finally:
        os.environ.clear()
        os.environ.update(monkey_env)


def test_unsupported_preflop_shortcircuits(tmp_path: Path):
    # Bypass env gate by stubbing a fake solver path that exists
    adapter = TexasSolverAdapter()
    # Use a real existing file so .exists() is true
    adapter._solver_path = Path(__file__)  # type: ignore[attr-defined]

    bad = SolveRequest(
        street="preflop",
        board=[],
        pot=100,
        ip_stack=10000,
        oop_stack=10000,
        ip_range="",
        oop_range="",
        bucket_labels=["33%", "66%", "jam"],
        spot="SRP",
    )
    with pytest.raises(UnsupportedSpotError):
        adapter.solve(bad)


def test_bucket_mapping_smoke():
    # Fake a tiny root payload that looks like a dict strategy
    raw = {
        "root": {
            "strategy": {
                "check": 0.1,
                "bet_60": 0.6,
                "allin": 0.3,
            }
        }
    }
    adapter = TexasSolverAdapter()
    advice = adapter._parse_output(_srp_req(), raw)  # type: ignore[attr-defined]
    # 60% should map to nearest bucket "66%"; allin -> "jam"
    assert advice["strategy"]["66%"] == pytest.approx(0.6, rel=1e-6)
    assert advice["strategy"]["jam"] == pytest.approx(0.3, rel=1e-6)
    assert advice["strategy"]["check"] == pytest.approx(0.1, rel=1e-6)
