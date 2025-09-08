# State Schema (Authoritative)

## Types
- **SeatIndex**: int (0..N-1)
- **Chips**: int (smallest unit)
- **Card**: string `"As" | "Td" | ...`
- **Street**: `"preflop" | "flop" | "turn" | "river" | "showdown" | "complete"`
- **ActionType**: `"post_blind" | "fold" | "check" | "call" | "bet" | "raise" | "all_in" | "deal"`
- **SeatType**: `"human" | "bot" | "empty"`
- **PlayerStatus**: `"active" | "folded" | "all_in"`
- **Position**: `"BTN" | "SB" | "BB" | "UTG" | "UTG1" | "MP" | "HJ" | "CO"` (derived by seat count)
- **BucketTag**: e.g., `"OPEN_2.5x"`, `"B33"`, `"B66"`, `"BPOT"`, `"R3x"`, `"R2.5x"`, `"JAM"`

## Root (per hand)
```json
{
  "hand_id": "string",
  "deck_seed": "string",
  "table": {
    "seat_count": 6,
    "sb": 50,
    "bb": 100,
    "ante": 0,
    "rake": { "enabled": false, "type": "none" }
  },
  "dealer_seat": 2,
  "sb_seat": 3,
  "bb_seat": 4,
  "street": "flop",
  "community": {
    "preflop": [],
    "flop": ["Ah","7d","2c"],
    "turn": ["Tc"],
    "river": ["2h"]
  },
  "pots": {
    "main": 4200,
    "sides": [
      { "size": 1200, "contestants": [1,4] }
    ]
  },
  "players": [/* array of PlayerState */],
  "to_act": 5,
  "legal_actions": {
    "can_fold": true,
    "can_check": false,
    "to_call": 500,
    "min_raise_to": 1000,
    "allowed_buckets": ["R3x","JAM"]
  },
  "spr": 5.2,
  "effective_stacks": [
    /* matrix or list:
       { "a":0,"b":1,"effective": 8900 }, ... */
  ],
  "action_history": [/* array of ActionRecord */]
}
```

### PlayerState
```json
{
  "seat": 4,
  "type": "bot",
  "alias": "LAG_4",
  "stack": 9800,
  "stack_bb": 98.0,
  "committed_street": 500,
  "committed_total": 1200,
  "status": "active",
  "position": "CO",
  "hole_cards": ["9s","9c"] // null for opponents until showdown
}
```

### ActionRecord
```json
{
  "idx": 7,
  "street": "flop",
  "actor_seat": 4,
  "type": "bet",
  "amount": 500,
  "bucket": "B33",
  "to_call_after": 500,
  "pot_after": 1800,
  "time_ms": 42,
  "rng_seed": "m0:hand123:act7"
}
```

---

## docs/BET-TREES.md

```md
# Bet-Size Trees (Locked in M0)

## Preflop
- **Opens** (per position): choose one baseline per position from { **2.2×**, **2.5×**, **3×** }.
- **3-bets**: ~**3×** vs open when IP; ~**3.5×** when OOP.
- **4-bets**: **2.2–2.5×** of 3-bet.
- **5-bets+**: **jam** unless a fixed % bucket is explicitly configured (optional; default jam).
```