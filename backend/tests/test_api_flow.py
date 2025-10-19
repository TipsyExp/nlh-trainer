from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app
from backend.adapters.engines import get_adapter


client = TestClient(app)


def test_api_end_to_end_hu_stepper():
    # 1) Create/reset session (HU: seats=2, human is seat 0)
    resp = client.post(
        "/api/session",
        json={
            "seats": 2,
            "sb": 50,
            "bb": 100,
            "ante": 0,
            "stacks": [10000, 10000],
            "base_seed": "T07",
            "human_seat": 0,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True

    # 2) Start a hand
    resp = client.post("/api/hand/start")
    assert resp.status_code == 200, resp.text
    hand_id = resp.json()["hand_id"]
    assert hand_id.startswith("H")

    # 3) Get state: SB should act first preflop (HU)
    resp = client.get("/api/hand/state")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    s = body["state"]
    actor = body["actor"]
    assert s["table"]["seats"] == 2
    assert actor["seat"] == s["table"]["sb_seat"]
    assert isinstance(actor.get("allowed_buckets"), list)

    # 4) Take a raise that snaps to 2.5x (request 240 -> 250)
    resp = client.post(
        "/api/hand/action",
        json={"seat": actor["seat"], "action": "raise", "amount": 240},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    s = body["state"]
    la = s["last_action"]
    assert la is not None
    assert la["snapped"] is True
    assert la["bucket_label"] == "2.5x"

    # 5) New state and actor visible
    resp = client.get("/api/hand/state")
    assert resp.status_code == 200
    body = resp.json()
    assert "state" in body
    assert "actor" in body


def test_api_hu_call_then_bot_check_advances_to_flop():
    # Reset adapter and session fresh
    client.post(
        "/api/session",
        json={
            "seats": 2,
            "sb": 50,
            "bb": 100,
            "ante": 0,
            "stacks": [10000, 10000],
            "base_seed": "T07-B",
            "human_seat": 0,
        },
    )

    client.post("/api/hand/start")

    resp = client.get("/api/hand/state")
    actor = resp.json()["actor"]
    # SB calls -> BB bot should auto "check" -> flop
    resp = client.post(
        "/api/hand/action", json={"seat": actor["seat"], "action": "call"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    s = body["state"]
    assert s["street"] in ("flop", "turn", "river", "showdown"), "Should have advanced off preflop"
