from __future__ import annotations

import hashlib
import json
from typing import Iterable, List

# NOTE:
# - `make_node_key(...)` is the pre-existing, human-readable key used elsewhere.
# - Task-18 adds `make_node_key_from_solve_request(req)` which returns a compact
#   SHA-256 hex digest over a canonical JSON blob constructed from a SolveRequest.
#   This key is stable and order-insensitive for board/bucket labels.


def _round3(x: float) -> str:
    # Compact 3dp rounding (strip trailing zeros/dot)
    s = f"{x:.3f}"
    return s.rstrip("0").rstrip(".")


def make_node_key(
    *,
    street: str,
    pot: int,
    board: Iterable[str],
    ip: bool,
    pot_type: str,
    stp: float,
    bucket_slice: str,
) -> str:
    """
    Deterministic, public-only key. Board ordering and case-insensitive.
    """
    s = street.lower()
    pt = pot_type.upper()
    b: List[str] = sorted(str(c).upper() for c in board)
    ip_s = "IP" if ip else "OOP"
    stp_s = _round3(stp)
    return "|".join([s, str(pot), "".join(b), ip_s, pt, stp_s, bucket_slice])


# ------------------- Task-18: request-based node key -------------------


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_board(board: Iterable[str]) -> str:
    # Uppercase and lexicographically sort, then join (e.g., ['Ah','7d','7s'] -> '7DAH7S')
    cards = [str(c).upper() for c in board]
    cards.sort()
    return "".join(cards)


def _canonical_bucket_labels(labels: Iterable[str]) -> List[str]:
    # Sort for stability unless order has semantic meaning. We choose to sort
    # and document it for deterministic keys across callers.
    return sorted(str(x) for x in labels)


def make_node_key_from_solve_request(req) -> str:
    """Return a stable, compact node_key for caching (SHA-256 hex).

    Canonical JSON includes:
      - street (lowercased)
      - board (uppercase, sorted, joined)
      - pot (as int if possible)
      - ip_stack, oop_stack
      - spot (string)
      - bucket_labels (sorted list for stability)
      - ranges: SHA-256 of ip_range and oop_range to keep key compact

    The entire canonical dict is then JSON-serialized with sorted keys and
    compact separators and hashed again with SHA-256. This ensures small,
    order-insensitive, and portable keys.
    """
    # Pull fields with safe normalization
    street = str(getattr(req, "street", "")).lower()
    board = _canonical_board(getattr(req, "board", []))

    pot_val = getattr(req, "pot", 0)
    try:
        pot = int(pot_val)
    except Exception:
        # If float or non-int convertible, fallback to string representation
        pot = int(float(pot_val)) if isinstance(pot_val, (float, str)) else 0

    ip_stack = getattr(req, "ip_stack", 0)
    oop_stack = getattr(req, "oop_stack", 0)
    spot = str(getattr(req, "spot", ""))

    labels = _canonical_bucket_labels(getattr(req, "bucket_labels", []))

    ip_range = str(getattr(req, "ip_range", ""))
    oop_range = str(getattr(req, "oop_range", ""))
    ranges = {
        "ip": _sha256_hex(ip_range),
        "oop": _sha256_hex(oop_range),
    }

    canonical = {
        "street": street,
        "board": board,
        "pot": pot,
        "ip_stack": ip_stack,
        "oop_stack": oop_stack,
        "spot": spot,
        "bucket_labels": labels,
        "ranges": ranges,
    }

    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return _sha256_hex(blob)
