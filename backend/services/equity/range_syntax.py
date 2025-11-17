# backend/services/equity/range_syntax.py
"""
Range syntax normalization shim.

Purpose
-------
Normalize loosely-typed PokerStove-style input strings into a consistent,
backend-friendly syntax. OMPEval expects an Equilab-like grammar (very
close to PokerStove), while eval7 parses PokerStove-like strings and
optionally supports weights. To keep things simple and portable:

- We accept common user inputs (mixed case, spaces, semicolons).
- We normalize casing and separators.
- We map synonyms like "xx" / "random" / "any" -> "random".
- For OMPEval targets, we STRIP weights (e.g. "0.5(AKo)" -> "AKo").
- For eval7 targets, we KEEP the original weights.

This module does not attempt full validation or expansion of ranges; it
performs conservative normalization and leaves parsing/validation to the
backend libraries.

Examples
--------
normalize_range(" AJo ,  KQs  , 88+ ") -> "AJo,KQs,88+"
normalize_range("xx, 0.5(AKo)", backend="ompeval") -> "random,AKo"
normalize_range("xx, 0.5(AKo)", backend="eval7")   -> "random,0.5(AKo)"

Notes
-----
- Both Equilab and PokerStove accept ',' as range separators. We normalize
  any whitespace/semicolon separators to comma.
- Suited/offsuit suffixes are normalized to lowercase ('s'/'o').
- Card ranks are normalized to uppercase.
"""
from __future__ import annotations

from typing import Iterable, List, Optional
import re

# Accept either PokerStove/Equilab-like tokens and simple weights.
_WEIGHT_RE = re.compile(r"^\s*(?P<w>\d*\.?\d+)\s*\((?P<body>.+)\)\s*$")
_SEP_RE = re.compile(r"[;\s]+")

# Basic validation of rank/suit letters; we don't strictly validate the entire
# grammar here, just normalize.
_RANKS = set("23456789TJQKA")
_SO_SUFFIX = {"S", "O", "s", "o"}


def _strip_outer_whitespace(s: str) -> str:
    return s.strip()


def _is_random(tok: str) -> bool:
    t = tok.strip().lower()
    return t in {"xx", "random", "any"}


def _normalize_token_casing(tok: str) -> str:
    """
    Normalize rank casing (uppercase) and suited/offsuit suffix (lowercase).
    Leave operators like '+', '-' untouched.
    """
    t = tok.strip()
    if not t:
        return t

    # common aliases
    if _is_random(t):
        return "random"

    # Fast path for weighted tokens (handled elsewhere)
    if _WEIGHT_RE.match(t):
        return t  # keep as-is; caller decides to strip or keep weights

    # Normalize letter casing inside the token: ranks uppercase, 's'/'o' lowercase.
    # We do not attempt to validate complex syntaxes here.
    out = []
    for ch in t:
        if ch.upper() in _RANKS:
            out.append(ch.upper())
        elif ch in "+-,":
            out.append(ch)
        elif ch in _SO_SUFFIX:
            out.append(ch.lower())
        else:
            out.append(ch)
    return "".join(out)


def _split_to_tokens(s: str) -> List[str]:
    """
    Split a user range string into tokens using comma as the canonical separator.
    We also accept whitespace or semicolons as separators and normalize them.
    """
    if not s:
        return []
    # Normalize all non-comma separators to spaces, then split, then join via commas.
    s = s.replace(",", " , ")
    s = _SEP_RE.sub(" ", s)
    parts = [p for p in s.split() if p != ","]
    # Now re-split by commas explicitly to preserve intended grouping.
    joined = ",".join(parts)
    tokens = [t for t in (t.strip() for t in joined.split(",")) if t]
    return tokens


def _strip_weights(tok: str) -> str:
    """
    If token is a weighted expression like '0.5(AKo)', return the body 'AKo'.
    Otherwise return the token unchanged.
    """
    m = _WEIGHT_RE.match(tok)
    if not m:
        return tok
    return m.group("body").strip()


def _normalize_for_ompeval(tokens: Iterable[str]) -> List[str]:
    """
    OMPEval does not support weights; we strip them and normalize casing/synonyms.
    """
    out: List[str] = []
    for t in tokens:
        t = _normalize_token_casing(t)
        if _is_random(t):
            out.append("random")
            continue
        # Strip weights like 0.6(XX) -> XX
        t = _strip_weights(t)
        t = _normalize_token_casing(t)
        if t:
            out.append(t)
    return out


def _normalize_for_eval7(tokens: Iterable[str]) -> List[str]:
    """
    eval7 supports PokerStove-style weights; we keep weighted tokens intact.
    We still normalize random synonyms and casing.
    """
    out: List[str] = []
    for t in tokens:
        if _is_random(t):
            out.append("random")
            continue
        t = _normalize_token_casing(t)
        out.append(t)
    return out


def normalize_range(s: str, backend: Optional[str] = None) -> str:
    """
    Normalize a user-supplied range string for the specified backend.

    Args:
        s: Input range string (PokerStove/Equilab-like).
        backend: One of {"ompeval", "eval7"} or None.
                 If None, apply backend-agnostic normalization (weights preserved).

    Returns:
        Comma-separated, normalized range string.
    """
    s = _strip_outer_whitespace(s or "")
    if not s:
        return s

    tokens = _split_to_tokens(s)

    if backend == "ompeval":
        norm = _normalize_for_ompeval(tokens)
    elif backend == "eval7" or backend is None:
        # Default path keeps weights to be more permissive.
        norm = _normalize_for_eval7(tokens)
    else:
        # Unknown backend: do a safe generic normalization (keep tokens).
        norm = _normalize_for_eval7(tokens)

    # Deduplicate while preserving order
    seen = set()
    out: List[str] = []
    for t in norm:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return ",".join(out)


__all__ = ["normalize_range"]
