"""
Autoplay stability tests.

This test invokes the ``run_autoplay`` helper for a modest number
of hands to ensure that it completes without raising exceptions.  The
autoplay uses the API endpoints to simulate a full game loop and
therefore exercises a wide range of interactions between the engine
and the FastAPI layer.
"""

from __future__ import annotations

import unittest

from backend.scripts.autoplay import run_autoplay


class TestAutoplay(unittest.TestCase):
    def test_autoplay_runs(self) -> None:
        """Ensure that autoplay does not raise for a small number of hands."""
        # Run a smaller number of hands for speed.  If the engine has
        # pathological state leaks or infinite loops this will fail.
        run_autoplay(num_hands=10, base_seed="autoplay_test")


if __name__ == "__main__":
    unittest.main()