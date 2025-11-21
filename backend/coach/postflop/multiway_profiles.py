# backend/coach/postflop/multiway_profiles.py
"""
Multiway postflop villain range profiles for the coach.

This module centralises how we assign **villain ranges** in multiway pots.
It is intentionally conservative and simple:

  * We start from the same TAG-style postflop ranges used for HU
    (see backend.coach.postflop.ranges).
  * For each active villain seat we decide a coarse role relative to the
    hero ("ip" or "oop") and pick a range from that profile.
  * The output is either:
      - a list of MultiwaySeatProfile objects, or
      - a convenience dict mapping seat -> range string.

The goal is to keep villain modelling logic in one place so the multiway
postflop coach can consume it without hardcoding ranges or roles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from backend.coach.decision_context import DecisionContext
from backend.coach.postflop.ranges import (
    DEFAULT_PROFILE_NAME,
    ProfileName,
    Role,
    get_hu_villain_range,
)


@dataclass(frozen=True)
class MultiwaySeatProfile:
    """
    Description of a single villain's postflop profile in a multiway pot.

    Fields:
        seat:
            Seat index of the villain.

        role:
            Villain's role relative to the hero on this street:
              - "ip"  – acts after the hero (in position)
              - "oop" – acts before the hero (out of position)

        profile:
            Abstract profile name (currently only "TAG").

        range:
            Concrete range string in the equity engine's syntax.
    """

    seat: int
    role: Role
    profile: ProfileName
    range: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _infer_role_relative_to_hero(
    hero_seat: int,
    villain_seat: int,
    active_seats: List[int],
) -> Role:
    """
    Best-effort classification of a villain as IP or OOP relative to hero.

    Heuristic:
        * Sort active_seats.
        * Seats that appear **after** hero_seat in that ordering are treated
          as "ip" (they act after hero).
        * Seats that appear **before** hero_seat are treated as "oop".

    This is deliberately simple and engine-agnostic; it does not attempt to
    reconstruct exact betting order by street. If the hero is not in
    active_seats, all villains are treated as OOP.
    """
    if not active_seats or hero_seat not in active_seats:
        return "oop"

    ordered = sorted(int(s) for s in active_seats)
    hero_seat = int(hero_seat)
    villain_seat = int(villain_seat)

    if villain_seat not in ordered:
        return "oop"

    hero_idx = ordered.index(hero_seat)
    villain_idx = ordered.index(villain_seat)

    return "ip" if villain_idx > hero_idx else "oop"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_multiway_profiles(
    *,
    street: str,
    hero_seat: int,
    active_seats: List[int],
    profile: ProfileName = DEFAULT_PROFILE_NAME,
) -> List[MultiwaySeatProfile]:
    """
    Construct MultiwaySeatProfile entries for all **villain** seats.

    Args:
        street:
            Current street name; typically "flop", "turn", or "river".
            Unknown values are tolerated; underlying range helpers will
            fall back to reasonable defaults.

        hero_seat:
            Hero's seat index. This seat is excluded from the result.

        active_seats:
            List of seat indices that appear to still be in the hand.

        profile:
            Name of the villain profile to use (currently only "TAG").

    Returns:
        A list of MultiwaySeatProfile objects, one per active villain seat.
    """
    hero_seat = int(hero_seat)
    active = [int(s) for s in active_seats or []]

    profiles: List[MultiwaySeatProfile] = []

    if not active:
        return profiles

    for seat in active:
        if seat == hero_seat:
            continue

        role = _infer_role_relative_to_hero(
            hero_seat=hero_seat, villain_seat=seat, active_seats=active
        )
        rng = get_hu_villain_range(street=street, role=role, profile=profile)

        profiles.append(
            MultiwaySeatProfile(
                seat=seat,
                role=role,
                profile=profile,
                range=rng,
            )
        )

    return profiles


def get_multiway_villain_ranges(
    *,
    street: str,
    hero_seat: int,
    active_seats: List[int],
    profile: ProfileName = DEFAULT_PROFILE_NAME,
) -> Dict[int, str]:
    """
    Convenience helper: map villain seat -> range string for a multiway pot.

    This is the function most callers (e.g. the multiway postflop coach)
    will use when constructing equity queries.

    Args:
        street:
            Current street (e.g. "flop", "turn", "river").

        hero_seat:
            Hero's seat index.

        active_seats:
            List of seats still in the pot.

        profile:
            Villain profile name (currently "TAG").

    Returns:
        Dict mapping each **villain** seat index to a range string.
    """
    profiles = build_multiway_profiles(
        street=street,
        hero_seat=hero_seat,
        active_seats=active_seats,
        profile=profile,
    )
    return {p.seat: p.range for p in profiles}


def get_multiway_villain_ranges_for_context(
    ctx: DecisionContext,
    profile: ProfileName = DEFAULT_PROFILE_NAME,
) -> Dict[int, str]:
    """
    Convenience wrapper around `get_multiway_villain_ranges` that operates
    directly on a DecisionContext.

    Only seats in `ctx.active_seats` other than `ctx.hero_seat` are given
    ranges. HU spots will return a mapping with at most one entry; true
    multiway pots (3+ players) will return one entry per villain seat.
    """
    return get_multiway_villain_ranges(
        street=ctx.street,
        hero_seat=ctx.hero_seat,
        active_seats=ctx.active_seats,
        profile=profile,
    )


__all__ = [
    "MultiwaySeatProfile",
    "build_multiway_profiles",
    "get_multiway_villain_ranges",
    "get_multiway_villain_ranges_for_context",
]
