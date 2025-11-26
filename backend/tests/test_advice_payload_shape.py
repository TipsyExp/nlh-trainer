# backend/tests/test_advice_payload_shape.py
from __future__ import annotations

from dataclasses import fields, is_dataclass

from backend.coach.schemas import AdvicePayloadV1, EquityAnnotation


def test_equity_annotation_dataclass_and_fields() -> None:
    # Should be a dataclass
    assert is_dataclass(EquityAnnotation)

    # Should have these core fields
    names = {f.name for f in fields(EquityAnnotation)}
    assert "hero_vs_villain_equity" in names
    assert "pot_odds" in names
    assert "min_equity_to_call" in names
    # Comment is nice to have but we don't hard-require any particular name here.


def test_advice_payload_v1_dataclass_minimum_shape() -> None:
    # Should be a dataclass
    assert is_dataclass(AdvicePayloadV1)

    names = {f.name for f in fields(AdvicePayloadV1)}

    # We keep this intentionally loose so schema can evolve
    for required in ("street", "recommendation", "source"):
        assert required in names
