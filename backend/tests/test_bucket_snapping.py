from backend.adapters.engines import get_adapter


def test_preflop_raise_snaps_to_bucket():
    eng = get_adapter()
    eng.start_table(2, 50, 100, 0, [10000, 10000], "S")
    eng.start_hand()

    a = eng.next_actor()
    assert "allowed_buckets" in a and isinstance(a["allowed_buckets"], list)

    # Request between 2.2x (220) and 2.5x (250) -> should snap to 2.5x
    eng.apply_action(a["seat"], "raise", amount=240)

    s = eng.state()
    assert s.last_action is not None
    assert s.last_action.snapped is True
    assert s.last_action.bucket_label == "2.5x"
    assert s.last_action.committed == 250
