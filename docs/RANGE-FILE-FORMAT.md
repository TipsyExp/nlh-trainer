# Preflop Preset Format

You may supply **YAML** or **CSV**. YAML is recommended for readability.

## YAML structure (per seat count)
```yaml
metadata:
  seat_count: 6
  stack_bb: [100]  # optional variants

positions:
  UTG:
    opens:
      - hands: ["AA","KK","QQ","AKs"]
        freq: 1.0
        size: "OPEN_2.5x"
      - hands: ["JJ","TT","AQs","AJs","KQs"]
        freq: 0.8
        size: "OPEN_2.5x"
    vs_open: {}   # (optional)
    vs_3bet: {}   # (optional)

  MP:
    opens:
      - hands: ["AA-99","AKs-AJs","KQs-KJs","AQo"]
        freq: 1.0
        size: "OPEN_2.5x"
  CO: { ... }
  BTN: { ... }
  SB:  { ... }
  BB:  { ... }

Conventions
    hands supports ranges: AA-99, suited AKs, offsuit AQo, groups A5s-A2s, or full combos like AsKd (rare; use only if needed).
    freq: 0.0–1.0 (mix). Engine will sample with seeded RNG.
    size: must be a valid bucket tag from BET-TREES.md.

Optional stack overrides:
overrides:
  "40bb":
    BTN:
      opens:
        - hands: ["ATo-AQo","KJo-KQo"]
          freq: 0.5
          size: "OPEN_2.2x"
```

## CSV alternative
```
seat_count,position,spot,hands,freq,size,stack
6,BTN,open,"AA-22, AKs-A2s, AKo-ATo, KQs-KTs",1.0,OPEN_2.2x,100
6,SB,vs_open,"TT-88, AQs-ATs",0.6,R3.5x,100
```

Runtime rules
    If a mapping is missing, fallback conservatively (fold>call) and log a warning.
    Any off-tree sizes observed must be snapped to the nearest configured bucket before lookup.

---

## docs/API-CONTRACT.md

```md
# API Contract (M0)

> All payloads conform to `STATE-SCHEMA.md`. No solver endpoints in M0.

## Session
### POST /api/session
Create/reset a table.
```json
{
  "seat_count": 6,
  "sb": 50, "bb": 100, "ante": 0,
  "stacks": [10000,10000,10000,10000,10000,10000],
  "seats": [
    {"type":"human","alias":"Hero"},
    {"type":"bot","alias":"Bot_2","profile":"TAG"}, ...
  ],
  "seed": "m0:2025-08-27"
}

200 → current state snapshot.

GET /api/state

Return current state snapshot.

Hand control
POST /api/hand/start

Start a new hand (deal, post blinds).
200 → state at first decision.

POST /api/action
Apply a human action.
{ "seat": 0, "type": "raise", "bucket": "B66" /* or "amount": 400 */ }
    Backend enforces bucket snapping & legality.
    200 → state advanced to next human decision or hand end.


POST /api/hand/next

Advance to next hand (after hand end).
200 → state at first decision.

Config
GET /api/config/ranges

List available range sets (by seat count/depth).

POST /api/config/ranges

Select/upload a range set.

GET /api/config/bots

Get bot knobs per seat.

POST /api/config/bots

Update bot knobs (persist for next hand).

POST /api/config/table

Update blinds/antes/stacks (apply on next hand).

Introspection
GET /api/introspect/legal

Current legal actions (to_call, min_raise_to, allowed_buckets).

Export
GET /api/export/hand/{hand_id}

Export single hand (JSON or text).

GET /api/export/session

Export session (JSON/CSV).

Errors
    400 illegal action or invalid bucket.
    409 wrong turn / race detected.
    422 schema validation failed.

```

---

## docs/QA-CHECKLIST.md

```md
# QA Checklist — M0

## Functional
- [ ] Full hand play-through for 2/3/6/9/10-max.
- [ ] HU blind rule: BTN posts SB; preflop SB acts first; postflop BTN acts last.
- [ ] Min-raise enforcement & re-opening rules correct.
- [ ] Buckets enforced; off-tree inputs snapped & logged.
- [ ] Side pots: 3p/4p multi-all-in scenarios distribute correctly.
- [ ] Walks (uncontested blinds) for each seat config.
- [ ] Export hand history; re-import or replay produces same result.
- [ ] UI: Table/Settings separation; knobs only on Settings.

## Determinism
- [ ] Same seed + same human actions ⇒ identical outcomes (deck, actions, pots).
- [ ] RNG seeds logged per decision.

## Non-functional
- [ ] Bot decisions <100 ms typical.
- [ ] 1,000-hand autoplay (bots-only) completes with zero crashes.
- [ ] UI smooth (no jank); action animations readable.

## Edge cases
- [ ] Short-stack jams; insufficient raises don’t reopen betting.
- [ ] Off-tree preflop sizes snapped, then tree stays consistent postflop.
- [ ] Dead blinds when seats empty.
- [ ] Correct card visibility; unique burns; no duplicate cards.

## Sign-off
- [ ] DoD items in `M0-SPEC.md` verified.
- [ ] Docs updated (API, schema, bet-trees, range format, runbook).

```