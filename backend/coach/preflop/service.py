# backend/coach/preflop/service.py
from __future__ import annotations

import os
from typing import List, Optional, Sequence

from .models import Advice, PreflopChart, PreflopContext
from .charts import load_charts_from_paths


class PreflopAdvisorService:
    """
    Chart-only preflop advisor (MVP).

    Responsibilities:
      - Load preflop charts from PREFLOP_CHART_PATHS (or explicit paths in tests).
      - Provide a simple get_advice(hand_id, idx) entrypoint.
      - For now, use chart lookups only (no equity fallback).

    Notes / Limitations (by design for this mini-milestone):
      - Context derivation from (hand_id, idx) is intentionally minimal.
        In real wiring, `_build_context` should be replaced / extended to
        pull positions, stack depth, hero hand, node, etc. from the engine.
      - Chart selection and row selection are currently conservative:
        they prefer the first matching chart/row, or fall back to the first
        available chart if no better signal is present.
    """

    def __init__(
        self,
        chart_paths: Optional[Sequence[str]] = None,
    ) -> None:
        """
        Initialize the advisor and eagerly load charts.

        chart_paths:
          - If provided, load charts from these paths (useful for tests).
          - If None, read PREFLOP_CHART_PATHS from the environment.
            Paths are split on ':' or ';'.
        """
        if chart_paths is None:
            raw = os.getenv("PREFLOP_CHART_PATHS", "")
            if raw:
                parts = [p.strip() for p in raw.split(os.pathsep)]
                chart_paths = [p for p in parts if p]
            else:
                chart_paths = []

        self._chart_paths: List[str] = list(chart_paths)
        self._charts: List[PreflopChart] = load_charts_from_paths(self._chart_paths)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @property
    def charts(self) -> Sequence[PreflopChart]:
        """Return the loaded charts (read-only view)."""
        return self._charts

    @property
    def has_charts(self) -> bool:
        """True if at least one chart has been loaded."""
        return bool(self._charts)

    def get_advice(self, hand_id: str, idx: int) -> Advice:
        """
        Return chart-based advice for the given engine decision.

        For this MVP:
          - Derives a minimal PreflopContext from (hand_id, idx).
          - Picks an appropriate chart (or the first one as a fallback).
          - Picks an appropriate row inside that chart.

        Raises:
          - RuntimeError if no charts are configured.
          - LookupError / ValueError if no row is found for the context.
        """
        if not self._charts:
            raise RuntimeError(
                "preflop coach charts not configured "
                "(PREFLOP_CHART_PATHS is empty or files failed to load)"
            )

        ctx = self._build_context(hand_id=hand_id, idx=idx)
        chart = self._select_chart(ctx, self._charts)
        row = self._select_row(ctx, chart)

        # Build a human-readable rationale string.
        chart_name = getattr(chart.meta, "name", "unknown_chart")
        node = getattr(row, "node", None)
        hand_key = getattr(row, "hand", None) or getattr(row, "hand_key", None)

        rationale_bits = [f"chart:{chart_name}"]
        if node:
            rationale_bits.append(f"node={node}")
        if hand_key:
            rationale_bits.append(f"hand={hand_key}")
        rationale_bits.append(f"hand_id={hand_id}")
        rationale_bits.append(f"idx={idx}")
        rationale = "; ".join(rationale_bits)

        return Advice(
            source="chart",
            bucket=getattr(row, "bucket"),
            rationale=rationale,
            strategy_bar=getattr(row, "strategy_bar"),
        )

    # ------------------------------------------------------------------ #
    # Internals (override / monkeypatch-friendly)
    # ------------------------------------------------------------------ #

    def _build_context(self, hand_id: str, idx: int) -> PreflopContext:
        """
        Derive a minimal PreflopContext from (hand_id, idx).

        For this mini-milestone, keep it very light:
          - Provide empty hand/node so selection falls back to the first chart/row.
          - Tests are free to monkeypatch this to a richer context.
        """
        # Safe defaults: empty strings ensure `_select_row` will fall back to the first row.
        return PreflopContext(
            hand_key="",
            node="",
            stack_bb=None,
            hero_position=None,
            villain_position=None,
        )

    def _select_chart(
        self,
        ctx: PreflopContext,
        charts: Sequence[PreflopChart],
    ) -> PreflopChart:
        """
        Choose a chart for the given context.

        Current heuristic:
          - If ctx.game_type / ctx.stack_bb / ctx.hero_position are present,
            prefer charts whose meta matches those fields.
          - Otherwise, or if nothing matches, fall back to the first chart.
        """
        if not charts:
            raise RuntimeError("no preflop charts loaded")

        game_type = getattr(ctx, "game_type", None)
        stack_bb = getattr(ctx, "stack_bb", None)
        hero_pos = getattr(ctx, "hero_position", None)

        candidates: List[PreflopChart] = []
        for chart in charts:
            meta = chart.meta

            # Match game type if provided
            if game_type:
                meta_game = getattr(meta, "game_type", None)
                if meta_game is not None and meta_game != game_type:
                    continue

            # Match stack depth if provided
            if stack_bb is not None:
                meta_stack = getattr(meta, "stack_bb", None)
                if meta_stack is not None and meta_stack != stack_bb:
                    continue

            # Match hero position membership if provided
            if hero_pos:
                positions = getattr(meta, "positions", []) or []
                if hero_pos not in positions:
                    continue

            candidates.append(chart)

        if candidates:
            return candidates[0]

        # Fallback: simplest behaviour – just use the first chart.
        return charts[0]

    def _select_row(self, ctx: PreflopContext, chart: PreflopChart):
        """
        Choose a chart row for the given context + chart.

        Current heuristic:
          - Try to match on (node, hand_key) if we have those on the context.
          - Otherwise, try to match on node alone.
          - Otherwise, return the first row.
        """
        rows = getattr(chart, "rows", []) or []
        if not rows:
            raise ValueError("chart has no rows")

        node = getattr(ctx, "node", None)
        ctx_hand_key = (
            getattr(ctx, "hero_hand_key", None)
            or getattr(ctx, "hand_key", None)
            or None
        )

        # 1) Exact match on (node, hand_key) if available
        if node and ctx_hand_key:
            hit = chart.lookup(node, ctx_hand_key)
            if hit is not None:
                return hit

        # 2) Match by node only
        if node:
            for r in rows:
                if getattr(r, "node", None) == node:
                    return r

        # 3) Fallback: first row
        return rows[0]
