from __future__ import annotations

from typing import Any, Dict, List

import pytest

from backend.policy.bot_profiles import CallCheckBot, TagBot
from backend.policy.rng import bot_rng
from backend.policy.range_manager import RangeChoice


# ---------- tiny helpers ----------

def ctx(
    *,
    street: str = "preflop",
    bb: int = 100,
    to_call: int = 0,
    min_raise: int = 200,
    allowed_buckets: List[str] | None = None,
    in_position: bool = False,
    first_action_this_street: bool = False,
    seat: int = 1,
) -> Dict[str, Any]:
    return {
        "seat": seat,
        "street": street,
        "bb": bb,
        "to_call": to_call,
        "min_raise": min_raise,
        "allowed_buckets": list(allowed_buckets or []),
        "in_position": in_position,
        "first_action_this_street": first_action_this_street,
        # extra fields some policies may inspect (harmless defaults)
        "button": 0,
        "sb_seat": 0,
        "bb_seat": 1,
    }


# ---------- CallCheckBot basic behavior ----------

def test_callcheck_policy_checks_when_nothing_to_call() -> None:
    policy = CallCheckBot()
    decision = policy.decide(ctx(street="flop", to_call=0), rng=bot_rng(["seed"]))
    assert decision["action"] == "check"


def test_callcheck_policy_calls_when_facing_bet() -> None:
    policy = CallCheckBot()
    decision = policy.decide(ctx(street="flop", to_call=120), rng=bot_rng(["seed"]))
    assert decision["action"] == "call"


# ---------- TagBot postflop (thin rule) ----------

def test_tag_postflop_ip_uncapped_stabs_with_smallest_nx_bucket() -> None:
    policy = TagBot()
    c = ctx(
        street="flop",
        to_call=0,
        bb=100,
        in_position=True,
        first_action_this_street=True,
        allowed_buckets=["2.2x", "2.5x", "3.0x", "jam"],
    )
    decision = policy.decide(c, rng=bot_rng(["postflop", "stab"]))
    assert decision["action"] == "bet"
    # should choose the *first* simple Nx (smallest) and compute amount = round(N * bb)
    assert decision.get("amount") == 220


def test_tag_postflop_facing_bet_calls() -> None:
    policy = TagBot()
    c = ctx(
        street="flop",
        to_call=120,
        bb=100,
        in_position=True,
        first_action_this_street=False,
        allowed_buckets=["call", "2.5xR", "3.0xR", "jam"],
    )
    decision = policy.decide(c, rng=bot_rng(["postflop", "call"]))
    assert decision["action"] == "call"


def test_tag_postflop_oop_checks_when_to_call_zero() -> None:
    policy = TagBot()
    c = ctx(
        street="flop",
        to_call=0,
        bb=100,
        in_position=False,
        first_action_this_street=True,
        allowed_buckets=["2.2x", "2.5x", "3.0x", "jam"],
    )
    decision = policy.decide(c, rng=bot_rng(["postflop", "oop"]))
    assert decision["action"] == "check"


# ---------- TagBot preflop (range-driven) ----------
#
# We don't rely on on-disk YAML fixtures in this thin test. Instead we
# monkeypatch the range manager singleton to return a desired RangeChoice.

class _DummyMgr:
    def __init__(self, choice: RangeChoice) -> None:
        self.choice = choice

    def choose_action(self, *args, **kwargs) -> RangeChoice:  # type: ignore[no-untyped-def]
        return self.choice


@pytest.mark.parametrize(
    "size_label,allowed,expected_amount",
    [
        ("2.5x", ["2.2x", "2.5x", "3.0x"], 250),  # exact hit
        ("3.5x", ["2.2x", "2.5x", "3.0x"], 300),  # snap DOWN to nearest allowed (3.0x)
    ],
)
def test_tag_preflop_raise_respects_or_snaps_bucket(monkeypatch, size_label, allowed, expected_amount) -> None:
    # Arrange the range manager to request a RAISE with given size_label
    from backend.policy import range_manager as rm

    monkeypatch.setattr(rm, "get_manager", lambda: _DummyMgr(RangeChoice("raise", size_label, "chart")))
    policy = TagBot()

    c = ctx(
        street="preflop",
        to_call=0,  # opening scenario
        bb=100,
        allowed_buckets=allowed,
    )

    # Act
    decision = policy.decide(c, rng=bot_rng(["preflop", "raise"]))

    # Assert
    assert decision["action"] in ("bet", "raise")  # depending on implementation name for open
    assert decision.get("amount") == expected_amount


def test_tag_preflop_missing_chart_fallback_calls(monkeypatch) -> None:
    # Arrange: range manager returns a fallback CALL (e.g., chart missing)
    from backend.policy import range_manager as rm

    monkeypatch.setattr(rm, "get_manager", lambda: _DummyMgr(RangeChoice("call", None, "fallback")))
    policy = TagBot()

    c = ctx(
        street="preflop",
        to_call=100,          # facing an open
        bb=100,
        allowed_buckets=["call", "2.5xR", "3.0xR", "jam"],
    )

    decision = policy.decide(c, rng=bot_rng(["preflop", "fallback"]))
    assert decision["action"] == "call"


# ---------- RNG helper determinism ----------

def test_bot_rng_deterministic_same_components() -> None:
    r1 = bot_rng(["a", 1, "H1", 0, 2, "bot"])
    r2 = bot_rng(["a", 1, "H1", 0, 2, "bot"])
    # draw a short sequence and ensure equality
    seq1 = [r1.random() for _ in range(5)]
    seq2 = [r2.random() for _ in range(5)]
    assert seq1 == seq2


def test_bot_rng_changes_when_any_component_changes() -> None:
    base = ["a", 1, "H1", 0, 2, "bot"]
    r_base = bot_rng(base)
    r_diff = bot_rng(base[:-1] + ["coach"])  # last component changed
    # extremely unlikely to match 5 draws exactly unless seeded the same
    assert [r_base.random() for _ in range(5)] != [r_diff.random() for _ in range(5)]
