"""
Deterministic RNG helper for bot decisions.

This module exposes a small utility for building a repeatable pseudo-random
number generator (`random.Random`) from a list of seed components. It’s
used to guarantee that, given the same inputs and decision path, bot
choices are identical across runs and environments.

Typical usage (for each bot decision):
    from backend.policy.rng import bot_rng

    rng = bot_rng([
        base_seed or "",       # e.g., session base_seed string
        session_id,            # logger / session id (int)
        hand_id,               # "H1", "H2", ... (str) or plain int
        decision_idx,          # next action index for this hand (int)
        bot_seat,              # acting bot seat (int)
        "bot",                 # constant tag so seeds don't collide elsewhere
    ])

    # then use rng in your policy sampling
    x = rng.random()

IMPORTANT:
- Do not use global `random.*` calls anywhere in the decision path.
- Always build the RNG from the same ordered components so results are stable.
"""

from __future__ import annotations

import hashlib
import random
from typing import Iterable, Union

SeedComponent = Union[str, int]


def _to_text(components: Iterable[SeedComponent]) -> str:
    """Join heterogeneous components into a single, unambiguous text seed."""
    # Use '|' as a separator that won't appear in ints, and stringify everything.
    # Keep ordering exactly as provided by the caller.
    return "|".join(str(x) for x in components)


def _stable_int_from_text(text: str) -> int:
    """Map arbitrary text to a stable, large integer via SHA-256.

    We convert the 32-byte digest to a big-endian integer. `random.Random`
    accepts arbitrarily large ints as a seed and reduces them internally,
    but keeping the full width maximizes entropy while staying deterministic.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest, "big", signed=False)


def bot_rng(seed_components: Iterable[SeedComponent]) -> random.Random:
    """Return a deterministic `random.Random` from the given seed components.

    Args:
        seed_components: Ordered pieces that uniquely identify the decision
            (e.g., base_seed, session_id, hand_id, decision_idx, bot_seat, tag).

    Returns:
        A `random.Random` instance seeded deterministically.

    Example:
        rng = bot_rng(["DOCS-EXAMPLE", 42, "H1", 0, 1, "bot"])
        assert rng.random() == bot_rng(["DOCS-EXAMPLE", 42, "H1", 0, 1, "bot"]).random()
    """
    text = _to_text(seed_components)
    seed_int = _stable_int_from_text(text)
    return random.Random(seed_int)


__all__ = ["bot_rng"]
