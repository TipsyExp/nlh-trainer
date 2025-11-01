from backend.policy.bet_buckets import BucketContext, allowed_sizes, snap_size


def test_preflop_open_sizes():
    ctx = BucketContext(
        street="preflop",
        to_call=0,
        min_raise_to=None,
        pot=0,
        bb=100,
        actor_stack=20000,
        already_committed=0,
    )
    labels = [b.label for b in allowed_sizes(ctx)]
    assert labels[:3] == ["2.2x", "2.5x", "3x"]
    assert labels[-1] == "jam"


def test_flop_bet_snap_down_to_66():
    ctx = BucketContext(
        street="flop",
        to_call=0,
        min_raise_to=None,
        pot=300,
        bb=100,
        actor_stack=20000,
        already_committed=0,
    )
    # request ~0.8 pot total
    tgt, snapped, label = snap_size(240, ctx)  # 0.8 * 300 = 240
    assert snapped is True
    assert label == "66%"


def test_raise_buckets_include_jam():
    ctx = BucketContext(
        street="turn",
        to_call=100,
        min_raise_to=200,
        pot=500,
        bb=100,
        actor_stack=1500,
        already_committed=0,
    )
    labels = [b.label for b in allowed_sizes(ctx)]
    assert "jam" in labels
