# backend/tests/test_texassolver_adapter.py
import os
import json
from pathlib import Path
import pytest

from backend.adapters.solver.texassolver_adapter import (
    TexasSolverAdapter,
    SolveRequest,
    CoachDisabledError,
)


def test_env_gating_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COACH_ENABLED", raising=False)
    monkeypatch.delenv("TEXASSOLVER_PATH", raising=False)

    adapter = TexasSolverAdapter()
    req = SolveRequest(
        street="flop",
        board=["Ah", "Kd", "3s"],
        pot=300,
        ip_stack=9900,
        oop_stack=9900,
        ip_range="AA,KK,QQ,JJ,TT,AKs,AQs",
        oop_range="AA,KK,QQ,JJ,TT,AKs,AQo",
        bucket_labels=["33%", "66%", "pot", "jam"],
        spot="SRP",
    )
    with pytest.raises(CoachDisabledError):
        adapter.solve(req)


@pytest.mark.skipif(
    os.getenv("TS_FIXTURE") is None, reason="No local TexasSolver fixture available"
)
def test_parse_golden_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Local-only test:
      1) Run the solver manually to produce a JSON output for an HU SRP node.
      2) Put the resulting JSON in $TS_FIXTURE/srp_output.json
      3) Set COACH_ENABLED=true and TEXASSOLVER_PATH to a valid absolute path.
      4) This test will bypass the external call and only exercise the parser via a monkeypatch.
    """
    fixture_dir = Path(os.environ["TS_FIXTURE"])
    json_path = fixture_dir / "srp_output.json"
    raw = json.loads(json_path.read_text(encoding="utf-8"))

    # Fake env to pass gating
    monkeypatch.setenv("COACH_ENABLED", "true")
    monkeypatch.setenv(
        "TEXASSOLVER_PATH", str(Path("/abs/path/to/console_solver"))
    )  # not executed

    adapter = TexasSolverAdapter()

    # Monkeypatch the solve path to call the private parser directly
    req = SolveRequest(
        street="flop",
        board=["Ah", "Kd", "3s"],
        pot=300,
        ip_stack=9900,
        oop_stack=9900,
        ip_range="AA,KK,QQ,JJ,TT,AKs,AQs",
        oop_range="AA,KK,QQ,JJ,TT,AKs,AQo",
        bucket_labels=["33%", "66%", "pot", "jam"],
        spot="SRP",
    )

    # Access the private method for local dev only
    # mypy: ignore[attr-defined] because we intentionally access a private
    advice = adapter._parse_output(req, raw)  # type: ignore[attr-defined]

    assert "recommended_bucket" in advice
    assert "strategy" in advice and isinstance(advice["strategy"], dict)
    # At least one of our buckets should appear
    assert any(b in advice["strategy"] for b in req.bucket_labels)


@pytest.mark.skipif(
    os.getenv("TS_FIXTURE") is None, reason="No local TexasSolver fixture available"
)
def test_parse_golden_fixture_3bp(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture_dir = Path(os.environ["TS_FIXTURE"])
    json_path = fixture_dir / "3bp_output.json"
    raw = json.loads(json_path.read_text(encoding="utf-8-sig"))

    # Gate pass-through (binary not executed here)
    monkeypatch.setenv("COACH_ENABLED", "true")
    monkeypatch.setenv("TEXASSOLVER_PATH", str(Path("C:/abs/path/console_solver.exe")))

    adapter = TexasSolverAdapter()
    req = SolveRequest(
        street="flop",
        board=["Qs", "Jh", "2h"],
        pot=900,
        ip_stack=2000,
        oop_stack=2000,
        ip_range="AA,KK,QQ,JJ,TT,99,AKs,AQs,AQo:0.5",
        oop_range="QQ,JJ,TT,99,88,AKo:0.25,AQs,AQo",
        bucket_labels=["50%", "100%", "jam"],
        spot="3BP",
    )

    advice = adapter._parse_output(req, raw)  # type: ignore[attr-defined]
    assert isinstance(advice["strategy"], dict)
    assert len(advice["strategy"]) >= 1
