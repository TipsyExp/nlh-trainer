# backend/tests/test_export_roundtrip.py

from __future__ import annotations

import json
from typing import Dict, Any, List

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def _create_session(seats=2, sb=50, bb=100, ante=0, stacks=None, base_seed="T12-roundtrip", human_seat=0) -> int:
    stacks = stacks or [10000, 10000]
    r = client.post(
        "/api/session",
        json={
            "seats": seats,
            "sb": sb,
            "bb": bb,
            "ante": ante,
            "stacks": stacks,
            "base_seed": base_seed,
            "human_seat": human_seat,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert "session_id" in data
    return data["session_id"]


def _start_hand() -> str:
    r = client.post("/api/hand/start")
    assert r.status_code == 200, r.text
    return r.json()["hand_id"]


def _current_actor() -> Dict[str, Any]:
    r = client.get("/api/hand/state")
    assert r.status_code == 200, r.text
    data = r.json()
    return data["actor"]


def _human_first_action(actor: Dict[str, Any]) -> Dict[str, Any]:
    # Deterministic safe line (matches engine capability):
    # if to_call == 0 -> "check" else "call"
    to_call = int(actor.get("to_call", 0) or 0)
    action = "check" if to_call == 0 else "call"
    return {"seat": int(actor["seat"]), "action": action, "amount": None}


def _post_human_action(payload: Dict[str, Any]) -> None:
    r = client.post("/api/hand/action", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True


def _export_hand_json(hand_id: str) -> Dict[str, Any]:
    r = client.get(f"/api/export/hand/{hand_id}.json")
    assert r.status_code == 200, r.text
    return r.json()


def _export_hand_csv(hand_id: str) -> str:
    r = client.get(f"/api/export/hand/{hand_id}.csv")
    assert r.status_code == 200, r.text
    return r.text


def _canonical_first_action(actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Project to a stable subset that should match across identical replays."""
    assert len(actions) >= 1
    a = actions[0]
    # Normalize keys we care about; ignore env/timestamp/seed
    keep = ["idx", "street", "actor_seat", "action", "amount", "bucket", "snapped", "to_call_after", "pot_after"]
    return {k: a.get(k) for k in keep}


def test_export_roundtrip_minimal_first_action():
    # --- Session A ---
    _create_session(base_seed="T12-roundtrip-1")
    hand_id_a = _start_hand()
    actor_a = _current_actor()
    assert actor_a is not None, "Expected a current actor after starting a hand"
    human_action_a = _human_first_action(actor_a)
    _post_human_action(human_action_a)

    exported_a = _export_hand_json(hand_id_a)
    assert exported_a["hand_id"] == hand_id_a
    actions_a = exported_a["actions"]
    assert len(actions_a) >= 1

    # Sanity: CSV exists and has a stable header
    csv_a = _export_hand_csv(hand_id_a)
    header = csv_a.splitlines()[0].split(",")
    # action header is normalized (not 'type')
    assert header[0] == "hand_id"
    assert "action" in header
    assert "created_at" in header

    # --- Session B (replay minimal first move) ---
    _create_session(base_seed="T12-roundtrip-1")  # same seed to keep structure identical
    hand_id_b = _start_hand()
    actor_b = _current_actor()
    assert actor_b is not None
    # Mirror the first action semantics from A (deterministic rule)
    human_action_b = _human_first_action(actor_b)
    _post_human_action(human_action_b)

    exported_b = _export_hand_json(hand_id_b)
    actions_b = exported_b["actions"]
    assert len(actions_b) >= 1

    # Compare canonicalized first actions
    ca = _canonical_first_action(actions_a)
    cb = _canonical_first_action(actions_b)
    assert ca == cb, f"Determinism mismatch:\nA={json.dumps(ca, sort_keys=True)}\nB={json.dumps(cb, sort_keys=True)}"
