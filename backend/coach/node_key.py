from __future__ import annotations

from typing import Iterable, List


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
