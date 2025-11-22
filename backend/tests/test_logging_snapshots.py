# backend/tests/test_logging_snapshots.py
"""
Tests for backend.logger snapshot helpers.

Focus:

    * Column creation / wiring for coach_advice_json.
    * LOG_COACH_ADVICE gating in log_coach_advice().
    * Basic behaviour of equity / preflop helpers (no crash, JSON stored).

These tests deliberately avoid touching the full engine / export layer;
they operate directly on the logger module and a small test table,
patched in via _find_snapshot_table.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

import pytest

from backend import logger as logger_mod


def _init_test_logger(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Tuple[Any, Any]:
    """
    Initialise the singleton logger against an isolated SQLite file and
    return (logger, conn).

    This does not depend on the engine schema; tests create their own
    table and patch _find_snapshot_table to point at it.

    Using monkeypatch.setenv for LOG_DB_PATH ensures that subsequent
    calls to get_logger() do not reinitialise the logger with a different
    path (which would close the original connection).
    """
    db_path = tmp_path / "logging_snapshots.sqlite"

    # Ensure the logger points at our temp DB and is freshly initialised.
    monkeypatch.setenv("LOG_DB_PATH", str(db_path))
    logger_mod.reset_logger()
    logger = logger_mod.get_logger()

    conn = getattr(logger, "conn", None)
    assert conn is not None, "SQLiteLogger should expose a .conn handle in tests"

    return logger, conn


def _setup_snapshot_table(conn: Any) -> str:
    """
    Create a simple test table that satisfies the logger's expectations.

    Returns the table name ("snapshots").
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            hand_id TEXT,
            idx INTEGER,
            equity_snapshot_json TEXT,
            preflop_advice_json TEXT,
            coach_advice_json TEXT
        )
        """
    )
    conn.commit()
    return "snapshots"


def test_log_coach_advice_writes_payload_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    When LOG_COACH_ADVICE is true, log_coach_advice() should serialize the
    payload and update coach_advice_json for the matching (hand_id, idx)
    row in the snapshot table.
    """
    _, conn = _init_test_logger(monkeypatch, tmp_path)
    table = _setup_snapshot_table(conn)

    # Ensure the logger targets our test table, not any engine table.
    monkeypatch.setattr(
        logger_mod,
        "_find_snapshot_table",
        lambda c: table,
        raising=True,
    )

    # Enable coach advice logging (override any env-derived defaults).
    monkeypatch.setattr(logger_mod, "LOG_COACH_ADVICE", True, raising=False)

    hand_id = "H123"
    idx = 0

    # Seed a row for the UPDATE to hit.
    conn.execute(
        f"INSERT INTO {table} (hand_id, idx) VALUES (?, ?)",
        (hand_id, idx),
    )
    conn.commit()

    # Sanity: no payload stored yet.
    cur = conn.execute(
        f"SELECT coach_advice_json FROM {table} WHERE hand_id = ? AND idx = ?",
        (hand_id, idx),
    )
    row = cur.fetchone()
    assert row is not None
    assert row[0] is None

    # Minimal AdviceV1-like payload.
    sample_advice: Dict[str, Any] = {
        "version": 1,
        "status": "ok",
        "meta": {
            "street": "preflop",
            "n_players": 2,
            "hero_seat": 0,
            "source": "chart",
        },
        "recommendation": {
            "bucket": "2.5x",
            "strategy_bar": [
                {"action": "2.5x", "weight": 1.0},
            ],
        },
        "equity": None,
        "thresholds": None,
        "rationale": "stub advice",
    }

    # Call the helper under test.
    logger_mod.log_coach_advice(hand_id=hand_id, idx=idx, advice=sample_advice)

    # Verify the payload was written.
    cur = conn.execute(
        f"SELECT coach_advice_json FROM {table} WHERE hand_id = ? AND idx = ?",
        (hand_id, idx),
    )
    row = cur.fetchone()
    assert row is not None
    assert isinstance(row[0], str)

    stored_obj = json.loads(row[0])
    assert stored_obj == sample_advice


def test_log_coach_advice_noop_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    When LOG_COACH_ADVICE is false, log_coach_advice() should be a no-op:
    it must not crash and must not mutate coach_advice_json.
    """
    _, conn = _init_test_logger(monkeypatch, tmp_path)
    table = _setup_snapshot_table(conn)

    monkeypatch.setattr(
        logger_mod,
        "_find_snapshot_table",
        lambda c: table,
        raising=True,
    )
    # Explicitly disable coach advice logging.
    monkeypatch.setattr(logger_mod, "LOG_COACH_ADVICE", False, raising=False)

    hand_id = "H999"
    idx = 3

    # Seed a row with a sentinel value.
    sentinel = '{"existing":"value"}'
    conn.execute(
        f"INSERT INTO {table} (hand_id, idx, coach_advice_json) " "VALUES (?, ?, ?)",
        (hand_id, idx, sentinel),
    )
    conn.commit()

    logger_mod.log_coach_advice(
        hand_id=hand_id,
        idx=idx,
        advice={"version": 1, "status": "ok"},
    )

    # The sentinel should remain unchanged.
    cur = conn.execute(
        f"SELECT coach_advice_json FROM {table} WHERE hand_id = ? AND idx = ?",
        (hand_id, idx),
    )
    row = cur.fetchone()
    assert row is not None
    assert row[0] == sentinel


def test_log_equity_snapshot_and_preflop_advice_share_same_table(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    Sanity check: equity and preflop helpers also write into the same
    snapshot table and honour their respective flags.
    """
    _, conn = _init_test_logger(monkeypatch, tmp_path)
    table = _setup_snapshot_table(conn)

    monkeypatch.setattr(
        logger_mod,
        "_find_snapshot_table",
        lambda c: table,
        raising=True,
    )

    # Enable both logging flags for this test.
    monkeypatch.setattr(logger_mod, "LOG_EQUITY_SNAPSHOT", True, raising=False)
    monkeypatch.setattr(logger_mod, "LOG_PREFLOP_ADVICE", True, raising=False)
    # For equity, ensure no redaction for easier comparison.
    monkeypatch.setattr(
        logger_mod,
        "LOG_EQUITY_SNAPSHOT_REDACT",
        False,
        raising=False,
    )

    hand_id = "H777"
    idx = 1

    # Seed a row for UPDATEs.
    conn.execute(
        f"INSERT INTO {table} (hand_id, idx) VALUES (?, ?)",
        (hand_id, idx),
    )
    conn.commit()

    equity_snapshot: Dict[str, Any] = {
        "backend": "ompeval",
        "mode": "hands",
        "board": [],
        "dead": [],
        "players": [
            {"seat": 0, "equity": 0.6},
            {"seat": 1, "equity": 0.4},
        ],
        "raw": {"iters": 20000},
    }

    preflop_advice: Dict[str, Any] = {
        "source": "chart",
        "bucket": "2.5x",
        "rationale": "stub rationale",
        "strategy_bar": {"2.5x": 1.0},
    }

    # Call helpers under test.
    logger_mod.log_equity_snapshot(hand_id=hand_id, idx=idx, snapshot=equity_snapshot)
    logger_mod.log_preflop_advice(hand_id=hand_id, idx=idx, advice=preflop_advice)

    cur = conn.execute(
        f"""
        SELECT equity_snapshot_json, preflop_advice_json
        FROM {table}
        WHERE hand_id = ? AND idx = ?
        """,
        (hand_id, idx),
    )
    row = cur.fetchone()
    assert row is not None

    eq_json, adv_json = row
    assert isinstance(eq_json, str)
    assert isinstance(adv_json, str)

    stored_eq = json.loads(eq_json)
    stored_adv = json.loads(adv_json)

    # Both helpers should have stored JSON objects matching our input.
    # (Equity snapshot redaction is disabled for this test.)
    assert stored_eq == equity_snapshot
    assert stored_adv == preflop_advice
