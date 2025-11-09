# backend/tests/test_loop_guard_reporting.py
from fastapi.testclient import TestClient
import pytest
from backend.main import app
from backend.adapters.engines import get_adapter


def test_loop_cap_reports_clear_error(monkeypatch):
    client = TestClient(app)

    # Try to force-enable /api/hand/auto no matter how it's gated
    monkeypatch.setenv("HAND_AUTO_ENABLED", "1")
    try:
        import backend.api.hand as hand_mod  # type: ignore

        # Common patterns — try both if present:
        if hasattr(hand_mod, "AUTO_HAND_ENABLED"):
            monkeypatch.setattr(hand_mod, "AUTO_HAND_ENABLED", True, raising=False)
        if hasattr(hand_mod, "_is_auto_enabled"):
            monkeypatch.setattr(
                hand_mod, "_is_auto_enabled", lambda: True, raising=False
            )
    except Exception:
        pass  # best effort

    # Create HU session
    r = client.post(
        "/api/session",
        json={
            "seats": 2,
            "sb": 50,
            "bb": 100,
            "ante": 0,
            "stacks": [10000, 10000],
            "base_seed": "loop-cap-test",
            "human_seat": 0,
            "bot_mode": "heuristic",
        },
    )
    assert r.status_code == 200

    # Start a hand
    r = client.post("/api/hand/start")
    assert r.status_code == 200

    # Force pathological loop: next_actor always returns a bot, apply_action is a no-op
    eng = get_adapter()

    def stuck_next_actor():
        return {
            "seat": 1,
            "to_call": 0,
            "min_raise": eng.bb,
            "allowed_buckets": ["check"],
        }

    def noop_apply(seat, action, amount=None):
        return None

    monkeypatch.setattr(eng, "next_actor", stuck_next_actor, raising=True)
    monkeypatch.setattr(eng, "apply_action", noop_apply, raising=True)

    res = client.post("/api/hand/auto")

    if res.status_code == 501:
        pytest.skip("/api/hand/auto is gated off (disabled)")

    # Expect a clear error indicating the cap/loop triggered
    assert res.status_code in (400, 409, 429, 500)
    body = res.json()
    msg = (body.get("detail") or str(body)).lower()
    assert ("cap" in msg) or ("loop" in msg)
