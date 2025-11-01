from backend.adapters.engines import get_adapter
from backend.models.state import Street


def _setup_hu():
    eng = get_adapter()
    eng.start_table(
        seats=2, sb=50, bb=100, ante=0, stacks=[10000, 10000], base_seed="A"
    )
    eng.start_hand()
    return eng


def _setup_6max():
    eng = get_adapter()
    eng.start_table(seats=6, sb=50, bb=100, ante=0, stacks=[10000] * 6, base_seed="B")
    eng.start_hand()
    return eng


def test_hu_actor_order():
    eng = _setup_hu()
    a = eng.next_actor()
    # SB acts first preflop
    assert a["seat"] == eng.state().table.sb_seat
    # Make preflop progress to postflop
    eng.apply_action(a["seat"], "call")
    a = eng.next_actor()
    eng.apply_action(a["seat"], "check")
    s = eng.state()
    # On flop, BB acts first in HU (first active left of button)
    assert s.street in (Street.flop, Street.turn, Street.river, Street.showdown)


def test_dealer_rotation_hu():
    eng = _setup_hu()
    first_button = eng.state().table.button
    # Play a minimal hand to completion (both check/call down)
    # NOTE: exact sequence may vary; just make sure the hand advances:
    for _ in range(3):  # preflop -> flop -> turn -> river -> showdown
        a = eng.next_actor()
        if a["to_call"] > 0:
            eng.apply_action(a["seat"], "call")
        else:
            eng.apply_action(a["seat"], "check")
    # Close remaining streets quickly
    for _ in range(6):
        a = eng.next_actor()
        if a.get("seat") is None:
            break
        if a["to_call"] > 0:
            eng.apply_action(a["seat"], "call")
        else:
            eng.apply_action(a["seat"], "check")

    # Start next hand; button must rotate
    eng.start_hand()
    second_button = eng.state().table.button
    assert second_button == (first_button + 1) % 2


def test_6max_blinds_and_utg_acts():
    eng = _setup_6max()
    s = eng.state()
    assert s.table.bb_seat == (s.table.sb_seat + 1) % 6
    # UTG acts first preflop (left of BB)
    utg = (s.table.bb_seat + 1) % 6
    assert eng.next_actor()["seat"] == utg


def test_determinism_same_seed_same_deal():
    eng1 = get_adapter()
    eng1.start_table(2, 50, 100, 0, [10000, 10000], "seed-DET")
    eng1.start_hand()
    s1 = eng1.state()
    holes1 = [p.hole_cards[:] for p in s1.players]

    eng2 = get_adapter()
    eng2.start_table(2, 50, 100, 0, [10000, 10000], "seed-DET")
    eng2.start_hand()
    s2 = eng2.state()
    holes2 = [p.hole_cards[:] for p in s2.players]

    assert holes1 == holes2
