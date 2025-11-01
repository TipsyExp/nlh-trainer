from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def _start_hu(seed: str = "QA10"):
    client.post(
        "/api/session",
        json={
            "seats": 2,
            "sb": 50,
            "bb": 100,
            "ante": 0,
            "stacks": [10000, 10000],
            "base_seed": seed,
            "human_seat": 0,
        },
    )
    client.post("/api/hand/start")


def test_visibility_opponent_cards_masked():
    _start_hu("MASK10")
    r = client.get("/api/hand/state")
    assert r.status_code == 200
    s = r.json()["state"]
    # hero seat=0, villain seat=1 should be masked
    hero = s["players"][0]["hole_cards"]
    vill = s["players"][1]["hole_cards"]
    assert hero != ["XX", "XX"]
    assert vill == ["XX", "XX"]


def test_hu_monstrous_request_snaps_to_jam_preflop():
    _start_hu("JAM10")
    r = client.get("/api/hand/state")
    actor = r.json()["actor"]
    # Request something absurdly large -> should snap to 'jam'
    r2 = client.post(
        "/api/hand/action",
        json={"seat": actor["seat"], "action": "raise", "amount": 10_000_000},
    )
    assert r2.status_code == 200
    la = r2.json()["state"]["last_action"]
    assert la["snapped"] is True
    assert la["bucket_label"] == "jam"
