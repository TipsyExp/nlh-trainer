from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app


def test_coach_disabled_returns_501(monkeypatch) -> None:
    monkeypatch.setenv("COACH_ENABLED", "false")
    client = TestClient(app)
    r = client.get("/api/coach/advice", params={"hand_id": "H1", "idx": 0})
    assert r.status_code == 501
    assert "disabled" in r.json()["detail"].lower()


def test_coach_enabled_still_501_until_wired(monkeypatch) -> None:
    monkeypatch.setenv("COACH_ENABLED", "true")
    client = TestClient(app)
    r = client.get("/api/coach/advice", params={"hand_id": "H1", "idx": 0})
    assert r.status_code == 501
