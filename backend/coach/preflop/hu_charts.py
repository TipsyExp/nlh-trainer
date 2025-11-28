# backend/coach/preflop/hu_charts.py
"""
Helpers for loading heads-up preflop charts for the coach.

We support two on-disk formats:

1) Legacy "row" format (meta + rows):
   {
     "meta": {...},
     "rows": [
       { "hand": "AKo", "node": "BTN_open", "bucket": "2.5x",
         "strategy_bar": {"2.5x": 1.0, "fold": 0.0} },
       ...
     ]
   }

2) New "matrix" format (your default_100bb_2.5x.yml):

   version: 1
   profile_id: ...
   game: {...}
   ranks: [A, K, Q, J, T, 9, 8, 7, 6, 5, 4, 3, 2]
   nodes:
     BTN_RFI:
       actions:
         open_raise_2_5x:
           type: raise
           sizing: 2.5x
           matrix: ...

We translate the matrix spec into a PreflopChart with ChartRow entries
indexed by (node, hand_key) such as ("BTN_open", "AKo").
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, DefaultDict, Dict, List, Mapping, Tuple, cast
from collections import defaultdict

try:
    import yaml  # type: ignore[import]
except Exception:  # pragma: no cover - optional dependency
    yaml = None  # type: ignore[assignment]

from backend.coach.preflop.models import ChartMeta, ChartRow, PreflopChart

# Profile name used by config and the default YAML filename.
DEFAULT_PROFILE_NAME = "default_100bb_2.5x"


@dataclass(frozen=True)
class HUChartSet:
    """Container for one or more PreflopChart objects keyed by profile name."""

    charts_by_profile: Dict[str, List[PreflopChart]]

    def charts_for_profile(self, profile: str) -> List[PreflopChart]:
        """Return charts for a given profile, or a reasonable fallback."""
        if profile in self.charts_by_profile:
            return self.charts_by_profile[profile]
        # Fallback: first available profile, or empty list.
        for charts in self.charts_by_profile.values():
            return charts
        return []

    # Provide basic sequence-like behaviour so older code that expects a
    # simple list of charts still works (iteration, len, indexing).
    def __iter__(self):
        for charts in self.charts_by_profile.values():
            for c in charts:
                yield c

    def __len__(self) -> int:  # pragma: no cover - trivial
        return sum(len(charts) for charts in self.charts_by_profile.values())

    def __getitem__(self, idx: int) -> PreflopChart:  # pragma: no cover - trivial
        flat: List[PreflopChart] = []
        for charts in self.charts_by_profile.values():
            flat.extend(charts)
        return flat[idx]


def _backend_root() -> Path:
    """
    Best-effort backend dir detection.

    We assume this file lives at: backend/coach/preflop/hu_charts.py
    So backend/ is two levels up from here.
    """
    here = Path(__file__).resolve()
    backend_dir = here.parents[2]  # .../backend
    return backend_dir


def _default_profile_path() -> Path:
    return _backend_root() / "data" / "preflop_hu" / f"{DEFAULT_PROFILE_NAME}.yml"


# ---------------------------------------------------------------------------
# Legacy "row" format loader
# ---------------------------------------------------------------------------


def _load_row_chart_from_yaml(data: Mapping[str, Any], path: Path) -> PreflopChart:
    meta_raw = data.get("meta") or {}
    rows_raw = data.get("rows") or []

    if not isinstance(rows_raw, list) or not rows_raw:
        raise ValueError(
            f"HU preflop chart YAML {path} must define a non-empty 'rows' list"
        )

    meta = ChartMeta(
        format_version=int(meta_raw.get("format_version", 1)),
        name=str(meta_raw.get("name", path.name)),
        game_type=str(meta_raw.get("game_type", "NLH")),
        stack_bb=int(meta_raw.get("stack_bb", 0)),
        rake=str(meta_raw.get("rake", "")),
        positions=list(meta_raw.get("positions") or []),
        notes=meta_raw.get("notes"),
    )

    rows: List[ChartRow] = []
    for row in rows_raw:
        if not isinstance(row, dict):
            continue

        hand_key = str(row.get("hand") or row.get("hand_key") or "").strip()
        node = str(row.get("node") or "").strip()
        bucket = str(row.get("bucket") or "").strip()
        strategy_bar_raw = row.get("strategy_bar") or {}

        strategy_bar: Dict[str, float] = {}
        if isinstance(strategy_bar_raw, dict):
            for k, v in strategy_bar_raw.items():
                try:
                    strategy_bar[str(k)] = float(v)
                except Exception:
                    continue

        if not hand_key or not node or not bucket:
            continue

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


# ---------------------------------------------------------------------------
# Matrix format loader (default_100bb_2.5x.yml)
# ---------------------------------------------------------------------------

# Map YAML node ids to the simpler node ids used by the preflop HU policy.
_NODE_ID_ALIASES: Dict[str, str] = {
    "BTN_RFI": "BTN_open",
    "BB_vs_BTN_RFI": "BB_vs_BTN_open",
    # other nodes (BTN_vs_BB_3bet, BB_vs_BTN_4bet, ...) can be exposed
    # as-is later if / when the policy uses them.
}


def _canonical_node_id(raw: str) -> str:
    return _NODE_ID_ALIASES.get(raw, raw)


def _bucket_label_for_action(
    node_id: str, action_id: str, action: Mapping[str, object]
) -> str:
    """Map an action spec to a bucket label such as '2.5x', 'call', 'jam'."""
    t = str(action.get("type", "")).lower()
    sizing = action.get("sizing")

    if t == "call":
        return "call"
    if t == "jam":
        return "jam"
    if t == "raise":
        # For our purposes a simple "<number>x" label is fine.
        if isinstance(sizing, (int, float)):
            return f"{float(sizing):g}x"
        if isinstance(sizing, str) and sizing:
            return sizing
        # Fallback: use action id
        return str(action_id)

    # Fallback: stable id
    return str(action_id)


def _hand_key_from_ranks(
    row_rank: str,
    col_rank: str,
    rank_to_idx: Mapping[str, int],
) -> str:
    """
    Convert a (row_rank, col_rank) cell into a canonical hand key like
    'AKs', 'AKo', 'TT'.

    Convention:
      - Diagonal: pocket pairs, e.g. 'TT'.
      - Above/below diagonal: suited / offsuit, using the usual
        "upper triangle = suited" convention.
    """
    if row_rank not in rank_to_idx or col_rank not in rank_to_idx:
        raise KeyError("unknown rank")

    i = rank_to_idx[row_rank]
    j = rank_to_idx[col_rank]

    if i == j:
        # Pair: TT, 99, ...
        return f"{row_rank}{col_rank}"

    # Higher rank has smaller index (A before K, etc.)
    if i < j:
        hi, lo = row_rank, col_rank
        suited = True  # upper triangle
    else:
        hi, lo = col_rank, row_rank
        suited = False  # lower triangle

    suffix = "s" if suited else "o"
    return f"{hi}{lo}{suffix}"


def _load_matrix_chart_from_yaml(data: Mapping[str, Any], path: Path) -> PreflopChart:
    game_raw = data.get("game") or {}
    meta = ChartMeta(
        format_version=int(data.get("version", 1)),
        name=str(data.get("description", path.name)),
        game_type=str(game_raw.get("variant", "NLH")),
        stack_bb=int(game_raw.get("effective_stack_bb", 100)),
        rake="0",
        positions=["BTN", "BB"],
        notes=str(data.get("profile_id") or ""),
    )

    ranks_list = list(
        data.get("ranks")
        or ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]
    )
    rank_to_idx: Dict[str, int] = {r: i for i, r in enumerate(ranks_list)}

    nodes_raw = data.get("nodes") or {}
    if not isinstance(nodes_raw, Mapping):
        raise ValueError("matrix HU chart YAML must define 'nodes' mapping")

    # Accumulate bucket mixes keyed by (node_id, hand_key)
    mixes: DefaultDict[Tuple[str, str], Dict[str, float]] = defaultdict(dict)

    for raw_node_id, node_spec in nodes_raw.items():
        if not isinstance(node_spec, Mapping):
            continue

        node_id = _canonical_node_id(str(raw_node_id))
        actions = node_spec.get("actions") or {}
        if not isinstance(actions, Mapping):
            continue

        for action_id, action_spec in actions.items():
            if not isinstance(action_spec, Mapping):
                continue

            bucket_label = _bucket_label_for_action(
                node_id, str(action_id), action_spec
            )
            matrix_spec = action_spec.get("matrix") or {}
            if not isinstance(matrix_spec, Mapping):
                continue

            # Prefer per-action ranks if present; otherwise use global ranks.
            matrix_ranks = list(matrix_spec.get("ranks") or ranks_list)
            col_rank_by_idx: Dict[int, str] = {
                idx: r for idx, r in enumerate(matrix_ranks) if r in rank_to_idx
            }

            rows_raw = matrix_spec.get("rows") or []
            if not isinstance(rows_raw, list):
                continue

            for row in rows_raw:
                if not isinstance(row, Mapping):
                    continue
                row_rank = str(row.get("rank") or "").strip()
                if row_rank not in rank_to_idx:
                    continue
                values = row.get("values") or []
                if not isinstance(values, list):
                    continue

                for j, val in enumerate(values):
                    col_rank = col_rank_by_idx.get(j)
                    if not col_rank:
                        continue
                    try:
                        f = float(val)
                    except Exception:
                        continue
                    if f <= 0.0:
                        continue

                    try:
                        hand_key = _hand_key_from_ranks(row_rank, col_rank, rank_to_idx)
                    except KeyError:
                        continue

                    key = (node_id, hand_key)
                    prev = mixes[key].get(bucket_label, 0.0)
                    mixes[key][bucket_label] = prev + f

    # Convert mixes into ChartRow entries and normalise the per-hand
    # distribution to include an implicit "fold" bucket.
    rows: List[ChartRow] = []
    for (node_id, hand_key), mix in mixes.items():
        cleaned: Dict[str, float] = {}
        for b, v in mix.items():
            try:
                fv = float(v)
            except Exception:
                fv = 0.0
            if fv > 0.0:
                cleaned[b] = fv

        total = sum(cleaned.values())
        if total < 1.0:
            # Add implicit fold mass so that every hand has a complete
            # distribution over {action buckets, fold}.
            cleaned["fold"] = cleaned.get("fold", 0.0) + max(0.0, 1.0 - total)
            total = sum(cleaned.values())

        if total <= 0.0:
            # Degenerate; just skip this hand.
            continue

        norm = {b: v / total for b, v in cleaned.items()}
        # Primary bucket = argmax over the normalised mix
        primary = max(norm.items(), key=lambda kv: kv[1])[0]

        rows.append(
            ChartRow(
                hand_key=hand_key,
                node=node_id,
                bucket=primary,
                strategy_bar=norm,
            )
        )

    chart = PreflopChart(meta=meta, rows=rows)
    chart.build_index()
    return chart


# ---------------------------------------------------------------------------
# Top-level YAML loader and dummy fallback
# ---------------------------------------------------------------------------


def _load_chart_from_yaml(path: Path) -> PreflopChart:
    if yaml is None:
        raise RuntimeError(
            "PyYAML is required to load HU preflop charts. "
            "Install it with: pip install pyyaml"
        )

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}  # type: ignore[no-untyped-call]

    if not isinstance(raw, Mapping):
        raise ValueError(f"HU preflop chart YAML {path} must be a mapping")

    data = cast(Mapping[str, Any], raw)

    # Detect format: matrix (your default_100bb_2.5x.yml) vs legacy rows.
    if "nodes" in data:
        return _load_matrix_chart_from_yaml(data, path)

    # Legacy row-format (meta + rows)
    return _load_row_chart_from_yaml(data, path)


def _make_dummy_chart() -> PreflopChart:
    """
    Tiny built-in chart used if the YAML file is missing or broken.

    It defines a single BTN_open row for AKo that prefers a 2.5x raise.
    (This is mainly for tests / emergency fallback.)
    """
    meta = ChartMeta(
        format_version=1,
        name="HU 100bb default (dummy)",
        game_type="NLH",
        stack_bb=100,
        rake="0",
        positions=["BTN", "BB"],
        notes="Built-in dummy chart used when YAML is unavailable.",
    )
    rows = [
        ChartRow(
            hand_key="AKo",
            node="BTN_open",
            bucket="2.5x",
            strategy_bar={"2.5x": 0.7, "fold": 0.3},
        )
    ]
    chart = PreflopChart(meta=meta, rows=rows)
    chart.build_index()
    return chart


def load_default_chart_set() -> HUChartSet:
    """
    Load the default HU 100bb 2.5x profile as a HUChartSet.

    Tries to read backend/data/preflop_hu/default_100bb_2.5x.yml; if that
    fails for any reason we fall back to a tiny in-memory dummy chart.
    """
    path = _default_profile_path()
    try:
        if path.exists():
            chart = _load_chart_from_yaml(path)
        else:
            chart = _make_dummy_chart()
    except Exception:  # pragma: no cover - defensive fallback
        chart = _make_dummy_chart()

    return HUChartSet(charts_by_profile={DEFAULT_PROFILE_NAME: [chart]})


__all__ = [
    "DEFAULT_PROFILE_NAME",
    "HUChartSet",
    "load_default_chart_set",
]
