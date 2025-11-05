from __future__ import annotations

from backend.coach.node_key import make_node_key


def test_node_key_stable_and_order_independent() -> None:
    k1 = make_node_key(
        street="flop",
        pot=300,
        board=["As", "7d", "Tc"],
        ip=True,
        pot_type="srp",
        stp=2.3456,
        bucket_slice="b33",
    )
    k2 = make_node_key(
        street="FLOP",
        pot=300,
        board=["tc", "AS", "7D"],  # different order/case
        ip=True,
        pot_type="SRP",
        stp=2.3456,
        bucket_slice="b33",
    )
    assert k1 == k2
    assert "IP" in k1
    assert k1.split("|")[0] == "flop"


def test_node_key_rounding_3dp() -> None:
    k = make_node_key(
        street="turn",
        pot=123,
        board=["Ah", "Kd", "2s", "2c"],
        ip=False,
        pot_type="3BP",
        stp=1.666666,
        bucket_slice="b50",
    )
    assert "1.667" in k
