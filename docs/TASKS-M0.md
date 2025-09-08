---

# TASKS-M0.md
```md
# TASKS — M0

Work ticket-by-ticket. Open **one PR per ticket** with passing CI, updated docs, and tests.

---

## TASK-01: Repository scaffolding & CI

**Deliver**
- Backend (FastAPI), Frontend (Next.js), `data/` (SQLite), `adapters/`, `third_party/`, `docs/`
- CI: lint, format, type-check, unit tests (Py + JS)
- Make targets: `make api`, `make web`, `make test`, `make autoplay`

**Accept**
- CI green
- Basic “health” endpoint up
- Docs present: M0-SPEC, STATE-SCHEMA, RUNBOOK, QA-CHECKLIST skeleton

---

## TASK-02: State schema plumbing

**Deliver**
- Pydantic models that mirror `docs/STATE-SCHEMA.md`
- JSON export utility (per hand, per session)
- SQLite schema: sessions, hands, actions (include `engine`, `evaluator`)

**Accept**
- Round-trip: build state → JSON → import → identical
- Deterministic seed stored per hand

---

## TASK-03: Engine Interface (PokerKit primary; PyPE optional)

**Deliver**
- PokerKit adapter: `start_table`, `start_hand`, `next_actor`, `apply_action`, `state`
- HU order correctness (BTN=SB acts first preflop; invert postflop)
- Dealer rotation, blinds/antes, side pots
- Optional: PyPokerEngine adapter with same interface for smoke tests

**Accept**
- HU and 6-max hands play end-to-end (stepper mode)
- Optional PyPE parity smoke (pot/winner invariants)

---

## TASK-04: Action abstraction (bet-size trees)

**Deliver**
- Enforce preflop raises (2.2/2.5/3×; 3-bet ~3× IP / ~3.5× OOP; 4-bet ~2.2–2.5×; ≥5-bet jam)
- Postflop buckets (Flop 33/66/100; Turn 66/100; River 66/100; raises ~2.5–3×; jam)
- Snapping logic + `snapped: true` flag

**Accept**
- All actions adhere to buckets or jam
- Illegal sizes snap correctly; min-raise enforced

---

## TASK-05: Preflop Range Manager

**Deliver**
- YAML/CSV loader for presets by seat count / position / stack depth
- Lookup API: given context (position, facing action bucket) → weighted actions + size tag
- Fallback policy with warnings

**Accept**
- Charts drive bot preflop; weights honored with seeded RNG
- Missing entries fallback safely (fold/call) with logs

---

## TASK-06: Bots (heuristic)

**Deliver**
- Profiles: Nit, TAG, LAG, Station with knobs (VPIP/PFR, 3-bet %, c-bet %, bluff %, fold-to-raise %, sizing mix)
- Postflop bins (made/draw/air + board class), SPR-aware aggression
- Deterministic randomness (seeded)

**Accept**
- Decisions sub-100ms
- Style knobs visibly change behavior in scripted scenarios

---

## TASK-07: Backend API

**Deliver**
- Session: create/reset, set seats/config/seed
- Hand: start, accept human action, auto-advance bots to next human point/end
- Introspection: snapshot, legal actions, min-raise, pot breakdown
- Export endpoints (JSON/CSV)

**Accept**
- End-to-end play from frontend with single human seat

---

## TASK-08: Frontend UI

**Deliver**
- **Settings** page: seats/bots, ranges/trees (view), blinds/antes/stacks, seed, solver settings (disabled), export controls
- **Table** page: table ring, stacks, pot, board, action panel with bucketed sizes, action history
- Solver panel placeholder hidden

**Accept**
- UX smooth (60 FPS target), visible min-raise/to-call, bucketed raise UI

---

## TASK-09: Logging & Determinism

**Deliver**
- SQLite writes: per-decision + per-hand (include `engine`, `evaluator`, RNG trace)
- Re-deal with same seed
- JSON/CSV export

**Accept**
- Deterministic replay test suite passes
- Hand export/import round-trips

---

## TASK-10: QA & Edge Cases

**Deliver**
- Targeted tests: multiple all-ins, side pots, walks, short-stack non-reopening raises, HU posting/order, off-tree snaps, card uniqueness, visibility rules
- 1,000-hand autoplay script (bots-only)

**Accept**
- All acceptance tests pass
- Autoplay finishes with zero crashes; latency within targets

---

## TASK-11: Docs polish

**Deliver**
- M0-SPEC, API-CONTRACT, STATE-SCHEMA, BET-TREES, RANGE-FILE-FORMAT, BOT-POLICY, QA-CHECKLIST, RUNBOOK, THIRD-PARTY-INTEGRATION, LICENSING-NOTES
- Wireframes for Table/Settings

**Accept**
- Docs complete & consistent; repo is self-serve for new devs

```