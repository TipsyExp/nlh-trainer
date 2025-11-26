# backend/coach/preflop/hu_charts.py
"""
Helpers for loading heads-up preflop charts for the coach.

For now this is deliberately tiny: we support a single built-in profile
("default_100bb_2.5x") and expose a convenience loader
`load_default_chart_set()` that returns a HUChartSet object suitable for
the HU preflop policy.

If the on-disk YAML file is missing or cannot be parsed we fall back to a
small in-memory dummy chart that covers AKo on the BTN, so tests and
basic behaviour still work.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

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


def _load_chart_from_yaml(path: Path) -> PreflopChart:
    if yaml is None:
        raise RuntimeError(
            "PyYAML is required to load HU preflop charts. "
            "Install it with: pip install pyyaml"
        )

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}  # type: ignore[no-untyped-call]

    meta_raw = data.get("meta") or {}
    rows_raw = data.get("rows") or []

    # If there is no proper rows list, treat this as an invalid HU YAML and
    # let caller fall back to the dummy chart.
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


def _make_dummy_chart() -> PreflopChart:
    """
    Tiny built-in chart used if the YAML file is missing or broken.

    It defines a single BTN_open row for AKo that prefers a 2.5x raise.
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
