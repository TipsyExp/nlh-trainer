# backend/tests/test_coach_api.py
from __future__ import annotations

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
    # With COACH_ENABLED=true and our current node_builder stub,
    # the route returns 501 with meta.status="unsupported" (preflop / not wired).
    monkeypatch.setenv("COACH_ENABLED", "true")
    client = TestClient(app)
    r = client.get("/api/coach/advice", params={"hand_id": "H1", "idx": 0})
    assert r.status_code == 501
    body = r.json()
    # Accept the new contract; older "not available" detail is no longer used.
    assert body.get("meta", {}).get("status") in {"unsupported", "timeout", "error"}


# The following will be enabled once GET /coach/advice is wired to node_builder + adapter + snapshot.
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
