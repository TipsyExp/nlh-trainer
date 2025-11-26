# backend/coach/postflop/ranges.py
"""
Postflop villain range presets for the coach.

This module defines a small set of *coarse* villain profiles that the
postflop coach can use when constructing equity queries. It is
intentionally conservative and simple:

  * Profiles are identified by a short name (e.g. "TAG").
  * For each profile we define HU postflop ranges by street and role:
      - street: "flop" | "turn" | "river"
      - role:   "ip"   | "oop"
  * Ranges are expressed in the same text format accepted by the equity
    service (hand/range strings such as:
        "AA,KK,QQ,JJ,TT,99,AKs,AQs,AJs,KQs,AKo,AQo"
    or generic ranges like:
        "22+,A2s+,K9s+,QTs+,JTs,ATo+,KQo"
    )

Current scope for M3 / Task 3:

  * Only HU ranges are defined.
  * Only a single default profile ("TAG") is provided.

Task 4 extends usage of this module so that:

  * HU helper functions remain the primary API for heads-up spots.
  * Shared utilities (street normalisation, generic fallback ranges) can be
    reused by multiway profile helpers defined in sibling modules.

The postflop coach service (HU or multiway) is expected to:

  * Decide which profile to use (typically from configuration).
  * Decide which role ("ip" vs "oop") applies to the villain at a given
    decision.
  * Call `get_hu_villain_range(...)` or a multiway profile helper to obtain
    a range string.

This file deliberately avoids importing DecisionContext or config modules
to keep dependencies simple and testable.
"""

from __future__ import annotations

from typing import Dict, List, Literal

Role = Literal["ip", "oop"]
ProfileName = Literal["TAG"]
StreetKey = Literal["flop", "turn", "river"]

DEFAULT_PROFILE_NAME: ProfileName = "TAG"

# Generic semi-tight default used as a last-resort fallback for unknown
# (street, role, profile) combinations.
GENERIC_SEMITIGHT_DEFAULT_RANGE = "22+,A2s+,K9s+,QTs+,JTs,ATo+,KQo"


# ---------------------------------------------------------------------------
# Internal profile definitions (HU, TAG-ish)
# ---------------------------------------------------------------------------
#
# These are deliberately coarse "TAG-ish" ranges intended as a starting
# point, not a final strategy model. They can be tuned independently of
# coach logic as we gather data.
#
# Semantics:
#   _HU_TAG_RANGES[street][role] -> range string
#
# Where range strings follow the usual preflop range expression syntax:
#   - "22+" means all pairs 22–AA.
#   - "A2s+" means suited A2–AK.
#   - "ATo+" means offsuit AT–AK.
#   - Commas separate components.
#

_HU_TAG_RANGES: Dict[StreetKey, Dict[Role, str]] = {
    # Generic "got here by playing a reasonable preflop strategy" range.
    "flop": {
        "ip": ("22+,A2s+,K9s+,Q9s+,J9s+,T9s,98s,87s," "ATo+,KJo+,QJo"),
        "oop": ("22+,A2s+,KTs+,QTs+,JTs,T9s,98s,87s," "AJo+,KQo"),
    },
    # Turn and river ranges are slightly tighter by default; in practice
    # these will be refined once we have per-node profiles.
    "turn": {
        "ip": ("55+,A5s+,KTs+,QTs+,JTs,T9s,98s," "AQo+,KQo"),
        "oop": ("66+,A5s+,KTs+,QTs+,JTs,T9s,98s," "AQo+,KQo"),
    },
    "river": {
        "ip": ("77+,ATs+,KTs+,QTs+,JTs,T9s," "AQo+,KQo"),
        "oop": ("88+,ATs+,KTs+,QTs+,JTs," "AQo+,KQo"),
    },
}


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------


def normalize_street_key(street: str) -> StreetKey:
    """
    Normalise an arbitrary street string into the internal StreetKey type.

    Unknown values are mapped to "flop" as a safe default.
    """
    s = street.lower().strip()
    if s in ("flop", "turn", "river"):
        return s  # type: ignore[return-value]
    return "flop"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def available_profiles() -> List[ProfileName]:
    """
    Return the list of known villain profile names.

    Useful for configuration validation and tests.
    """
    # For now we only expose the default profile, but the interface is future-proof.
    return [DEFAULT_PROFILE_NAME]


def get_hu_villain_range(
    *,
    street: str,
    role: Role,
    profile: ProfileName = DEFAULT_PROFILE_NAME,
) -> str:
    """
    Return a default HU postflop villain range for the given
    (street, role, profile).

    Args:
        street:
            Current street name; case-insensitive. Expected values are
            "flop", "turn", or "river". Unknown streets fall back to
            "flop".

        role:
            Villain's role relative to the hero:
              - "ip"  – in position
              - "oop" – out of position

        profile:
            Name of the villain profile. Currently only "TAG" is
            defined; other values are treated as "TAG" for now.

    Returns:
        A range string in the equity engine's native syntax.

    Fallback behaviour:
        - Unknown profile → treated as DEFAULT_PROFILE_NAME ("TAG").
        - Unknown street  → treated as "flop".
        - If a particular (street, role) mapping is missing, falls back
          to the "flop" range for that role; if that is also missing,
          returns a generic semi-tight default:
              GENERIC_SEMITIGHT_DEFAULT_RANGE.
    """
    # Normalise inputs
    street_key: StreetKey = normalize_street_key(street)

    role_norm: Role = "ip" if role == "ip" else "oop"

    # Only "TAG" is currently implemented; other names alias to TAG.
    profile_norm = profile.upper()
    if profile_norm != "TAG":
        profile_norm = "TAG"

    # Future: branch on profile_norm when more profiles are added.
    ranges = _HU_TAG_RANGES

    # Try exact (street, role)
    by_street = ranges.get(street_key, {})
    value = by_street.get(role_norm)
    if value:
        return value

    # Fallback: try flop for the same role
    flop_value = ranges.get("flop", {}).get(role_norm)
    if flop_value:
        return flop_value

    # Last resort: semi-tight default
    return GENERIC_SEMITIGHT_DEFAULT_RANGE


def get_default_villain_range(street: str, role: Role = "oop") -> str:
    """
    Convenience helper used by the HU postflop coach v1.

    This is equivalent to:

        get_hu_villain_range(
            street=street,
            role=role,
            profile=DEFAULT_PROFILE_NAME,
        )

    It lets the coach depend on a minimal, profile-agnostic API while
    still keeping the richer profile-based helper available for future
    configuration work.

    Multiway helpers in sibling modules may also use this as a generic
    "reasonable villain" range when they don't have seat-specific
    profiles available.
    """
    return get_hu_villain_range(street=street, role=role, profile=DEFAULT_PROFILE_NAME)


def get_villain_range_for_postflop(
    *,
    street: str,
    hero_is_ip: bool,
    preflop_line: str | None = None,
    hero_position: str | None = None,
    villain_position: str | None = None,
    profile: ProfileName = DEFAULT_PROFILE_NAME,
) -> str:
    """
    Higher-level HU helper for postflop villain ranges.

    This is the API the postflop coach should prefer going forward. It is
    designed to accept richer context (preflop line, positions, profile)
    without pulling in DecisionContext or configuration modules.

    Args:
        street:
            Current street name; case-insensitive. Expected values are
            "flop", "turn", or "river". Unknown streets fall back to
            "flop".

        hero_is_ip:
            True if hero is in position postflop (acts after villain),
            False if hero is out of position.

        preflop_line:
            Optional abstract label for the preflop action sequence,
            e.g. "BTN_RFI_BB_call" or "BTN_RFI_BB_3B_BTN_call".
            Currently unused, but reserved so that future versions can
            condition villain ranges on the exact preflop path.

        hero_position:
            Optional textual position label for the hero ("BTN", "SB",
            "BB", etc.). Currently unused here, but included so callers
            can pass a consistent context without changing the API.

        villain_position:
            Optional textual position label for the villain. Also
            reserved for future refinements.

        profile:
            Villain profile name; currently only "TAG" is supported.

    Returns:
        A range string in the equity engine's native syntax.

    Current behaviour (v1):
        - Infer villain role from hero_is_ip:
            * hero_is_ip = True  -> villain is OOP
            * hero_is_ip = False -> villain is IP
        - Delegate to get_hu_villain_range(...) with that role.
        - Ignore preflop_line / positions for now.

    This keeps current semantics identical to the old helpers, while
    allowing future implementations to become more expressive without
    having to change call sites.
    """
    street_key: StreetKey = normalize_street_key(street)

    # If hero is in position, villain is OOP; otherwise villain is IP.
    villain_role: Role = "oop" if hero_is_ip else "ip"

    return get_hu_villain_range(
        street=street_key,
        role=villain_role,
        profile=profile,
    )


__all__ = [
    "DEFAULT_PROFILE_NAME",
    "ProfileName",
    "Role",
    "StreetKey",
    "GENERIC_SEMITIGHT_DEFAULT_RANGE",
    "normalize_street_key",
    "available_profiles",
    "get_hu_villain_range",
    "get_default_villain_range",
    "get_villain_range_for_postflop",
]
