# backend/tests/test_policy_timeout_fallback.py

import time
from fastapi.testclient import TestClient
from backend.main import app
from backend.bots.policy import BotPolicy


class _SlowPolicy(BotPolicy):
    def decide(self, ctx, rng):
        # Simulate heavy compute way beyond the time budget
        time.sleep(0.5)
        # Would never be returned if the timeout is respected
        return {"action": "raise", "amount": 10**9}


def test_bot_timeout_falls_back_to_safe(monkeypatch):
    client = TestClient(app)

    # Tighten budget for the test
    monkeypatch.setenv("BOT_TIME_BUDGET_MS", "50")

    # Monkeypatch the policy selector to always use our slow policy
    import backend.api.hand as hand_mod

    monkeypatch.setattr(
        hand_mod, "_select_bot_policy", lambda: _SlowPolicy(), raising=True
    )

    # Session with bots enabled
    r = client.post(
        "/api/session",
        json={
            "seats": 2,
            "sb": 50,
            "bb": 100,
            "ante": 0,
            "stacks": [10000, 10000],
            "base_seed": "timeout-test",
            "human_seat": 0,
            "bot_mode": "heuristic",
        },
    )
    assert r.status_code == 200

    # Start hand; server should auto-advance to first human decision.
    r = client.post("/api/hand/start")
    assert r.status_code == 200

    # State should be valid; no hang; if a bot had to act, fallback must be legal.
    st = client.get("/api/hand/state").json()["state"]
    assert "street" in st
    # We don't assert the exact fallback move here; success = no error/hang and legal state.
