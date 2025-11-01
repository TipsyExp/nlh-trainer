from backend.adapters.engines import get_adapter


def _setup():
    eng = get_adapter()
    eng.start_table(2, 50, 100, 0, [10000, 10000], "S")
    eng.start_hand()
    return eng


def test_allowed_buckets_exposed_on_actor():
    eng = _setup()
    a = eng.next_actor()
    assert isinstance(a.get("allowed_buckets"), list)
    # Should include preflop open labels when to_call>0 for SB in HU:
    # (Our minimal engine sets to_call=50 for SB; labels exist nonetheless)
    assert any(lbl in a["allowed_buckets"] for lbl in ("2.2x", "2.5x", "3x", "jam"))
