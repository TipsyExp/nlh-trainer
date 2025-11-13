# docs/scripts/capture_examples.py
from __future__ import annotations

import csv
import io
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

from fastapi.testclient import TestClient

# ---- Repository root & import path shim (so "import backend" works when run as a script)
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# IMPORTANT: set LOG_DB_PATH BEFORE importing/starting the app so the logger
# initializes against our docs-local DB during startup.
EXAMPLES_DIR = ROOT / "docs" / "examples"
EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("LOG_DB_PATH", str(EXAMPLES_DIR / "examples.sqlite"))

# Canonical, CI-like environment (deterministic & coach off)
os.environ.setdefault("COACH_ENABLED", "false")
os.environ.setdefault("PYTHONHASHSEED", "0")
for _k in ("BOT_MODE", "BOT_PROFILE", "HAND_AUTO_ENABLED", "ENGINE_DEBUG_HTTP"):
    os.environ.pop(_k, None)

# Reset the docs DB so session_id starts at 1 every run (remove DB + WAL/SHM if present)
_db = Path(os.environ["LOG_DB_PATH"])
for _p in (
    _db,
    _db.with_suffix(_db.suffix + "-wal"),
    _db.with_suffix(_db.suffix + "-shm"),
):
    try:
        _p.unlink()
    except FileNotFoundError:
        pass

# Now import the FastAPI app (after env & DB reset)
from backend.main import app  # noqa: E402

# Volatile fields vary run-to-run; strip them from docs artifacts to avoid drift
VOLATILE_JSON_KEYS = {"created_at", "time_ms", "rng_seed", "meta"}
VOLATILE_CSV_COLUMNS = {"created_at", "time_ms", "rng_seed", "meta"}


def _normalize_eol(text: str) -> str:
    # Normalize CRLF/CR to LF so examples don't flip on Windows vs Linux
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _write_text(path: Path, text: str) -> None:
    path.write_text(_normalize_eol(text), encoding="utf-8")


def _strip_volatile_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: _strip_volatile_json(v)
            for k, v in obj.items()
            if k not in VOLATILE_JSON_KEYS
        }
    if isinstance(obj, list):
        return [_strip_volatile_json(v) for v in obj]
    return obj


def _write_json(path: Path, data: Any) -> None:
    # Canonical JSON for docs (sorted keys, pretty, LF EOLs, volatile keys removed)
    clean = _strip_volatile_json(data)
    _write_text(path, json.dumps(clean, indent=2, sort_keys=True) + "\n")


def _rewrite_csv_drop_columns(csv_text: str, drop: set[str]) -> str:
    # Drop volatile columns; keep header order for the rest; normalize EOLs to LF
    csv_text = _normalize_eol(csv_text)
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    if not rows:
        return ""
    header = rows[0]
    keep_idx = [i for i, name in enumerate(header) if name not in drop]
    new_header = [header[i] for i in keep_idx]
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(new_header)
    for row in rows[1:]:
        if not row:
            continue
        writer.writerow([row[i] for i in keep_idx if i < len(row)])
    return out.getvalue()


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


def export_and_write_examples(
    client: TestClient, session_id: int, hand_id: str
) -> None:
    # Hand JSON (canonicalized)
    h_json_resp = client.get(f"/api/export/hand/{hand_id}.json")
    h_json_resp.raise_for_status()
    _write_json(EXAMPLES_DIR / "export_hand.json", h_json_resp.json())

    # Hand CSV (drop volatile columns, normalize EOLs)
    h_csv_resp = client.get(f"/api/export/hand/{hand_id}.csv")
    h_csv_resp.raise_for_status()
    _write_text(
        EXAMPLES_DIR / "export_hand.csv",
        _rewrite_csv_drop_columns(h_csv_resp.text, VOLATILE_CSV_COLUMNS),
    )

    # Session JSON (canonicalized)
    s_json_resp = client.get(f"/api/export/session/{session_id}.json")
    s_json_resp.raise_for_status()
    _write_json(EXAMPLES_DIR / "export_session.json", s_json_resp.json())

    # Session CSV (drop volatile columns, normalize EOLs)
    s_csv_resp = client.get(f"/api/export/session/{session_id}.csv")
    s_csv_resp.raise_for_status()
    _write_text(
        EXAMPLES_DIR / "export_session.csv",
        _rewrite_csv_drop_columns(s_csv_resp.text, VOLATILE_CSV_COLUMNS),
    )


if __name__ == "__main__":
    main()
