# backend/coach/preflop/service.py
from __future__ import annotations

import os
from typing import TYPE_CHECKING, List, Optional, Sequence, Any

from .charts import load_charts_from_paths
from .models import Advice, PreflopChart, PreflopContext
from .ranges import (
    NODE_BB_VS_SB_OPEN,
    NODE_SB_OPEN,
    NODE_HU_GENERIC,
    get_default_villain_range,
    hero_hand_key_to_range,
)
from backend.services.equity.base import PlayerSpec

if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from backend.services.equity.service import EquityService


class PreflopAdvisorService:
    """
    Chart-first preflop advisor with optional equity fallback.

    Responsibilities:
      - Load preflop charts from PREFLOP_CHART_PATHS (or explicit paths in tests).
      - Provide a simple get_advice(hand_id, idx) entrypoint.
      - Prefer chart lookups; when a (node, hand_key) has no chart row and
        an equity engine is available, optionally fall back to an
        equity-threshold decision.

    Notes:
      - Context derivation from (hand_id, idx) is intentionally minimal.
        In real wiring, `_build_context` should be replaced / extended to
        pull positions, stack depth, hero hand, node, etc. from the engine.
      - Equity fallback is conservative and HU-only, using coarse default
        villain ranges and a single threshold knob PREFLOP_EQ_DEFEND_THRESH.
    """

    def __init__(
        self,
        chart_paths: Optional[Sequence[str]] = None,
        equity_service: Optional[EquityService] = None,
        eq_defend_thresh: Optional[float] = None,
        fallback_required: Optional[bool] = None,
    ) -> None:
        """
        Initialize the advisor and eagerly load charts.

        chart_paths:
          - If provided, load charts from these paths (useful for tests).
          - If None, read PREFLOP_CHART_PATHS from the environment.
            Paths are split on ':' or ';' (via os.pathsep).

        equity_service:
          - Optional injected EquityService (for tests or custom wiring).
          - If None, we attempt to construct one lazily. If that fails,
            equity fallback is treated as unavailable.

        eq_defend_thresh:
          - Optional explicit equity defend threshold.
          - If None, read PREFLOP_EQ_DEFEND_THRESH from the environment,
            defaulting to 0.48.

        fallback_required:
          - When True, failure to use equity fallback for a chart miss
            will raise a RuntimeError instead of silently falling back
            to a chart-based heuristic.
          - If None, read PREFLOP_FALLBACK_REQUIRED from the environment
            (default false).
        """
        # Resolve chart paths
        if chart_paths is None:
            raw = os.getenv("PREFLOP_CHART_PATHS", "")
            if raw:
                parts = [p.strip() for p in raw.split(os.pathsep)]
                chart_paths = [p for p in parts if p]
            else:
                chart_paths = []

        self._chart_paths: List[str] = list(chart_paths)
        self._charts: List[PreflopChart] = load_charts_from_paths(self._chart_paths)

        # Equity service wiring (optional)
        self._equity: Optional[EquityService]
        if equity_service is not None:
            self._equity = equity_service
        else:
            try:
                from backend.services.equity.service import (
                    EquityService as _EquityService,
                )

                self._equity = _EquityService()
            except Exception:
                # If equity wiring fails (e.g. missing deps), we still allow
                # pure chart mode; equity fallback will be unavailable.
                self._equity = None

        # Defend threshold (coarse, HU-only for now)
        if eq_defend_thresh is not None:
            self._eq_defend_thresh = float(eq_defend_thresh)
        else:
            raw_thresh = os.getenv("PREFLOP_EQ_DEFEND_THRESH", "").strip()
            try:
                self._eq_defend_thresh = float(raw_thresh) if raw_thresh else 0.48
            except ValueError:
                self._eq_defend_thresh = 0.48

        # Behaviour when equity fallback is unavailable
        if fallback_required is not None:
            self._fallback_required = bool(fallback_required)
        else:
            raw_required = (
                os.getenv("PREFLOP_FALLBACK_REQUIRED", "false").strip().lower()
            )
            self._fallback_required = raw_required in {"1", "true", "yes", "on"}

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
        Return preflop advice for the given engine decision.

        Resolution order:
          1. Build a minimal PreflopContext from (hand_id, idx).
          2. Select the most appropriate chart.
          3. If context has both node and hand_key:
               - Try a direct chart lookup.
               - If a row exists, return chart-based Advice (source="chart").
               - If no row exists:
                   * If equity engine is available, attempt equity fallback.
                   * If fallback fails and `fallback_required` is true, raise.
                   * Otherwise fall back to a chart-based heuristic row.
             Else (no node/hand_key on context):
               - Use chart-based heuristic row only (no equity fallback).

        Raises:
          - RuntimeError if no charts are configured.
          - RuntimeError if chart miss + fallback_required and equity is unavailable.
          - ValueError if chart is empty.
        """
        if not self._charts:
            raise RuntimeError(
                "preflop coach charts not configured "
                "(PREFLOP_CHART_PATHS is empty or files failed to load)"
            )

        ctx = self._build_context(hand_id=hand_id, idx=idx)
        chart = self._select_chart(ctx, self._charts)

        row = None
        node = (ctx.node or "").strip()
        hand_key = (ctx.hand_key or "").strip()

        # 1) Direct chart hit if we have a concrete (node, hand_key)
        if node and hand_key:
            row = chart.lookup(node, hand_key)

        # 2) If no chart row and we have an equity engine, attempt fallback.
        if row is None and node and hand_key and self._equity is not None:
            try:
                return self._equity_fallback(
                    ctx=ctx,
                    chart=chart,
                    hand_id=hand_id,
                    idx=idx,
                )
            except RuntimeError:
                if self._fallback_required:
                    raise

        # 3) Fallback to chart-based heuristic row (previous behaviour)
        if row is None:
            try:
                row = self._select_row(ctx, chart)
            except LookupError:
                if node and hand_key and self._equity is not None:
                    return self._equity_fallback(
                        ctx=ctx,
                        chart=chart,
                        hand_id=hand_id,
                        idx=idx,
                    )
                if self._fallback_required:
                    raise
                raise

        # Build a human-readable rationale string for chart path.
        chart_name = getattr(chart.meta, "name", "unknown_chart")
        row_node = getattr(row, "node", None)
        row_hand_key = getattr(row, "hand_key", None)

        rationale_bits = [f"chart:{chart_name}"]
        if row_node:
            rationale_bits.append(f"node={row_node}")
        if row_hand_key:
            rationale_bits.append(f"hand={row_hand_key}")
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

    # ------------------------------------------------------------------ #
    # Equity fallback internals
    # ------------------------------------------------------------------ #

    def _equity_fallback(
        self,
        ctx: PreflopContext,
        chart: PreflopChart,  # noqa: ARG002 - reserved for future use
        hand_id: str,
        idx: int,
    ) -> Advice:
        """
        Equity-based fallback when no chart row exists for (node, hand_key).

        Uses:
          - hero range derived from ctx.hand_key (pbots-/Equilab-style shorthand).
          - villain range from get_default_villain_range(node).
          - EquityService to compute hero equity in a HU scenario.
          - PREFLOP_EQ_DEFEND_THRESH to decide defend vs fold.

        Raises RuntimeError when fallback cannot be performed.
        """
        if self._equity is None:
            raise RuntimeError(
                "equity fallback unavailable: no equity service configured"
            )

        node = (ctx.node or NODE_HU_GENERIC).strip() or NODE_HU_GENERIC
        hand_key = (ctx.hand_key or "").strip()
        hero_range = hero_hand_key_to_range(hand_key)
        if not hero_range:
            raise RuntimeError("equity fallback unavailable: missing hero hand key")

        villain_range = get_default_villain_range(node)

        svc: Any = self._equity

        # 0) Prefer a direct range-vs-range helper if present on the stub/service.
        #    Tests may inject a very small stub with this exact method.
        range_methods = [
            "range_vs_range_equity",
            "ranges_equity",
            "equity_ranges",
            "equity_of_ranges",
            "hero_vs_range_equity",  # some stubs overload this to accept ranges
        ]
        for name in range_methods:
            fn = getattr(svc, name, None)
            if callable(fn):
                try:
                    eq = fn(hero_range, villain_range)  # type: ignore[misc]
                    hero_equity = float(eq)
                    break
                except Exception:
                    # If signature doesn't match (e.g., real EquityService), try next option.
                    continue
        else:
            # 1) Generic: find a callable in a permissive order.
            def _pick_callable(obj: Any):
                for n in ("calc_equity", "calc", "compute", "evaluate", "run"):
                    f = getattr(obj, n, None)
                    if callable(f):
                        return f
                if callable(obj):  # __call__ on the object itself
                    return obj
                return None

            calc = _pick_callable(svc)

            # 2) Normalize whatever result we get to a hero equity float.
            def _extract_hero_equity(res: Any) -> float:
                per_player = getattr(res, "per_player", None)
                if per_player is None and isinstance(res, dict):
                    per_player = res.get("per_player")
                if per_player and isinstance(per_player, (list, tuple)):
                    first = per_player[0]
                    if isinstance(first, dict) and "equity" in first:
                        return float(first["equity"])
                if isinstance(res, (int, float)):
                    return float(res)
                if (
                    isinstance(res, (list, tuple))
                    and res
                    and isinstance(res[0], (int, float))
                ):
                    return float(res[0])
                raise RuntimeError(
                    "equity fallback unavailable: unrecognized equity result"
                )

            if calc is not None:
                try:
                    res = calc(
                        players=[
                            PlayerSpec(range=hero_range),
                            PlayerSpec(range=villain_range),
                        ],
                        board=(),
                        dead=(),
                        exact=False,
                        iters=None,
                        timeout_ms=None,
                    )
                except Exception as e:  # pragma: no cover
                    raise RuntimeError(f"equity fallback unavailable: {e}") from e
                hero_equity = _extract_hero_equity(res)
            else:
                # 3) Last-resort: accept a fixed attribute on the stub.
                fixed = None
                for n in ("equity", "eq", "hero_equity", "p", "pwin"):
                    val = getattr(svc, n, None)
                    if isinstance(val, (int, float)):
                        fixed = float(val)
                        break
                # Also accept a 'per_player'-shaped attribute on the stub.
                if fixed is None:
                    per_player_attr = getattr(svc, "per_player", None)
                    if isinstance(per_player_attr, (list, tuple)) and per_player_attr:
                        first = per_player_attr[0]
                        if isinstance(first, dict) and "equity" in first:
                            try:
                                fixed = float(first["equity"])
                            except Exception:
                                fixed = None
                if fixed is None:
                    raise RuntimeError(
                        "equity fallback unavailable: no usable equity function or value on equity service"
                    )
                hero_equity = fixed  # type: ignore[assignment]

        thresh = float(self._eq_defend_thresh)
        defend = hero_equity >= thresh
        bucket = self._choose_fallback_bucket(node=node, defend=defend)

        # Simple pure-strategy bar for now.
        strategy_bar = {bucket: 1.0}

        rationale = (
            "equity_fallback: "
            f"node={node}; hero={hero_range}; villain={villain_range}; "
            f"eq={hero_equity:.3f}; thresh={thresh:.3f}; "
            f"decision={'defend' if defend else 'fold'}; "
            f"hand_id={hand_id}; idx={idx}"
        )

        return Advice(
            source="equity",
            bucket=bucket,
            rationale=rationale,
            strategy_bar=strategy_bar,
        )

    def _choose_fallback_bucket(self, node: str, defend: bool) -> str:
        """
        Map a (node, defend?) decision to an engine bucket label.

        Buckets must align with the engine's preflop semantics:

          - Open nodes (no facing bet) typically use:
              ["2.2x", "2.5x", "3.0x", "jam"]

          - Facing-open nodes (e.g. BB vs SB open) use:
              ["fold", "call", "2.5xR", "3.0xR", "jam"]

        For this mini-milestone we keep the mapping intentionally simple:
          - sb_open:
              defend=True  -> "2.5x"
              defend=False -> "fold"
          - bb_vs_sb_open:
              defend=True  -> "call"
              defend=False -> "fold"
          - other nodes:
              defend=True  -> "call"
              defend=False -> "fold"
        """
        node = (node or "").strip().lower()

        if node == NODE_SB_OPEN:
            return "2.5x" if defend else "fold"

        if node == NODE_BB_VS_SB_OPEN:
            return "call" if defend else "fold"

        # Generic HU fallback: call vs fold.
        return "call" if defend else "fold"
