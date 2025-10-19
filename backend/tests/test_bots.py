from backend.policy.bots import choose_preflop_action, BotContext, NIT, TAG, LAG, STATION

def test_seeded_is_deterministic():
    ctx = BotContext(seat_count=2, position="SB", facing="no_raise", seed="S")
    a1 = choose_preflop_action(ctx, TAG)
    a2 = choose_preflop_action(ctx, TAG)
    assert (a1.action, a1.size_label, a1.source) == (a2.action, a2.size_label, a2.source)

def test_style_knobs_affect_raise_rate():
    ctx = BotContext(seat_count=2, position="SB", facing="no_raise", seed="S")
    # Sample a bunch of seeds to approximate raise frequency difference
    def count_raises(profile):
        r = 0
        for i in range(50):
            c = BotContext(seat_count=2, position="SB", facing="no_raise", seed=f"S{i}")
            a = choose_preflop_action(c, profile)
            if a.action == "raise":
                r += 1
        return r
    lag_raises = count_raises(LAG)
    nit_raises = count_raises(NIT)
    assert lag_raises > nit_raises  # LAG should raise more often than NIT

def test_fallback_policy():
    ctx_missing = BotContext(seat_count=2, position="CO", facing="no_raise", seed="X")
    a = choose_preflop_action(ctx_missing, TAG)
    assert a.source == "fallback" and a.action == "fold" and a.size_label is None

    ctx_missing2 = BotContext(seat_count=2, position="CO", facing="vs_open_2.5x", seed="X")
    b = choose_preflop_action(ctx_missing2, TAG)
    assert b.source == "fallback" and b.action == "call" and b.size_label is None
