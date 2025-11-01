# backend/tests/test_exports.py
from __future__ import annotations

import csv
from typing import Any, Dict
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def _create_session(seats=2, sb=50, bb=100, ante=0, stacks=None, base_seed="T12-export", human_seat=0) -> int:
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
    return int(data["session_id"])

def _start_hand() -> str:
    r = client.post("/api/hand/start")
    assert r.status_code == 200, r.text
    return r.json()["hand_id"]

def _get_state() -> Dict[str, Any]:
    r = client.get("/api/hand/state")
    assert r.status_code == 200, r.text
    return r.json()

def _deterministic_first_action(actor: Dict[str, Any]) -> Dict[str, Any]:
    to_call = int(actor.get("to_call", 0) or 0)
    action = "check" if to_call == 0 else "call"
    return {"seat": int(actor["seat"]), "action": action, "amount": None}

def _post_action(payload: Dict[str, Any]) -> Dict[str, Any]:
    r = client.post("/api/hand/action", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    return data

def _export_hand_json(hand_id: str) -> Dict[str, Any]:
    r = client.get(f"/api/export/hand/{hand_id}.json")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/json")
    return r.json()

def _export_hand_csv(hand_id: str) -> str:
    r = client.get(f"/api/export/hand/{hand_id}.csv")
    assert r.status_code == 200, r.text
    assert "text/csv" in r.headers["content-type"]
    return r.text

def _export_session_json(session_id: int) -> Dict[str, Any]:
    r = client.get(f"/api/export/session/{session_id}.json")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/json")
    return r.json()

def _export_session_csv(session_id: int) -> str:
    r = client.get(f"/api/export/session/{session_id}.csv")
    assert r.status_code == 200, r.text
    assert "text/csv" in r.headers["content-type"]
    return r.text

def test_export_endpoints_and_shapes_minimal():
    # Arrange: session + one deterministic human action
    session_id = _create_session(base_seed="T12-export-1")
    hand_id = _start_hand()
    state = _get_state()
    actor = state.get("actor")
    if actor:
        _post_action(_deterministic_first_action(actor))

    # ---- Hand JSON ----
    h_json = _export_hand_json(hand_id)
    assert h_json["hand_id"] == hand_id
    assert isinstance(h_json.get("actions"), list)
    assert len(h_json["actions"]) >= 1

    # First action has a stable subset of keys
    a0 = h_json["actions"][0]
    for k in ["idx", "street", "actor_seat", "action"]:
        assert k in a0

    # ---- Hand CSV ----
    h_csv = _export_hand_csv(hand_id)
    lines = [ln for ln in h_csv.splitlines() if ln.strip()]
    assert len(lines) >= 2  # header + ≥1 row
    reader = csv.reader(lines)
    h_hdr = next(reader)
    # Minimal stability: hand_id first; action & created_at present
    assert h_hdr[0] == "hand_id"
    assert "action" in h_hdr
    assert "created_at" in h_hdr
    h_row = next(reader)
    assert len(h_row) == len(h_hdr)

    # ---- Session JSON ----
    s_json = _export_session_json(session_id)
    assert int(s_json["session_id"]) == int(session_id)
    assert isinstance(s_json.get("hands"), list)
    assert any(h.get("hand_id") == hand_id for h in s_json["hands"])

    # ---- Session CSV ----
    s_csv = _export_session_csv(session_id)
    slines = [ln for ln in s_csv.splitlines() if ln.strip()]
    assert len(slines) >= 2
    sreader = csv.reader(slines)
    sheader = next(sreader)

    # Session CSV is a flattened per-action log for the session; it mirrors the hand CSV header
    # (hand_id, idx, street, actor_seat, action, amount, ..., created_at)
    assert sheader[0] == "hand_id"
    assert "action" in sheader
    assert "created_at" in sheader

    srow = next(sreader)
    assert len(srow) == len(sheader)

    # Since this test produced exactly one hand, rows should reference that hand_id
    hi = sheader.index("hand_id")
    assert srow[hi] == hand_id
