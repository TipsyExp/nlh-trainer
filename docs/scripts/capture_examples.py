# docs/scripts/capture_examples.py
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

from fastapi.testclient import TestClient

# IMPORTANT: set LOG_DB_PATH BEFORE importing/starting the app so the logger
# initializes against our docs-local DB during startup.
ROOT = Path(__file__).resolve().parents[2]

# Ensure the repo root is importable when running this as a script
# (so "from backend.main import app" works on Windows / direct invocations)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXAMPLES_DIR = ROOT / "docs" / "examples"
EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("LOG_DB_PATH", str(EXAMPLES_DIR / "examples.sqlite"))

# Now import the FastAPI app
from backend.main import app  # noqa: E402


def _write_json(path: Path, data: Any) -> None:
    """
    Write pretty JSON with stable key ordering and normalized LF newlines
    to avoid CRLF (^M) drift on Windows.
    """
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    _write_text(path, text)


def _write_text(path: Path, text: str) -> None:
    """
    Write text with normalized LF newlines so that example files do not
    differ between Windows (CRLF) and Linux/macOS (LF).
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    path.write_text(text, encoding="utf-8")


def _deterministic_human_first_action(actor: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic policy used across docs/tests:
      - if to_call == 0 -> "check"
      - else -> "call"
    """
    to_call = int(actor.get("to_call", 0) or 0)
    action = "check" if to_call == 0 else "call"
    return {"seat": int(actor["seat"]), "action": action, "amount": None}


def main() -> None:
    # Use TestClient to fire requests against the live app (startup hooks included).
    with TestClient(app) as client:
        # --- Create session ---
        session_resp = client.post(
            "/api/session",
            json={
                "seats": 2,
                "sb": 50,
                "bb": 100,
                "ante": 0,
                "stacks": [10_000, 10_000],
                "base_seed": "DOCS-EXAMPLE-SEED-1",
                "human_seat": 0,
            },
        )
        session_resp.raise_for_status()
        session_json = session_resp.json()
        _write_json(EXAMPLES_DIR / "session_create.json", session_json)
        session_id = int(session_json["session_id"])

        # --- Start a hand ---
        start_resp = client.post("/api/hand/start")
        start_resp.raise_for_status()
        start_json = start_resp.json()
        _write_json(EXAMPLES_DIR / "hand_start.json", start_json)
        hand_id: str = start_json["hand_id"]

        # --- Current state / actor ---
        state_resp = client.get("/api/hand/state")
        state_resp.raise_for_status()
        state_json = state_resp.json()
        _write_json(EXAMPLES_DIR / "hand_state.json", state_json)

        actor = state_json.get("actor")
        if actor is None:
            # Edge: If no actor (hand already complete), still export and exit.
            export_and_write_examples(client, session_id, hand_id)
            return

        # --- Apply deterministic first human action ---
        action_payload = _deterministic_human_first_action(actor)
        action_resp = client.post("/api/hand/action", json=action_payload)
        action_resp.raise_for_status()
        action_json = action_resp.json()
        _write_json(EXAMPLES_DIR / "hand_action.json", action_json)

        # --- Export examples (hand + session) ---
        export_and_write_examples(client, session_id, hand_id)


def export_and_write_examples(client: TestClient, session_id: int, hand_id: str) -> None:
    # Hand JSON
    h_json_resp = client.get(f"/api/export/hand/{hand_id}.json")
    h_json_resp.raise_for_status()
    _write_json(EXAMPLES_DIR / "export_hand.json", h_json_resp.json())

    # Hand CSV
    h_csv_resp = client.get(f"/api/export/hand/{hand_id}.csv")
    h_csv_resp.raise_for_status()
    _write_text(EXAMPLES_DIR / "export_hand.csv", h_csv_resp.text)

    # Session JSON
    s_json_resp = client.get(f"/api/export/session/{session_id}.json")
    s_json_resp.raise_for_status()
    _write_json(EXAMPLES_DIR / "export_session.json", s_json_resp.json())

    # Session CSV
    s_csv_resp = client.get(f"/api/export/session/{session_id}.csv")
    s_csv_resp.raise_for_status()
    _write_text(EXAMPLES_DIR / "export_session.csv", s_csv_resp.text)


if __name__ == "__main__":
    main()
