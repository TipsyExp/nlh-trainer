from fastapi.testclient import TestClient
from backend.main import app


def test_hand_auto_is_disabled_in_prod(monkeypatch):
    # Simulate prod: gate the /api/hand/auto endpoint
    monkeypatch.setenv("HAND_AUTO_ENABLED", "0")

    client = TestClient(app)

    # Minimal HU session
    r = client.post(
        "/api/session",
        json={
            "seats": 2,
            "sb": 50,
            "bb": 100,
            "ante": 0,
            "stacks": [10000, 10000],
            "base_seed": "gate-test",
            "human_seat": 0,
            "bot_mode": "heuristic",
        },
    )
    assert r.status_code == 200

    # Start a hand
    r = client.post("/api/hand/start")
    assert r.status_code == 200

    # Gate should reject /auto
    res = client.post("/api/hand/auto")
    assert res.status_code in (501, 403)
    body = res.json()
    assert body.get("status") == "disabled" or (
        "detail" in body and "disabled" in str(body["detail"]).lower()
    )
