# backend/coach/preflop/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Literal


@dataclass(frozen=True)
class ChartMeta:
    """
    Metadata describing a preflop chart.

    Fields are intentionally simple and loosely typed so that different chart
    sources (JSON/TOML, generated, etc.) can map into this shape without
    friction.

    Attributes:
        format_version: Schema/version of the chart file format (e.g. 1).
        name:           Human-readable name, e.g. "HU 25bb SRP vSB".
        game_type:      Game type identifier, e.g. "NLH".
        stack_bb:       Effective stack in big blinds (e.g. 25).
        rake:           Rake descriptor, e.g. "0" or "5% capped".
        positions:      Ordered list of seat labels, e.g. ["SB", "BB"].
        notes:          Optional free-form notes about assumptions (rake, pool).
    """

    format_version: int
    name: str
    game_type: str
    stack_bb: int
    rake: str
    positions: List[str]
    notes: Optional[str] = None


@dataclass(frozen=True)
class ChartRow:
    """
    Single row in a preflop chart.

    A row describes the recommended action bucket and strategy mix for a given
    abstracted hand and node.

    Attributes:
        hand_key:      Canonical hand identifier, e.g. "AJo", "A5s", "QQ".
        node:          Spot identifier, e.g. "sb_open", "bb_vs_sb_open".
        bucket:        Primary recommended bucket, e.g. "2.5x", "jam", "fold".
        strategy_bar:  Normalized strategy distribution, mapping bucket label
                       -> probability in [0, 1]. The sum does not need to be
                       exactly 1.0 but should be close.
    """

    hand_key: str
    node: str
    bucket: str
    strategy_bar: Dict[str, float]


@dataclass
class PreflopChart:
    """
    In-memory representation of a preflop chart.

    Attributes:
        meta:  Chart-level metadata.
        rows:  List of ChartRow entries.

    The chart may also maintain derived indexes for faster lookup by
    (node, hand_key).
    """

    meta: ChartMeta
    rows: List[ChartRow] = field(default_factory=list)

    # Optional in-memory index for quick lookups.
    _index: Dict[Tuple[str, str], ChartRow] = field(
        default_factory=dict, init=False, repr=False
    )

    def build_index(self) -> None:
        """
        Build or rebuild the internal (node, hand_key) -> row index.

        This is idempotent and safe to call multiple times.
        """
        idx: Dict[Tuple[str, str], ChartRow] = {}
        for row in self.rows:
            key = (row.node, row.hand_key)
            # Last one wins if duplicates exist; charts should avoid this.
            idx[key] = row
        self._index = idx

    def lookup(self, node: str, hand_key: str) -> Optional[ChartRow]:
        """
        Find a row for the given node and canonical hand key.

        Returns:
            ChartRow if a matching row exists, else None.
        """
        if not self._index:
            self.build_index()
        return self._index.get((node, hand_key))


@dataclass(frozen=True)
class Advice:
    """
    Normalized preflop advice returned by the coach.

    Attributes:
        source:        One of:
                         - "chart"  → direct lookup from a preflop chart
                         - "equity" → equity-threshold fallback decision
        bucket:        Primary recommended bucket, e.g. "2.5x", "jam", "fold".
        rationale:     Human-readable explanation of the recommendation
                       (chart name, node, assumptions, etc.).
        strategy_bar:  Strategy distribution over buckets (bucket -> weight).
    """

    source: Literal["chart", "equity"]
    bucket: str
    rationale: str
    strategy_bar: Dict[str, float]


@dataclass(frozen=True)
class PreflopContext:
    """
    Minimal description of a preflop spot for chart lookup.

    For this mini-milestone we keep it deliberately small. Later we can extend
    it to include full table configuration, effective stack, rake profile, and
    precise node identifiers derived from the engine state.

    Attributes:
        hand_key:        Canonical hand identifier, e.g. "AJo".
        node:            Spot identifier within the chart, e.g. "sb_open".
        stack_bb:        Optional effective stack in big blinds.
        hero_position:   Optional logical position label, e.g. "SB", "BB".
        villain_position: Optional opposing position, e.g. "BB".
    """

    hand_key: str
    node: str
    stack_bb: Optional[int] = None
    hero_position: Optional[str] = None
    villain_position: Optional[str] = None
