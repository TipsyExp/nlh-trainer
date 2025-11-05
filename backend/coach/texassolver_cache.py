# backend/coach/texassolver_cache.py
from __future__ import annotations
import os
from typing import Dict, Tuple
from backend.adapters.solver.texassolver_adapter import TexasSolverAdapter, SolveRequest, AdvicePayload

# naive in-memory cache (per-process)
_CACHE: Dict[Tuple, AdvicePayload] = {}

def _cache_key(req: SolveRequest) -> Tuple:
    # Include env-driven knobs so changes produce a different entry
    threads = os.getenv("COACH_TS_THREADS", "1")
    acc     = os.getenv("COACH_TS_ACCURACY", "1.0")
    iters   = os.getenv("COACH_TS_MAX_ITERS", "200")

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
    key = _cache_key(req)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    advice = adapter.solve(req)
    _CACHE[key] = advice
    return advice
