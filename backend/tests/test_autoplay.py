"""
Autoplay stability tests.

This test invokes the ``run_autoplay`` helper for a modest number
of hands to ensure that it completes without raising exceptions. The
tests cover both the default (CALLCHECK) bot and the opt-in TAG bot
profile gated by an environment variable / parameter.
"""

from __future__ import annotations

import os
import unittest

from backend.scripts.autoplay import run_autoplay


class TestAutoplay(unittest.TestCase):
    def test_autoplay_runs_default(self) -> None:
        """Default policy (CALLCHECK): should complete a few hands cleanly."""
        prev = os.environ.get("BOT_PROFILE")
        try:
            # Ensure default behavior
            if "BOT_PROFILE" in os.environ:
                del os.environ["BOT_PROFILE"]
            # Small run for speed
            run_autoplay(num_hands=5, base_seed="autoplay_default")
        finally:
            # Restore env
            if prev is not None:
                os.environ["BOT_PROFILE"] = prev
            elif "BOT_PROFILE" in os.environ:
                del os.environ["BOT_PROFILE"]

    def test_autoplay_runs_tag_profile(self) -> None:
        """TAG policy enabled: still completes cleanly with fixed seed."""
        # Prefer passing the profile to the helper (it sets/clears env internally).
        run_autoplay(num_hands=5, base_seed="autoplay_tag", bot_profile="TAG")


if __name__ == "__main__":
    unittest.main()
