"""
Quick bots-only autoplay driver for M0.
Runs N hands HU (human_seat still 0, but we auto-apply "check/call" for both seats).

Usage:
  python -m backend.scripts.autoplay --hands 1000 --seed AUTO
"""

from __future__ import annotations
import argparse
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def start_session(seed: str):
    r = client.post("/api/session", json={
        "seats": 2, "sb": 50, "bb": 100, "ante": 0,
        "stacks": [10000, 10000],
        "base_seed": seed,
        "human_seat": 0,
    })
    r.raise_for_status()

def start_hand():
    r = client.post("/api/hand/start")
    r.raise_for_status()

def state():
    r = client.get("/api/hand/state")
    r.raise_for_status()
    return r.json()

def apply_action(seat: int, action: str, amount: int | None = None):
    payload = {"seat": seat, "action": action}
    if amount is not None:
        payload["amount"] = amount
    r = client.post("/api/hand/action", json=payload)
    r.raise_for_status()
    return r.json()

def bot_policy(actor) -> tuple[str, int | None]:
    # super-naive policy for autoplay:
    # if to_call == 0 -> check; else -> call
    to_call = int(actor.get("to_call", 0))
    if to_call <= 0:
        return "check", None
    return "call", None

def play_one_hand() -> None:
    start_hand()
    # step until there is no actor or the adapter moves streets to end
    for _ in range(200):
        s = state()
        actor = s.get("actor")
        if not actor:
            break
        action, amount = bot_policy(actor)
        # always act from "human seat" (0) when it's our turn,
        # but our API only accepts actions from human_seat, so if it's seat 1 we skip
        if int(actor["seat"]) != 0:
            # we can't post actions for bots via /api here; just fetch again
            # engine auto-advances bots on the human's check/call path when applicable
            # so we emulate "wait" by calling state again after a no-op
            # if needed, you could add a non-API direct engine driver later.
            # To force progress, try a no-op "check" if allowed.
            if int(actor.get("to_call", 0)) == 0:
                apply_action(0, "check")
            else:
                apply_action(0, "call")
        else:
            apply_action(0, action, amount)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hands", type=int, default=1000)
    ap.add_argument("--seed", type=str, default="AUTO")
    args = ap.parse_args()

    start_session(args.seed)
    for i in range(args.hands):
        play_one_hand()
        if (i + 1) % 100 == 0:
            print(f"Played {i+1} hands")

if __name__ == "__main__":
    main()
