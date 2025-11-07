from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pytest

from backend.coach.cache import SolverCache
from backend.coach import cache as cache_mod
from backend.coach.texassolver_cache import resolve_with_cache
from backend.coach.node_key import make_node_key_from_solve_request
from backend.adapters.solver.texassolver_adapter import SolveRequest
from backend.logger import get_logger


def test_cache_set_get_roundtrip() -> None:
    c = SolverCache()
    key = "unit:test:key:001"
    payload = '{"advice":"stub"}'
    c.set(key, payload)
    assert c.get(key) == payload


def test_put_get_cached_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure reasonable defaults
    monkeypatch.setenv("COACH_CACHE_TTL_DAYS", "30")
    c = SolverCache()
    key = "unit:test:key:json:001"
    payload: Dict[str, Any] = {"recommended_bucket": "A", "strategy": {"A": 1.0}}
    c.put_cached(key, payload)
    got = c.get_cached(key)
    assert got is not None
    assert got.get("recommended_bucket") == "A"


def test_cache_ttl_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COACH_CACHE_TTL_DAYS", "1")
    c = SolverCache()

    key = "unit:test:key:ttl:001"
    payload = {"v": 1}
    c.put_cached(key, payload)

    # Backdate created_at beyond TTL
    conn = c._conn  # type: ignore[attr-defined]
    old_ts = (
        (datetime.now(timezone.utc) - timedelta(days=3))
        .replace(microsecond=0)
        .isoformat()
    )
    conn.execute(
        "UPDATE solver_cache SET created_at = ? WHERE node_key = ?", (old_ts, key)
    )
    conn.commit()

    assert c.get_cached(key) is None, "expired rows should be treated as cache miss"


def test_cache_lru_prune(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COACH_CACHE_MAX_ROWS", "3")
    monkeypatch.setenv("COACH_CACHE_TTL_DAYS", "30")
    c = SolverCache()

    # Insert 5 rows
    for i in range(5):
        c.put_cached(f"key:{i}", {"i": i})
    # Enforce prune
    deleted = c.prune()

    # Count rows
    conn = c._conn  # type: ignore[attr-defined]
    n = conn.execute("SELECT COUNT(*) FROM solver_cache").fetchone()[0]
    assert n == 3
    assert deleted >= 2


# ---------------- Read-through wrapper tests (mock adapter) ----------------


def _reset_cache_singleton() -> None:
    # Ensure the module-level singleton picks up new env in each test
    try:
        cache_mod._CACHE_SINGLETON = None
    except Exception:
        pass


def test_resolve_with_cache_read_through(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_cache_singleton()
    monkeypatch.setenv("COACH_CACHE_TTL_DAYS", "30")
    monkeypatch.setenv("COACH_CACHE_MAX_ROWS", "5000")

    # Stub the adapter's solve to count calls
    calls = {"n": 0}

    def fake_solve(self, req):  # type: ignore[no-redef]
        calls["n"] += 1
        return {"recommended_bucket": "X", "strategy": {"X": 1.0}, "ev_map": {"X": 0.0}}

    monkeypatch.setattr(
        "backend.adapters.solver.texassolver_adapter.TexasSolverAdapter.solve",
        fake_solve,
        raising=True,
    )

    req = SolveRequest(
        street="flop",
        board=["Ah", "Kd", "3s"],
        pot=100,
        ip_stack=200,
        oop_stack=200,
        ip_range="AA,AKs",
        oop_range="KK,QQ",
        bucket_labels=["TOP", "MID", "LOW"],
        spot="SRP",
    )

    # Ensure clean slate for this node
    nk = make_node_key_from_solve_request(req)
    conn = get_logger().conn
    conn.execute("DELETE FROM solver_cache WHERE node_key = ?", (nk,))
    conn.commit()

    payload1, cached1, node_key1 = resolve_with_cache(req)
    payload2, cached2, node_key2 = resolve_with_cache(req)

    assert calls["n"] == 1, "adapter.solve should be called only on the miss"
    assert cached1 is False and cached2 is True
    assert (
        node_key1 == node_key2 and isinstance(node_key1, str) and len(node_key1) == 64
    )
    assert payload1["recommended_bucket"] == "X"


def test_resolve_with_cache_ttl_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_cache_singleton()
    monkeypatch.setenv("COACH_CACHE_TTL_DAYS", "1")
    monkeypatch.setenv("COACH_CACHE_MAX_ROWS", "5000")

    calls = {"n": 0}

    def fake_solve(self, req):
        calls["n"] += 1
        return {"recommended_bucket": "R", "strategy": {"R": 1.0}, "ev_map": {"R": 0.0}}

    monkeypatch.setattr(
        "backend.adapters.solver.texassolver_adapter.TexasSolverAdapter.solve",
        fake_solve,
        raising=True,
    )

    req = SolveRequest(
        street="flop",
        board=["2c", "7d", "Jh"],
        pot=60,
        ip_stack=180,
        oop_stack=220,
        ip_range="A2s+",
        oop_range="K9o+",
        bucket_labels=["B1", "B2"],
        spot="SRP",
    )

    # First resolve -> miss and store
    payload, cached, nk = resolve_with_cache(req)
    assert cached is False

    # Backdate created_at beyond TTL
    conn = get_logger().conn
    old_ts = (
        (datetime.now(timezone.utc) - timedelta(days=5))
        .replace(microsecond=0)
        .isoformat()
    )
    conn.execute(
        "UPDATE solver_cache SET created_at = ? WHERE node_key = ?", (old_ts, nk)
    )
    conn.commit()

    # Second resolve should expire and re-solve
    payload2, cached2, nk2 = resolve_with_cache(req)
    assert cached2 is False
    assert calls["n"] == 2
    assert nk == nk2
