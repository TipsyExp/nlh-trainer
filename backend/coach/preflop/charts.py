# backend/coach/preflop/charts.py
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Sequence

from .models import ChartMeta, ChartRow, PreflopChart, PreflopContext

_RANKS = "23456789TJQKA"
_RANK_INDEX: Dict[str, int] = {r: i for i, r in enumerate(_RANKS)}


def canonicalize_hand(cards: Sequence[str]) -> str:
    """
    Canonicalize a two-card hand to a compact key used by charts.

    Examples:
        ["Ah", "Ad"] -> "AA"
        ["Ah", "Jh"] -> "AJs"
        ["Ah", "Jc"] -> "AJo"

    This helper is here for future use when we derive hand keys from real hole
    cards. For this mini-milestone, charts are expected to already use these
    canonical keys in their "hand" field.
    """
    if len(cards) != 2:
        raise ValueError(f"expected 2 cards, got {len(cards)}")

    c1, c2 = cards[0], cards[1]
    if len(c1) != 2 or len(c2) != 2:
        raise ValueError(f"cards must be rank+suit like 'Ah', got {c1!r}, {c2!r}")

    r1, s1 = c1[0], c1[1]
    r2, s2 = c2[0], c2[1]

    if r1 not in _RANK_INDEX or r2 not in _RANK_INDEX:
        raise ValueError(f"invalid rank in cards: {c1!r}, {c2!r}")

    # Pairs: "JJ", "TT", etc.
    if r1 == r2:
        return f"{r1}{r2}"

    # Non-pairs: sort by rank, high first, then "s"/"o" suffix.
    suited = s1 == s2
    if _RANK_INDEX[r1] > _RANK_INDEX[r2]:
        hi, lo = r1, r2
    else:
        hi, lo = r2, r1

    return f"{hi}{lo}{'s' if suited else 'o'}"


def _load_chart_from_path(path: str) -> PreflopChart:
    """
    Load a single chart JSON file into a PreflopChart.

    Expected JSON shape:

    {
      "meta": {
        "format_version": 1,
        "name": "HU 25bb SRP vSB",
        "game_type": "NLH",
        "stack_bb": 25,
        "rake": "0",
        "positions": ["SB", "BB"],
        "notes": "optional"
      },
      "rows": [
        {
          "hand": "AJo",
          "node": "sb_open",
          "bucket": "2.5x",
          "strategy_bar": { "fold": 0.0, "call": 0.2, "2.5x": 0.8 }
        }
      ]
    }
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    meta_raw = data.get("meta") or {}
    rows_raw = data.get("rows") or []

    meta = ChartMeta(
        format_version=int(meta_raw.get("format_version", 1)),
        name=str(meta_raw.get("name", os.path.basename(path))),
        game_type=str(meta_raw.get("game_type", "NLH")),
        stack_bb=int(meta_raw.get("stack_bb", 0)),
        rake=str(meta_raw.get("rake", "")),
        positions=list(meta_raw.get("positions", [])),
        notes=meta_raw.get("notes"),
    )

    rows: List[ChartRow] = []
    for row in rows_raw:
        hand_key = str(row["hand"])
        node = str(row["node"])
        bucket = str(row["bucket"])
        strategy_bar = dict(row.get("strategy_bar") or {})
        rows.append(
            ChartRow(
                hand_key=hand_key,
                node=node,
                bucket=bucket,
                strategy_bar=strategy_bar,
            )
        )

    chart = PreflopChart(meta=meta, rows=rows)
    chart.build_index()
    return chart


def load_charts_from_paths(paths: Sequence[str]) -> List[PreflopChart]:
    """
    Load charts from a sequence of file paths.

    Empty or whitespace-only paths are ignored. Raises if a path points to
    a non-existent file or invalid JSON.

    The caller is responsible for deciding how to handle errors (e.g., treat
    "no charts loaded" as "coach disabled" vs surfacing an error).
    """
    charts: List[PreflopChart] = []
    for raw in paths:
        path = raw.strip()
        if not path:
            continue
        chart = _load_chart_from_path(path)
        charts.append(chart)
    return charts


def find_chart_for_context(
    ctx: PreflopContext,
    charts: Sequence[PreflopChart],
) -> Optional[PreflopChart]:
    """
    Select the most appropriate chart for a given preflop context.

    Heuristics (simple for now):
      1. If ctx.stack_bb is set, prefer charts with matching stack_bb.
      2. If hero/villain positions are set, require both to appear in chart.meta.positions.
      3. Among candidates, return the first chart that contains a row for
         (ctx.node, ctx.hand_key).
      4. As a fallback, search all charts for a row for (ctx.node, ctx.hand_key).

    Returns:
        A PreflopChart if a suitable chart is found; otherwise None.
    """
    if not charts:
        return None

    candidates: List[PreflopChart] = list(charts)

    # Filter by stack depth, if provided.
    if ctx.stack_bb is not None:
        exact_stack = [c for c in candidates if c.meta.stack_bb == ctx.stack_bb]
        if exact_stack:
            candidates = exact_stack

    # Filter by positions, if provided.
    if ctx.hero_position and ctx.villain_position:

        def _pos_ok(c: PreflopChart) -> bool:
            positions = set(c.meta.positions or [])
            return ctx.hero_position in positions and ctx.villain_position in positions

        pos_filtered = [c for c in candidates if _pos_ok(c)]
        if pos_filtered:
            candidates = pos_filtered

    # Prefer candidates that actually contain the requested node/hand.
    for chart in candidates:
        if chart.lookup(ctx.node, ctx.hand_key) is not None:
            return chart

    # Fallback: search all charts.
    for chart in charts:
        if chart.lookup(ctx.node, ctx.hand_key) is not None:
            return chart

    return None
