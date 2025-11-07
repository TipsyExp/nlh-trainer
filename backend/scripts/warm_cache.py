from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from typing import Iterable, List, Sequence

from backend.adapters.solver.texassolver_adapter import (
    SolveRequest,
    CoachDisabledError,
    UnsupportedSpotError,
)
from backend.coach.texassolver_cache import resolve_with_cache
from backend.coach.cache import ensure_tables
from backend.logger import get_logger


def _parse_spr_list(raw: str) -> List[float]:
    vals: List[float] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            vals.append(float(part))
        except ValueError:
            raise argparse.ArgumentTypeError(f"Invalid SPR value: {part}")
    if not vals:
        raise argparse.ArgumentTypeError("At least one SPR is required")
    return vals


def _sample_boards(n: int) -> List[List[str]]:
    # Deterministic board sampler (no hand context here; suitable for warm-up only)
    import random

    ranks = list("23456789TJQKA")
    suits = list("hdcs")  # use lowercase suits, e.g. Ah, Kd, 3s
    deck = [r + s for r in ranks for s in suits]

    boards: List[List[str]] = []
    rnd = random.Random(1337)
    for _ in range(n):
        b = rnd.sample(deck, 3)
        boards.append([b[0], b[1], b[2]])
    return boards


def _ensure_env_threads(threads: int | None) -> None:
    if threads is None:
        return
    os.environ["COACH_TS_THREADS"] = str(threads)


def _guard_env() -> None:
    ce = os.environ.get("COACH_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not ce:
        print("warm_cache: COACH_ENABLED is not true — enable it to warm the cache.")
        sys.exit(2)
    tsp = os.environ.get("TEXASSOLVER_PATH", "").strip()
    if not tsp:
        print("warm_cache: TEXASSOLVER_PATH is not set — solver binary required.")
        sys.exit(2)


DEFAULT_BUCKETS = ["TOP", "MID", "LOW"]


def _build_requests(
    preset: str, boards: Sequence[Sequence[str]], sprs: Sequence[float]
) -> List[SolveRequest]:
    reqs: List[SolveRequest] = []
    # Heuristics for HU SRP postflop warm-up
    if preset == "hu_srp":
        # Use symmetric stacks; choose integer chip units for stable keys
        base_stack = 200  # arbitrary units (e.g., BB or chips), consistent across nodes
        for b in boards:
            for spr in sprs:
                # spr = stack / pot -> pot = stack / spr
                pot = max(1, int(round(base_stack / max(spr, 0.1))))
                reqs.append(
                    SolveRequest(
                        street="flop",
                        board=list(b),
                        pot=pot,
                        ip_stack=base_stack,
                        oop_stack=base_stack,
                        ip_range="AA,KK,QQ,AKs,AKo,AQs,AQo,TT-22",  # generic warm-up ranges
                        oop_range="AA,KK,QQ,AKs,AKo,AQs,AQo,TT-22",
                        bucket_labels=list(DEFAULT_BUCKETS),
                        spot="SRP",
                    )
                )
    else:
        raise ValueError(f"Unsupported preset: {preset}")
    return reqs


def main(argv: Iterable[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Warm the solver advice cache (SQLite)")
    p.add_argument(
        "--preset", default="hu_srp", help="Preset to generate nodes (default: hu_srp)"
    )
    p.add_argument(
        "--boards",
        type=int,
        default=50,
        help="Number of flop boards to sample (default: 50)",
    )
    p.add_argument(
        "--spr",
        default="20,40",
        help="Comma-separated SPR values (e.g., '20,40' or '30')",
    )
    p.add_argument(
        "--threads",
        type=int,
        default=None,
        help="Passthrough for COACH_TS_THREADS (optional)",
    )
    args = p.parse_args(list(argv) if argv is not None else None)

    _guard_env()
    _ensure_env_threads(args.threads)

    # Ensure cache table exists up front (fresh runs / CI or first runs)
    ensure_tables(get_logger().conn)

    try:
        sprs = _parse_spr_list(args.spr)
    except argparse.ArgumentTypeError as e:
        print(f"warm_cache: {e}")
        return 2

    boards = _sample_boards(max(1, int(args.boards)))
    reqs = _build_requests(args.preset, boards, sprs)

    total = 0
    hits = 0
    misses = 0
    errors = 0
    latencies: List[float] = []

    print(
        f"warm_cache: preset={args.preset} boards={len(boards)} sprs={sprs} threads={args.threads or '-'}"
    )

    for req in reqs:
        start = time.perf_counter()
        try:
            payload, cached, node_key = resolve_with_cache(req)
            dt_ms = (time.perf_counter() - start) * 1000.0
            latencies.append(dt_ms)
            total += 1
            if cached:
                hits += 1
            else:
                misses += 1
            # Lightweight progress feedback
            print(
                f"node={node_key[:12]} street={req.street} board={''.join(req.board)} spr~{req.ip_stack/max(req.pot,1):.1f} cached={str(cached).lower()} latency_ms={dt_ms:.1f}"
            )
        except UnsupportedSpotError:
            dt_ms = (time.perf_counter() - start) * 1000.0
            errors += 1
            print(
                f"node=? street={req.street} board={''.join(req.board)} status=unsupported latency_ms={dt_ms:.1f}"
            )
            continue
        except CoachDisabledError:
            dt_ms = (time.perf_counter() - start) * 1000.0
            errors += 1
            print(
                f"node=? street={req.street} board={''.join(req.board)} status=disabled latency_ms={dt_ms:.1f}"
            )
            continue
        except Exception as e:
            dt_ms = (time.perf_counter() - start) * 1000.0
            errors += 1
            print(
                f"node=? street={req.street} board={''.join(req.board)} status=error err={e} latency_ms={dt_ms:.1f}"
            )
            continue

    avg_ms = statistics.mean(latencies) if latencies else 0.0
    p50 = statistics.median(latencies) if latencies else 0.0
    print(
        f"warm_cache: done total={total} hits={hits} misses={misses} errors={errors} avg_ms={avg_ms:.1f} p50_ms={p50:.1f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
