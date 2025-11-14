# backend/coach/preflop/ranges.py
"""Static preflop range helpers for the chart/equity advisor.

This module centralises:
  - Default villain ranges per preflop node (HU-only for now).
  - A tiny helper to turn a hand_key (e.g. "AJo") into a pbots-style
    range string suitable for use as a hero input.

Keeping these here avoids hard-coding ranges and parsing logic inside
the advisor service itself.
"""

from __future__ import annotations

from typing import Dict

RangeString = str

# ---------------------------------------------------------------------------
# Node identifiers (HU-only, minimal for now)
# ---------------------------------------------------------------------------

# Hero = SB, opening pot preflop.
NODE_SB_OPEN = "sb_open"

# Hero = BB, facing a small-blind open.
NODE_BB_VS_SB_OPEN = "bb_vs_sb_open"

# Generic HU fallback node identifier (used when we don't have a more
# specific node; may be expanded or removed later as wiring improves).
NODE_HU_GENERIC = "hu_generic"

# ---------------------------------------------------------------------------
# Default villain ranges (pbots syntax, HU-only, coarse approximations)
# ---------------------------------------------------------------------------

# Baseline HU opening/defending range. This is intentionally coarse and
# should be treated as an assumption for dev/analysis only, not a GTO spec.
_DEFAULT_HU_VILLAIN_RANGE: RangeString = "22+,A2s+,K9s+,QTs+,JTs,A9o+,KJo+,QJo"

# Node-specific overrides. All strings are pbots_calc-style ranges.
_DEFAULT_VILLAIN_RANGES: Dict[str, RangeString] = {
    # When hero is BB vs SB open, we assume villain (SB) opens roughly this range.
    NODE_BB_VS_SB_OPEN: _DEFAULT_HU_VILLAIN_RANGE,
    # Generic HU fallback: same as baseline unless refined later.
    NODE_HU_GENERIC: _DEFAULT_HU_VILLAIN_RANGE,
    # For sb_open, we rarely need a villain range for fallback in this phase;
    # use the same baseline if required.
    NODE_SB_OPEN: _DEFAULT_HU_VILLAIN_RANGE,
}


def get_default_villain_range(node: str) -> RangeString:
    """
    Return a default villain range (pbots syntax) for a given preflop node.

    The intent is to provide a simple, documented assumption for equity-based
    fallback decisions in the preflop advisor. Ranges are HU-only, coarse,
    and chosen for robustness rather than theoretical accuracy.

    If the node is unknown, falls back to a generic HU baseline.
    """
    node = (node or "").strip().lower()
    return _DEFAULT_VILLAIN_RANGES.get(node, _DEFAULT_HU_VILLAIN_RANGE)


def hero_hand_key_to_range(hand_key: str) -> RangeString:
    """
    Convert a chart/engine hand key into a pbots-compatible hero range string.

    Examples:
      - "AJo"   -> "AJo"
      - "AJs"   -> "AJs"
      - "AKO"   -> "AKo"
      - "jj"    -> "JJ"
      - "T9s"   -> "T9s"

    Behaviour:
      - Strips whitespace and normalises ranks to uppercase.
      - Keeps/normalises a trailing 's' or 'o' (case-insensitive).
      - Returns the original cleaned key if it doesn't match the expected
        pattern; the equity backend may still accept it or raise.

    This helper does not attempt to expand the hand into individual combos;
    it returns a shorthand that pbots_calc is expected to understand.
    """
    key = (hand_key or "").strip()
    if not key:
        return key

    # Normalise basic shape: ranks uppercase, optional last-char s/o lower.
    key_up = key.upper()
    if len(key_up) >= 3 and key_up[-1] in {"S", "O"}:
        return key_up[:-1] + key_up[-1].lower()

    return key_up
