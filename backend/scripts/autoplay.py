"""
Simple autoplay script for the NLH trainer backend.

This script drives the FastAPI application through its session and hand
endpoints to simulate a number of hands without human intervention.  It
is intended primarily for testing that the server and engine remain
stable over long sequences of games.  The bot policy used here is
extremely naive: it always checks when there is nothing to call and
otherwise calls any bet.  No raises are ever made.

You can run this module directly via ``python -m backend.scripts.autoplay``
or invoke ``autoplay`` programmatically from within tests.  The number
of hands to play can be provided on the command line as an integer
argument; the default is 100 hands.
"""

from __future__ import annotations

import sys
from typing import Optional

from fastapi.testclient import TestClient

from backend.main import app


def run_autoplay(num_hands: int = 100, base_seed: str = "autoplay_seed") -> None:
    """Run a naive autoplay across a number of hands.

    Args:
        num_hands: The number of hands to simulate.
        base_seed: Optional base seed to use for deterministic deck shuffling.

    Raises:
        RuntimeError: If the session creation or hand progression fails.
    """
    client = TestClient(app)
    # Configure a new session; we always play heads‑up with equal stacks.
    session_req = {
        "seats": 2,
        "sb": 50,
        "bb": 100,
        "ante": 0,
        "stacks": [10000, 10000],
        "base_seed": base_seed,
        "human_seat": 0,
    }
    resp = client.post("/api/session", json=session_req)
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to create session: {resp.text}")

    for _ in range(int(num_hands)):
        # Start a new hand; this will auto‑advance bots up to the first human action
        start = client.post("/api/hand/start")
        if start.status_code != 200:
            raise RuntimeError(f"hand start failed: {start.text}")
        # Loop until the hand completes or a safety limit is reached
        steps = 0
        while True:
            # Fetch the current public state and actor.  The /hand/state
            # endpoint will return ``actor`` as None when the hand has
            # concluded.  To avoid infinite loops (e.g. if the engine
            # never signals completion), break after a generous number of
            # iterations.
            state_resp = client.get("/api/hand/state")
            if state_resp.status_code != 200:
                raise RuntimeError(f"state query failed: {state_resp.text}")
            data = state_resp.json()
            actor = data.get("actor")
            if not actor:
                # Hand completed
                break
            # Always act from the human seat (0).  The session is
            # configured with human_seat=0 and the server will reject
            # actions for other seats.  We ignore the seat returned in
            # actor because bots are advanced automatically by the API.
            to_call = int(actor.get("to_call", 0))
            action_req = {
                "seat": 0,
                "action": "check" if to_call <= 0 else "call",
                "amount": None,
            }
            action = client.post("/api/hand/action", json=action_req)
            # Treat non‑200 as fatal
            if action.status_code != 200:
                raise RuntimeError(f"action failed: {action.text}")
            steps += 1
            if steps > 100:
                # Break to avoid hanging if the engine fails to end the hand
                break


def main(argv: Optional[list[str]] = None) -> None:
    """Entry point for CLI execution.

    Pass the number of hands to play as the first argument.  When run
    without arguments, defaults to 100 hands.
    """
    if argv is None:
        argv = sys.argv[1:]
    try:
        num = int(argv[0]) if argv else 100
    except ValueError:
        print(f"Invalid number of hands: {argv[0]}")
        sys.exit(1)
    try:
        run_autoplay(num_hands=num)
    except Exception as exc:
        print(f"Autoplay encountered an error: {exc}")
        sys.exit(2)


if __name__ == "__main__":
    main()
