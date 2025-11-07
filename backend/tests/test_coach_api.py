# backend/tests/test_coach_api.py
from __future__ import annotations

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from backend.main import app


def test_advice_disabled(monkeypatch) -> None:
    monkeypatch.setenv("COACH_ENABLED", "false")
    client = TestClient(app)
    r = client.get("/api/coach/advice", params={"hand_id": "H1", "idx": 0})
    assert r.status_code == 501
    body = r.json()
    assert isinstance(body, dict)
    # New contract prefers meta.status="disabled"; keep backward tolerance if shape changes again
    if "meta" in body:
        assert body["meta"].get("status") == "disabled"
    else:
        assert "disabled" in str(body.get("detail", "")).lower()


def test_advice_enabled_stub(monkeypatch) -> None:
    # With COACH_ENABLED=true and current builder,
    # the route returns 501 with meta.status in {"unsupported","timeout","error"} at preflop.
    monkeypatch.setenv("COACH_ENABLED", "true")
    client = TestClient(app)
    r = client.get("/api/coach/advice", params={"hand_id": "H1", "idx": 0})
    assert r.status_code == 501
    body = r.json()
    # Accept the new contract; older "not available" detail is no longer used.
    assert body.get("meta", {}).get("status") in {"unsupported", "timeout", "error"}


# ---------------- Task-18 API integration checks (mocked builder + adapter) ----------------


def _dummy_req():
    from backend.adapters.solver.texassolver_adapter import SolveRequest

    return SolveRequest(
        street="flop",
        board=["Ah", "Kd", "3s"],
        pot=120,
        ip_stack=240,
        oop_stack=240,
        ip_range="AA,AKs",
        oop_range="KK,QQ",
        bucket_labels=["TOP", "MID", "LOW"],
        spot="SRP",
    )


def test_advice_cached_and_node_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COACH_ENABLED", "true")

    # Mock node builder to avoid UnsupportedSpotError
    dummy = _dummy_req()

    def fake_build(hand_id: str, idx: int):  # noqa: ANN001
        return dummy

    monkeypatch.setattr(
        "backend.coach.node_builder.build_solve_request_from_hand",
        fake_build,
        raising=True,
    )

    # Mock adapter.solve and count calls
    calls = {"n": 0}

    def fake_solve(self, req):  # noqa: ANN001
        calls["n"] += 1
        return {"recommended_bucket": "T", "strategy": {"T": 1.0}, "ev_map": {"T": 0.0}}

    monkeypatch.setattr(
        "backend.adapters.solver.texassolver_adapter.TexasSolverAdapter.solve",
        fake_solve,
        raising=True,
    )

    # Ensure the cache is clean for this node
    from backend.coach.node_key import make_node_key_from_solve_request
    from backend.logger import get_logger

    nk = make_node_key_from_solve_request(dummy)
    conn = get_logger().conn
    conn.execute("DELETE FROM solver_cache WHERE node_key = ?", (nk,))
    conn.commit()

    client = TestClient(app)

    r1 = client.get("/api/coach/advice", params={"hand_id": "HX", "idx": 42})
    assert r1.status_code == 200
    b1 = r1.json()
    assert b1["meta"]["cached"] is False
    assert isinstance(b1["meta"]["node_key"], str) and len(b1["meta"]["node_key"]) == 64

    r2 = client.get("/api/coach/advice", params={"hand_id": "HX", "idx": 42})
    assert r2.status_code == 200
    b2 = r2.json()
    assert b2["meta"]["cached"] is True
    assert b2["meta"]["node_key"] == b1["meta"]["node_key"]

    # Adapter should have been called only once due to cache hit
    assert calls["n"] == 1


def test_advice_snapshot_includes_node_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COACH_ENABLED", "true")

    # Mock builder
    dummy = _dummy_req()

    def fake_build(hand_id: str, idx: int):  # noqa: ANN001
        return dummy

    monkeypatch.setattr(
        "backend.coach.node_builder.build_solve_request_from_hand",
        fake_build,
        raising=True,
    )

    # Mock adapter
    def fake_solve(self, req):  # noqa: ANN001
        return {"recommended_bucket": "A", "strategy": {"A": 1.0}, "ev_map": {"A": 0.0}}

    monkeypatch.setattr(
        "backend.adapters.solver.texassolver_adapter.TexasSolverAdapter.solve",
        fake_solve,
        raising=True,
    )

    # Capture snapshot calls
    recorded: Dict[str, Any] = {}

    def fake_write_snapshot(hand_id, idx, node_key, advice_json):  # noqa: ANN001
        recorded["node_key"] = node_key
        recorded["advice_json"] = advice_json

    monkeypatch.setattr(
        "backend.coach.advice_store.write_snapshot",
        fake_write_snapshot,
        raising=True,
    )

    client = TestClient(app)
    r = client.get("/api/coach/advice", params={"hand_id": "HY", "idx": 7})
    assert r.status_code == 200
    body = r.json()

    assert isinstance(recorded.get("node_key"), str)
    assert recorded["node_key"] == body["meta"]["node_key"]


# The following remain as placeholders for future full integration with real solver
@pytest.mark.skip(
    reason="Enable after wiring GET /coach/advice to node_builder + adapter"
)
def test_advice_unsupported(monkeypatch) -> None: ...


@pytest.mark.skip(
    reason="Enable after wiring GET /coach/advice to node_builder + adapter"
)
def test_advice_timeout(monkeypatch) -> None: ...


@pytest.mark.skip(reason="Enable after wiring GET /coach/advice + advice_store")
def test_advice_success_snapshot(monkeypatch) -> None: ...
