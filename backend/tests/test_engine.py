"""
Unit tests for the PokerKitAdapter and API behaviours.

These tests exercise min‑raise enforcement, heads‑up order logic, off‑tree
size snapping, and RNG determinism.  They use the FastAPI TestClient to
interact with the service endpoints and also exercise the adapter
directly where appropriate.  The tests are written using Python's
``unittest`` framework so they can run without the external ``pytest``
dependency.
"""

from __future__ import annotations

import unittest
from typing import List

from fastapi.testclient import TestClient

from backend.main import app
from backend.adapters.engines.pokerkit_adapter import PokerKitAdapter


def _setup_session(client: TestClient, base_seed: str | None = None) -> None:
    """Create a new session using the default HU parameters.

    Args:
        client: A TestClient instance bound to the FastAPI app.
        base_seed: Optional base seed for deterministic shuffling.
    """
    req = {
        "seats": 2,
        "sb": 50,
        "bb": 100,
        "ante": 0,
        "stacks": [10000, 10000],
        "human_seat": 0,
    }
    if base_seed is not None:
        req["base_seed"] = base_seed
    resp = client.post("/api/session", json=req)
    assert resp.status_code == 200, f"session creation failed: {resp.text}"


class TestPokerKitAdapter(unittest.TestCase):
    """Tests covering engine logic independent of the API layer."""

    def test_rng_determinism(self) -> None:
        """Ensure that identical base seeds produce identical hands and deck seeds."""
        eng1 = PokerKitAdapter()
        eng1.start_table(2, 50, 100, 0, [10000, 10000], base_seed="seed")
        hand1 = eng1.start_hand()
        state1 = eng1.state()
        holes1: List[List[str]] = [list(p.hole_cards) for p in state1.players]
        seed1 = state1.deck_seed

        eng2 = PokerKitAdapter()
        eng2.start_table(2, 50, 100, 0, [10000, 10000], base_seed="seed")
        hand2 = eng2.start_hand()
        state2 = eng2.state()
        holes2: List[List[str]] = [list(p.hole_cards) for p in state2.players]
        seed2 = state2.deck_seed

        # Hand identifiers should both be H1 and deck seeds identical
        self.assertEqual(hand1, "H1")
        self.assertEqual(hand2, "H1")
        self.assertEqual(seed1, seed2)
        self.assertEqual(holes1, holes2)

        # Starting a second hand with the same base seed should repeat deterministically
        hand1b = eng1.start_hand()
        state1b = eng1.state()
        holes1b: List[List[str]] = [list(p.hole_cards) for p in state1b.players]
        seed1b = state1b.deck_seed
        hand2b = eng2.start_hand()
        state2b = eng2.state()
        holes2b: List[List[str]] = [list(p.hole_cards) for p in state2b.players]
        seed2b = state2b.deck_seed
        self.assertEqual(hand1b, "H2")
        self.assertEqual(hand2b, "H2")
        self.assertEqual(seed1b, seed2b)
        self.assertEqual(holes1b, holes2b)


class TestAPIAdapterInteractions(unittest.TestCase):
    """Tests covering the adapter via the FastAPI endpoints."""

    def setUp(self) -> None:
        self.client = TestClient(app)
        _setup_session(self.client)

    def test_min_raise_enforcement(self) -> None:
        """Verify that raises below the minimum are rejected and that legal raises are accepted."""
        # Start a new hand
        self.client.post("/api/hand/start")
        state_resp = self.client.get("/api/hand/state").json()
        actor = state_resp["actor"]
        to_call = int(actor["to_call"])
        min_raise = int(actor["min_raise"])
        seat = int(actor["seat"])
        # Construct an illegal raise that is trivially below any valid bucket
        illegal_total = to_call + 1  # e.g. call plus 1 chip
        resp_bad = self.client.post(
            "/api/hand/action",
            json={"seat": seat, "action": "raise", "amount": illegal_total},
        )
        self.assertEqual(resp_bad.status_code, 400)
        self.assertIn("min-raise", resp_bad.json().get("detail", ""))

        # Raise with the advertised minimum; engine may snap up to the nearest bucket
        resp_ok = self.client.post(
            "/api/hand/action",
            json={"seat": seat, "action": "raise", "amount": min_raise},
        )
        self.assertEqual(resp_ok.status_code, 200)
        last = resp_ok.json()["state"]["last_action"]
        committed = int(last.get("committed"))
        # Committed must be at least the advertised minimum
        self.assertGreaterEqual(committed, min_raise)
        # Snap flag indicates whether the requested amount was adjusted
        # It is acceptable for the engine to snap upward

    def test_hu_preflop_call_transitions_to_flop(self) -> None:
        """Direct engine test: SB call followed by BB check advances to flop with BB acting first.

        This test bypasses the API auto‑advance mechanism to exercise the
        underlying adapter directly.  In heads‑up play the small blind
        acts first preflop.  When the small blind calls and the big blind
        checks, the street should transition to the flop and the big blind
        should be the next actor.  The engine should not prematurely
        terminate the hand.
        """
        from backend.adapters.engines.pokerkit_adapter import PokerKitAdapter

        eng = PokerKitAdapter()
        eng.start_table(2, 50, 100, 0, [10000, 10000], base_seed="test")
        eng.start_hand()
        # Preflop: small blind acts first
        a = eng.next_actor()
        self.assertEqual(a["seat"], eng.sb_seat)
        # SB calls
        eng.apply_action(a["seat"], "call")
        # Now big blind should act
        b = eng.next_actor()
        self.assertEqual(b["seat"], eng.bb_seat)
        # BB checks
        eng.apply_action(b["seat"], "check")
        # Street should have progressed to the flop
        state = eng.state()
        self.assertEqual(state.street, "flop")
        # Next actor should remain the big blind on the flop
        c = eng.next_actor()
        self.assertEqual(c["seat"], eng.bb_seat)

    def test_off_tree_size_snapping(self) -> None:
        """Raising to an unsupported amount should snap to the nearest bucket."""
        # Start a new hand
        self.client.post("/api/hand/start")
        # Query actor info
        actor = self.client.get("/api/hand/state").json()["actor"]
        seat = actor["seat"]
        # Determine to_call to craft off‑tree raise
        to_call = int(actor["to_call"])
        # Request a total that is between two allowed raise targets
        # For preflop facing to_call=50, allowed targets are call, 300, 350.  Request 325 to snap to 300 or 350.
        requested = to_call + 275  # 325 total commitment
        resp = self.client.post(
            "/api/hand/action",
            json={"seat": seat, "action": "raise", "amount": requested},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["state"]
        last = data["last_action"]
        # Ensure the request was snapped
        self.assertTrue(last.get("snapped", False))
        committed = int(last.get("committed", 0))
        allowed_labels = last.get("allowed_buckets", [])
        # Determine BB from the state to compute bucket targets
        bb = int(data["table"]["bb"])
        expected_targets: List[int] = []
        for label in allowed_labels:
            # Skip call bucket when evaluating raise targets
            if label == "call":
                continue
            if label == "2.2x":
                expected_targets.append(max(int(round(2.2 * bb)), bb))
            elif label == "2.5x":
                expected_targets.append(max(int(round(2.5 * bb)), bb))
            elif label == "3.0x":
                expected_targets.append(max(int(round(3.0 * bb)), bb))
            elif label in ("2.5xR", "3.0xR"):
                # Facing action labels include R suffix; compute on top of to_call
                mult = 2.5 if label.startswith("2.5") else 3.0
                expected_targets.append(to_call + int(round(mult * max(bb, 100))))
            elif label == "jam":
                expected_targets.append(10**12)
        self.assertIn(committed, expected_targets)


if __name__ == "__main__":
    unittest.main()