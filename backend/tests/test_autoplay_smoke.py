# backend/tests/test_autoplay_smoke.py
import os
import pytest
from fastapi.testclient import TestClient
from backend.main import app


@pytest.mark.slow
def test_autoplay_smoke_50():
    os.environ["BOT_MODE"] = "heuristic"
    client = TestClient(app)

    r = client.post(
        "/api/session",
        json={
            "seats": 2,
            "sb": 50,
            "bb": 100,
            "ante": 0,
            "stacks": [10000, 10000],
            "base_seed": "smoke-50",
            "human_seat": 0,
            "bot_mode": "heuristic",
        },
    )
    assert r.status_code == 200

    for _ in range(50):
        s = client.post("/api/hand/start")
        assert s.status_code == 200
        # server should already have advanced bots to either hero or showdown
        st = client.get("/api/hand/state").json()["state"]
        assert "street" in st
        # if we're done, contract must be clean:
        if st["street"] == "showdown":
            assert st.get("to_act") is None
            assert st.get("pot_total") is not None
