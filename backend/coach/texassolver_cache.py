# backend/coach/texassolver_cache.py
from __future__ import annotations

import os
from typing import Any, Dict, Tuple

from backend.adapters.solver.texassolver_adapter import (
    TexasSolverAdapter,
    SolveRequest,
    AdvicePayload,
)
from backend.coach.cache import (
    get_cached as cache_get,
    put_cached as cache_put,
    prune as cache_prune,
)
from backend.coach.node_key import make_node_key_from_solve_request

# Task-17: naïve in-memory cache (per-process) kept for back-compat
_CACHE: Dict[Tuple, AdvicePayload] = {}


def _cache_key(req: SolveRequest) -> Tuple:
    """Legacy in-memory cache key (process-local)."""
    # Include env-driven knobs so changes produce a different entry
    threads = os.getenv("COACH_TS_THREADS", "1")
    acc = os.getenv("COACH_TS_ACCURACY", "1.0")
    iters = os.getenv("COACH_TS_MAX_ITERS", "200")

    return (
        req.street,
        tuple(req.board),
        req.pot,
        min(req.ip_stack, req.oop_stack),
        req.ip_range,
        req.oop_range,
        tuple(sorted(req.bucket_labels, key=str)),
        req.spot,
        f"t={threads}",
        f"a={acc}",
        f"i={iters}",
    )


def get_advice_cached(adapter: TexasSolverAdapter, req: SolveRequest) -> AdvicePayload:
    """Legacy helper: process-local cache around adapter.solve(req).
    Kept to avoid breaking callers until API layer is switched to resolve_with_cache.
    """
    key = _cache_key(req)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    advice = adapter.solve(req)
    _CACHE[key] = advice
    return advice


# ---------------- Task-18: SQLite-backed read-through cache ----------------


def resolve_with_cache(req: SolveRequest) -> tuple[Dict[str, Any], bool, str]:
    """Resolve advice with a persistent (SQLite) read-through cache.

    Returns: (payload_dict, cached_flag, node_key)
    - payload_dict: advice payload as a plain dict
    - cached_flag: True if returned from cache; False if freshly solved
    - node_key: stable node key (sha256 hex) derived from the SolveRequest
    """
    node_key = make_node_key_from_solve_request(req)

    # 1) Attempt TTL-aware cache read
    cached = cache_get(node_key)
    if cached is not None:
        # Ensure mapping type
        return dict(cached), True, node_key

    # 2) Miss/expired -> solve via adapter
    adapter = TexasSolverAdapter()
    advice = adapter.solve(req)
    payload: Dict[str, Any] = dict(advice)

    # 3) Write-through & prune (best-effort; failures shouldn't break response)
    try:
        cache_put(node_key, payload)
        cache_prune()
    except Exception:
        # Intentionally swallow cache store errors to keep request successful
        pass

    return payload, False, node_key


__all__ = [
    "get_advice_cached",
    "resolve_with_cache",
]
