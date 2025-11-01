from backend.policy.range_manager import get_manager, RangeChoice


def test_load_and_lookup_hu_open():
    m = get_manager()
    dist = m.lookup_distribution(seat_count=2, position="SB", facing="no_raise")
    assert dist is not None
    assert "raise" in dist and isinstance(dist["raise"], dict)
    assert "2.5x" in dist["raise"]


def test_seeded_sampling_is_deterministic():
    m = get_manager()
    a1 = m.choose_action(seat_count=2, position="SB", facing="no_raise", seed="S")
    a2 = m.choose_action(seat_count=2, position="SB", facing="no_raise", seed="S")
    assert isinstance(a1, RangeChoice) and isinstance(a2, RangeChoice)
    # same seed -> identical choice
    assert (a1.action, a1.size_label) == (a2.action, a2.size_label)


def test_missing_entry_falls_back_safely():
    m = get_manager()
    # Non-existent position should fallback
    a = m.choose_action(seat_count=2, position="CO", facing="no_raise", seed="X")
    assert a.source == "fallback"
    assert a.action == "fold" and a.size_label is None

    b = m.choose_action(seat_count=2, position="CO", facing="vs_open_2.5x", seed="X")
    assert b.source == "fallback"
    assert b.action == "call" and b.size_label is None
