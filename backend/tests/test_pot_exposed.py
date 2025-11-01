from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_pot_field_exposed_in_state():
    client.post(
        "/api/session",
        json={
            "seats": 2,
            "sb": 50,
            "bb": 100,
            "ante": 0,
            "stacks": [10000, 10000],
            "base_seed": "POT1",
            "human_seat": 0,
        },
    )
    client.post("/api/hand/start")
    r = client.get("/api/hand/state")
    assert r.status_code == 200
    s = r.json()["state"]
    assert "pot_total" in s
    assert isinstance(s["pot_total"], int)
