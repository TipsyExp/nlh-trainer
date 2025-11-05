from __future__ import annotations

from backend.coach.cache import SolverCache


def test_cache_set_get_roundtrip() -> None:
    c = SolverCache()
    key = "unit:test:key:001"
    payload = '{"advice":"stub"}'
    c.set(key, payload)
    assert c.get(key) == payload
