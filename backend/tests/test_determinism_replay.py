from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def _start_session_and_hand(seed: str):
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


def test_replay_is_deterministic_with_same_seed():
    # Run #1
    _start_session_and_hand("REPLAY-SEED")
    r = client.get("/api/hand/state")
    s1 = r.json()["state"]
    hero1 = s1["players"][0]["hole_cards"]  # human_seat = 0
    seed1 = s1["deck_seed"]

    # Human raises 240 -> snaps to 250
    actor = r.json()["actor"]
    rraise = client.post("/api/hand/action", json={"seat": actor["seat"], "action": "raise", "amount": 240})
    la1 = rraise.json()["state"]["last_action"]
    assert la1["snapped"] is True
    assert la1["bucket_label"] in ("2.5x", "2.5xR")
    assert int(la1["committed"]) == 250

    # Run #2 (fresh session, same base_seed)
    _start_session_and_hand("REPLAY-SEED")
    r2 = client.get("/api/hand/state")
    s2 = r2.json()["state"]
    hero2 = s2["players"][0]["hole_cards"]
    seed2 = s2["deck_seed"]

    # Same seed -> same hero cards and deck_seed
    assert seed1 == seed2
    assert hero1 == hero2

    # Same action -> same snap behavior
    actor2 = r2.json()["actor"]
    rraise2 = client.post("/api/hand/action", json={"seat": actor2["seat"], "action": "raise", "amount": 240})
    la2 = rraise2.json()["state"]["last_action"]
    assert la2["snapped"] is True
    assert la2["bucket_label"] in ("2.5x", "2.5xR")
    assert int(la2["committed"]) == 250
