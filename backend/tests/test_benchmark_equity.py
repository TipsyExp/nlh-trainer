# backend/tests/test_benchmark_equity.py
from __future__ import annotations

import csv
import io
from typing import Any, Dict, List

from backend.scripts import benchmark_equity as bench_mod
from backend.services.equity.base import PlayerSpec


def _small_scenarios() -> List[Dict[str, Any]]:
    """
    Tiny benchmark scenarios for tests.

    These deliberately use much smaller iters than the CLI defaults so the
    test suite stays fast, while still exercising the same code paths.
    """
    return [
        {
            "name": "hu_hands_small",
            "players": [
                PlayerSpec(hand=("Ah", "Ad")),
                PlayerSpec(hand=("Kh", "Qh")),
            ],
            "board": [],
            "dead": [],
            "exact": False,
            "iters": 500,
        },
        {
            "name": "hu_ranges_small",
            "players": [
                PlayerSpec(range="JJ+"),
                PlayerSpec(range="random"),
            ],
            "board": [],
            "dead": [],
            "exact": False,
            "iters": 500,
        },
    ]


def _read_csv_rows(buf: io.StringIO) -> List[Dict[str, str]]:
    buf.seek(0)
    reader = csv.DictReader(buf.getvalue().splitlines())
    return list(reader)


def test_benchmark_equity_basic_csv_contract() -> None:
    """
    run_matrix should emit a CSV with sensible, non-empty rows and the
    expected columns when run with a tiny matrix and a single policy.

    We only exercise policy="auto" here so the test passes even when
    optional backends (pbots, Henry) are not installed.
    """
    scenarios = _small_scenarios()
    policies = ["auto"]

    buf = io.StringIO()
    bench_mod.run_matrix(policies, scenarios, buf)

    rows = _read_csv_rows(buf)
    # One row per (policy, scenario)
    assert len(rows) >= len(scenarios)

    required_fields = {
        "scenario",
        "policy",
        "status",
        "backend",
        "mode",
        "n_players",
        "board_len",
        "exact",
        "iters",
        "samples",
        "elapsed_ms",
        "evals_per_sec",
        "eq_sum",
        "equities",
    }

    # Contract: each row has the required fields
    for row in rows:
        assert required_fields.issubset(
            row.keys()
        ), f"missing fields in row: {row.keys()}"

    # At least one scenario should complete successfully under policy=auto.
    ok_rows = [r for r in rows if r.get("status") == "ok"]
    assert ok_rows, "expected at least one successful benchmark row"

    for row in ok_rows:
        # Basic numeric sanity checks
        elapsed_ms = float(row["elapsed_ms"])
        assert elapsed_ms >= 0.0

        n_players = int(row["n_players"])
        assert n_players >= 2

        samples = int(row["samples"]) if row.get("samples") else 0
        assert samples >= 0

        evals_per_sec = float(row["evals_per_sec"])
        # With samples > 0 and non-zero time, we expect a positive rate.
        if samples > 0 and elapsed_ms > 0.0:
            assert evals_per_sec > 0.0

        # Equities: sum should be in a reasonable range when present.
        if row.get("eq_sum") not in ("", None):
            eq_sum = float(row["eq_sum"])
            assert 0.0 <= eq_sum <= float(n_players)


def test_benchmark_equity_handles_missing_backends() -> None:
    """
    run_matrix must not crash even when a forced policy (e.g. 'pbots')
    refers to an optional backend that isn't available.

    Instead, the script should record status='error' with a message and
    continue emitting CSV rows.
    """
    scenarios = _small_scenarios()
    policies = ["pbots"]

    buf = io.StringIO()
    # Should not raise even if pbots_calc / Henry are missing.
    bench_mod.run_matrix(policies, scenarios, buf)

    rows = _read_csv_rows(buf)
    # One row per scenario for this policy
    assert len(rows) == len(scenarios)

    for row in rows:
        assert row["policy"] == "pbots"
        # We tolerate either 'ok' (if pbots is installed) or 'error'
        # (if pbots is unavailable); the key contract is that the run
        # completes and emits rows.
        assert row["status"] in {"ok", "error"}
        if row["status"] == "error":
            # Expect a non-empty error message for diagnostic value.
            assert row.get("error"), "missing error message for failing row"
