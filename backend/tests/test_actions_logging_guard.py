from __future__ import annotations
import sqlite3
from fastapi.testclient import TestClient


def test_completed_hand_writes_actions(tmp_path, monkeypatch):
    # Isolate db for this test
    db = tmp_path / "ci.sqlite"
    monkeypatch.setenv("LOG_DB_PATH", str(db))
    monkeypatch.setenv("COACH_ENABLED", "false")

    # Import app AFTER env vars so startup hooks bind to our DB
    from backend.main import app

    client = TestClient(app)

    # Start a simple session
    r = client.post(
        "/api/session",
        json={
            "seats": 2,
            "sb": 50,
            "bb": 100,
            "ante": 0,
            "stacks": [10000, 10000],
            "base_seed": "T15-logging-guard",
            "human_seat": 0,
        },
    )
    assert r.status_code == 200

    # Start a hand and take a deterministic first action
    r = client.post("/api/hand/start")
    assert r.status_code == 200
    st = client.get("/api/hand/state").json()
    actor = st.get("actor")
    if actor:
        to_call = int(actor.get("to_call") or 0)
        action = "check" if to_call == 0 else "call"
        r = client.post(
            "/api/hand/action",
            json={
                "seat": int(actor["seat"]),
                "action": action,
                "amount": None,
            },
        )
        assert r.status_code == 200

    # Assert at least one action logged
    con = sqlite3.connect(str(db))
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='actions'"
        )
        assert cur.fetchone(), "actions table missing"
        cur.execute("SELECT COUNT(*) FROM actions")
        n = cur.fetchone()[0]
        assert n >= 1, "no action rows recorded"
    finally:
        con.close()
