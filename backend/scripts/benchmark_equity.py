# backend/scripts/benchmark_equity.py
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence  # <- removed Tuple

from backend.services.equity.base import Card, EquityResult, PlayerSpec
from backend.services.equity.service import EquityService


def _scenarios() -> List[Dict[str, Any]]:
    """
    Define a tiny matrix of benchmark scenarios.

    These are intentionally small so they are safe to run locally or in CI.
    They cover:
      - HU fixed hands (preflop MC).
      - HU fixed hands (flop exact).
      - HU fixed hands (flop MC) -> compared vs exact to compute err.
      - HU ranges (preflop MC).
      - 3-way ranges (preflop MC).
    """
    return [
        {
            "name": "hu_hands_preflop",
            "players": [
                PlayerSpec(hand=("Ah", "Ad")),
                PlayerSpec(hand=("Kh", "Qh")),
            ],
            "board": [],
            "dead": [],
            "exact": False,
            "iters": 10_000,
        },
        {
            "name": "hu_hands_flop_exact",
            "players": [
                PlayerSpec(hand=("Ah", "Ad")),
                PlayerSpec(hand=("Kh", "Qh")),
            ],
            "board": ["As", "Kd", "2c"],
            "dead": [],
            "exact": True,
            "iters": None,
        },
        {
            # Same as the exact flop case, but MC to estimate error vs exact
            "name": "hu_hands_flop_mc",
            "players": [
                PlayerSpec(hand=("Ah", "Ad")),
                PlayerSpec(hand=("Kh", "Qh")),
            ],
            "board": ["As", "Kd", "2c"],
            "dead": [],
            "exact": False,
            "iters": 20_000,
        },
        {
            "name": "hu_ranges_preflop",
            "players": [
                PlayerSpec(range="JJ+"),
                PlayerSpec(range="random"),
            ],
            "board": [],
            "dead": [],
            "exact": False,
            "iters": 20_000,
        },
        {
            "name": "three_way_ranges_preflop",
            "players": [
                PlayerSpec(range="JJ+"),
                PlayerSpec(range="TT+"),
                PlayerSpec(range="random"),
            ],
            "board": [],
            "dead": [],
            "exact": False,
            "iters": 20_000,
        },
    ]


def _parse_policies(raw: Optional[str]) -> List[str]:
    if not raw:
        # Default matrix for CI/local: new stack (ompeval primary), plus fallbacks
        return ["auto", "ompeval", "eval7", "pokerkit"]
    parts = [p.strip().lower() for p in raw.split(",")]
    return [p for p in parts if p]


def _samples_from_result(res: EquityResult) -> int:
    """
    Best-effort extraction of 'samples' from an EquityResult.

    For OMPEval: prefer raw["iters"] (for MC), else res.iters.
    For Eval7:   raw["trials"] or res.iters.
    For PokerKit: raw["trials"] or res.iters.
    """
    if res.raw:
        for key in ("iters", "samples", "simulations", "trials"):
            v = res.raw.get(key)
            if isinstance(v, (int, float)):
                return int(v)
    if res.iters is not None:
        return int(res.iters)
    return 0


def _stderr_from_result(res: EquityResult) -> Optional[float]:
    if res.raw:
        v = res.raw.get("stderr") or res.raw.get("std_err")
        try:
            return float(v) if v is not None else None
        except Exception:
            return None
    return None


def _threads_from_result(res: EquityResult) -> Optional[int]:
    if res.raw:
        v = res.raw.get("threads")
        try:
            return int(v) if v is not None else None
        except Exception:
            return None
    return None


def _equities_from_result(res: EquityResult) -> List[float]:
    return [float(p.get("equity", 0.0)) for p in res.per_player]


def _backend_supports_ranges(
    svc: EquityService,
    backend_name: str,
) -> Optional[bool]:
    """
    Introspect the underlying backend capabilities where possible.

    Returns:
      True/False when we can find the backend and call supports_ranges().
      None if we can't determine it.
    """
    backends: Sequence[Any] = getattr(svc, "_backends", [])  # type: ignore[assignment]
    for b in backends:
        if getattr(b, "name", "") == backend_name:
            try:
                return bool(b.supports_ranges())  # type: ignore[no-untyped-call]
            except Exception:
                return None
    return None


def _mean_abs_err(a: Sequence[float], b: Sequence[float]) -> Optional[float]:
    if not a or not b or len(a) != len(b):
        return None
    return sum(abs(x - y) for x, y in zip(a, b)) / float(len(a))


def _compute_err_vs_exact(
    svc: EquityService,
    players: Sequence[PlayerSpec],
    board: Sequence[Card],
    dead: Sequence[Card],
    iters: Optional[int],
) -> Optional[float]:
    """
    For a small HU flop case, run an exact baseline and compare to MC equities.

    Returns mean absolute error across players, or None if exact is unavailable.
    """
    try:
        exact_res = svc.calc_equity(
            players=players,
            board=board,
            dead=dead,
            iters=None,
            exact=True,
            timeout_ms=None,
        )
        if not exact_res.exact:
            return None
        exact_eqs = _equities_from_result(exact_res)

        mc_res = svc.calc_equity(
            players=players,
            board=board,
            dead=dead,
            iters=iters or 20_000,
            exact=False,
            timeout_ms=None,
        )
        mc_eqs = _equities_from_result(mc_res)
        return _mean_abs_err(exact_eqs, mc_eqs)
    except Exception:
        return None


def run_matrix(
    policies: Iterable[str],
    scenarios: Iterable[Dict[str, Any]],
    csv_out,
) -> None:
    fieldnames = [
        "scenario",
        "policy",
        "status",
        "error",
        "backend",
        "mode",
        "supports_ranges",
        "n_players",
        "board_len",
        "exact",
        "iters",
        "samples",
        "stderr",
        "threads",
        "elapsed_ms",
        "evals_per_sec",
        "eq_sum",
        "equities",
        "err_vs_exact",
    ]
    writer = csv.DictWriter(csv_out, fieldnames=fieldnames)
    writer.writeheader()

    for policy in policies:
        policy = policy.strip().lower()
        if not policy:
            continue

        # Configure policy via environment for this EquityService instance.
        os.environ["EQUITY_BACKEND_POLICY"] = policy

        for sc in scenarios:
            scenario_name = sc["name"]
            players: Sequence[PlayerSpec] = sc["players"]
            board: Sequence[Card] = sc.get("board", [])
            dead: Sequence[Card] = sc.get("dead", [])
            exact: bool = bool(sc.get("exact", False))
            iters = sc.get("iters")

            svc = EquityService()

            started = time.perf_counter()
            status = "ok"
            err_msg = ""
            backend_name = ""
            mode = ""
            supports_ranges: Optional[bool] = None
            n_players = len(players)
            board_len = len(board)
            samples = 0
            equities: List[float] = []
            stderr_val: Optional[float] = None
            threads_val: Optional[int] = None
            err_vs_exact: Optional[float] = None

            try:
                res = svc.calc_equity(
                    players=players,
                    board=board,
                    dead=dead,
                    iters=iters,
                    exact=exact,
                    timeout_ms=None,
                )
                elapsed_ms = (time.perf_counter() - started) * 1000.0

                backend_name = res.backend
                mode = res.mode
                supports_ranges = _backend_supports_ranges(svc, backend_name)
                samples = _samples_from_result(res)
                equities = _equities_from_result(res)
                stderr_val = _stderr_from_result(res)
                threads_val = _threads_from_result(res)

                # Optional correctness probe: for the HU flop MC scenario,
                # compute mean absolute error vs exact (if exact is supported).
                if scenario_name == "hu_hands_flop_mc" and not exact:
                    err_vs_exact = _compute_err_vs_exact(
                        svc=svc,
                        players=players,
                        board=board,
                        dead=dead,
                        iters=iters,
                    )

            except Exception as e:
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                status = "error"
                err_msg = str(e)

            # Compute simple metrics
            eq_sum = sum(equities) if equities else 0.0
            elapsed_sec = elapsed_ms / 1000.0 if elapsed_ms > 0 else 0.0
            evals_per_sec = (
                float(samples) / elapsed_sec if samples and elapsed_sec else 0.0
            )

            row = {
                "scenario": scenario_name,
                "policy": policy,
                "status": status,
                "error": err_msg,
                "backend": backend_name,
                "mode": mode,
                "supports_ranges": (
                    "" if supports_ranges is None else ("1" if supports_ranges else "0")
                ),
                "n_players": n_players,
                "board_len": board_len,
                "exact": int(bool(exact)),
                "iters": "" if iters is None else int(iters),
                "samples": samples,
                "stderr": "" if stderr_val is None else f"{stderr_val:.6g}",
                "threads": "" if threads_val is None else int(threads_val),
                "elapsed_ms": round(elapsed_ms, 3),
                "evals_per_sec": round(evals_per_sec, 3) if evals_per_sec else 0.0,
                "eq_sum": round(eq_sum, 6) if equities else "",
                "equities": ";".join(f"{e:.6f}" for e in equities),
                "err_vs_exact": (
                    "" if err_vs_exact is None else f"{float(err_vs_exact):.6f}"
                ),
            }
            writer.writerow(row)


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=(
            "Tiny equity benchmark/correctness harness.\n\n"
            "Runs a small matrix of equity scenarios across one or more "
            "EQUITY_BACKEND_POLICY values and emits CSV rows with timing "
            "and basic equity summaries.\n\n"
            "Example:\n"
            "  python -m backend.scripts.benchmark_equity --out bench.csv\n"
            "  python -m backend.scripts.benchmark_equity --policies auto,ompeval,eval7\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--out",
        default="-",
        help='Output CSV file path (default: "-" for stdout).',
    )
    ap.add_argument(
        "--policies",
        default="auto,ompeval,eval7,pokerkit",
        help="Comma-separated EQUITY_BACKEND_POLICY values to benchmark "
        '(default: "auto,ompeval,eval7,pokerkit").',
    )
    return ap


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    policies = _parse_policies(args.policies)
    scenarios = _scenarios()

    # Determine CSV destination
    if args.out == "-" or args.out == "":
        csv_out = sys.stdout
        run_matrix(policies, scenarios, csv_out)
    else:
        out_path = args.out
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            run_matrix(policies, scenarios, f)


if __name__ == "__main__":
    main()
