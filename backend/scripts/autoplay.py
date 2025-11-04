"""
Simple autoplay script for the NLH trainer backend.

This script drives the FastAPI application through its session and hand
endpoints to simulate a number of hands without human intervention. It
is intended primarily for testing that the server and engine remain
stable over long sequences of games.

Defaults:
- Human policy: always check when there is nothing to call, otherwise call.
- Bot policy: selected via the BOT_PROFILE environment variable or the
  --bot-profile flag here ("CALLCHECK" default; use "TAG" to enable the TAG profile).

Run via:
  python -m backend.scripts.autoplay --hands 100 --base-seed autoplay_seed --bot-profile TAG
"""

from __future__ import annotations

import os
import sys
import argparse
from typing import Optional

from fastapi.testclient import TestClient

from backend.main import app


def run_autoplay(
    num_hands: int = 100,
    base_seed: str = "autoplay_seed",
    bot_profile: Optional[str] = None,
) -> None:
    """Run autoplay across a number of hands.

    Args:
        num_hands: Number of hands to simulate.
        base_seed: Base seed for deterministic deck shuffling.
        bot_profile: Optional bot policy name ("CALLCHECK" default, "TAG" supported).

    Raises:
        RuntimeError: If the session creation or hand progression fails.
    """
    if bot_profile:
        os.environ["BOT_PROFILE"] = bot_profile.strip().upper()

    client = TestClient(app)

    # Configure a new session; we always play heads-up with equal stacks.
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

    for hand_no in range(int(num_hands)):
        # Start a new hand; this will auto-advance bots up to the first human action
        start = client.post("/api/hand/start")
        if start.status_code != 200:
            raise RuntimeError(f"hand start failed: {start.text}")

        # Loop until the hand completes or a safety limit is reached
        steps = 0
        while True:
            # Fetch current state and actor
            state_resp = client.get("/api/hand/state")
            if state_resp.status_code != 200:
                raise RuntimeError(f"state query failed: {state_resp.text}")
            data = state_resp.json()
            actor = data.get("actor")
            if not actor:
                # Hand completed
                break

            # Human (seat 0) acts: check if nothing to call, else call
            to_call = int(actor.get("to_call", 0))
            action_req = {
                "seat": 0,
                "action": "check" if to_call <= 0 else "call",
                "amount": None,
            }
            action = client.post("/api/hand/action", json=action_req)
            if action.status_code != 200:
                raise RuntimeError(f"action failed: {action.text}")

            steps += 1
            if steps > 100:
                # Safety: break to avoid hanging if the engine fails to end the hand
                break


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Autoplay NLH trainer hands using FastAPI TestClient."
    )
    p.add_argument(
        "--hands",
        "-n",
        type=int,
        default=100,
        help="Number of hands to play (default: 100)",
    )
    p.add_argument(
        "--base-seed",
        type=str,
        default="autoplay_seed",
        help='Base seed for deterministic decks (default: "autoplay_seed")',
    )
    p.add_argument(
        "--bot-profile",
        type=str,
        choices=["CALLCHECK", "TAG", "callcheck", "tag"],
        default=None,
        help='Bot profile (default: CALLCHECK). Use "TAG" to enable the TAG bot.',
    )
    return p


def main(argv: Optional[list[str]] = None) -> None:
    """Entry point for CLI execution."""
    if argv is None:
        argv = sys.argv[1:]

    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    bot_profile = args.bot_profile.upper() if args.bot_profile else None

    try:
        run_autoplay(
            num_hands=args.hands,
            base_seed=args.base_seed,
            bot_profile=bot_profile,
        )
    except Exception as exc:
        print(f"Autoplay encountered an error: {exc}")
        sys.exit(2)


if __name__ == "__main__":
    main()
