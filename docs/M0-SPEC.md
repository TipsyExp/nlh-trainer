# M0 SPEC — NLH Training Simulator (Play Mode)

**Objective**: Ship a playable No-Limit Hold’em simulator supporting 2/3/6/9/10-max with:  
- Full hand flow (blinds → streets → showdown)  
- Preflop presets (charts & sizings) by default  
- Basic non-solver bots  
- **Locked** action abstraction (bet-size trees)  
- **Finalized** state schema  
- UI shell (Table + Settings; solver knobs visible but disabled)  
- Deterministic logging/exports

**Out of scope (M0)**: Any solver integration (postflop or preflop), multiway solver approximations, RL.

---

## 1) Architecture (frozen in M0)

- **Engine**: **PokerKit** via a thin Engine Interface.
- **Service**: Single FastAPI backend (no background workers in M0).
- **UI**: Next.js + Tailwind; two pages (Table, Settings).
- **Data**: YAML/CSV for ranges & trees; SQLite for logs (and cache table scaffolding).
- **Determinism**: Seeded RNG; fixed rounding rules; strict min-raise enforcement.

---

## 2) Engine Integration

**Primary**: PokerKit adapter exposes:  
- `start_table(seats, blinds, stacks, seed)`  
- `start_hand()`  
- `next_actor() -> seat, legal_actions, to_call, min_raise`  
- `apply_action(seat, action, amount)`  
- `state() -> schema` (maps to `STATE-SCHEMA.md`)  
- HU order (BTN=SB acts first preflop), dealer rotation, side pots.

**Evaluator** (M0):  
- Default: PokerKit’s builtin evaluator for showdown checks.  
- Optional QA cross-check: HenryRLee via `adapters/evaluator/pheval_adapter.py`.

---

## 3) State Schema (finalized in M0)

See `docs/STATE-SCHEMA.md` (authoritative).  
Key guarantees persisted per decision/hand: legal actions, to-call, min-raise, pot/side pots, action history, RNG seeds, **engine/evaluator** tags.

---

## 4) Bet-Size Trees (locked)

**Preflop**: opens 2.2/2.5/3×; 3-bets (~3× IP / ~3.5× OOP); 4-bets (~2.2–2.5× of 3-bet); 5-bets+ jam.  
**Postflop**: Flop 33/66/100%; Turn 66/100%; River 66/100%; raises ~2.5–3× and jam.  
**Rounding**: snap to nearest legal size honoring min-raise and stack caps; mark “snapped” in logs.

---

## 5) Preflop Presets (charts)

- Organized by seat count (2/3/6/9/10) and position labels.  
- Each entry: action, frequency (0–100%), sizing bucket, optional stack-depth overrides.  
- Range Manager returns weighted actions; off-tree sizes are snapped.

---

## 6) Bots (non-solver)

Profiles: **Nit, TAG, LAG, Station**.  
Heuristics: preflop via presets (+ loosen/tighten), postflop via bins (made/draw/air), board class, SPR rules.  
Knobs: VPIP/PFR, 3-bet %, c-bet %, raise-vs-cbet %, bluff %, fold-to-raise %, sizing mix.  
Randomness: seed-based, small noise. Decisions sub-100ms.

---

## 7) UI

**Table**: table ring + stacks + pot + board; action panel with bucketed sizes; history pane (solver panel hidden).  
**Settings**: seats/bots, ranges/trees, table rules (blinds/antes/rake 0), determinism (seed), solver toggles (disabled), persistence (log path, export).

---

## 8) API (contracts only)

- Session: create/reset table, set seat map/config/seed.  
- Hand: start, submit human action, auto-advance bots, end hand, export history.  
- Config: read/write ranges, bet trees, bot knobs, table rules.  
- Introspection: snapshot, legal actions, min-raise, pot breakdown.  
All payloads adhere to `STATE-SCHEMA.md`.

---

## 9) Persistence & Logging

- **Per decision**: timestamp, hand id, actor, action, size, pot after, legal actions offered, RNG seed.  
- **Per hand**: initial stacks, showdown, winners/amounts, final stacks, export blob.  
- Storage: SQLite + optional JSON/CSV exports; deterministic replays by seed.  
- Record `engine` and `evaluator` used for the hand.

---

## 10) QA

**Acceptance**  
- Full hands playable at 2/3/6/9/10.  
- Preflop presets applied; postflop buckets enforced.  
- Min-raise, all-in & side pots correct.  
- Legal actions/to-call accurate.  
- Hand histories export & replay deterministically.  
- UI separation (no bot knobs on Table).

**Edge Cases**  
- Multiple all-ins and side pots; short-stack jams.  
- Walks across seat configs; HU posting/order correctness.  
- Off-tree sizes (snap); bucket illegalities due to stacks.  
- Card uniqueness; correct visibility/muck rules.

**Non-functional**  
- Smooth UI (60 FPS target).  
- Decisions under 100ms typical.  
- 1,000-hand autoplay (bots) with zero crashes.

---

## 11) Deliverables

- Engine Interface spec  
- State schema doc  
- Bet-size trees doc  
- Preflop charts (YAML/CSV templates)  
- Bot policy doc  
- API contract  
- UI wireframes  
- QA checklist  
- Runbook  
- **Distribution**: CI-produced `.zip` of our source (no vendored third-party code)

---

## 12) Risks & Mitigations

- **Side-pot correctness** → targeted tests + independent calc cross-checks.  
- **Off-tree sizes** → snap + logs.  
- **Seat expansion bugs** → seat-agnostic position resolution.  
- **Chart gaps** → conservative fallback (fold/call) + warnings.  
- **Future engine swap** → stable interface to allow alternatives later.

---

## Definition of Done (M0)

1) Play complete hands at 2/3/6/9/10; export histories.  
2) Preflop presets; postflop buckets enforced.  
3) UI: Table/Settings; knobs only on Settings.  
4) All-in + side-pot resolution correct.  
5) Deterministic replays (same seed/actions).  
6) Docs complete & consistent + ship slim `.zip` artifact.