# RUNBOOK — M0

## Prereqs
- Python 3.10+
- Node 18+
- SQLite 3

## Install

```bash
# Backend
python -m venv .venv && source .venv/bin/activate
pip install -U pip wheel
pip install fastapi uvicorn pydantic sqlite-utils
pip install pokerkit               # primary engine
# Optional QA evaluator:
# pip install phevaluator

# Frontend
cd web && npm ci
```

Configure

Environment (examples):
```bash
export ENGINE=PokerKit
export EVALUATOR=PokerKit      # or HenryRLee
export LOG_DB_PATH=./data/m0.sqlite
# export RNG_SEED=123456
```

If you change ENGINE or EVALUATOR, reset the session.

Run

```bash
# Backend
make api
# or
uvicorn app.main:app --reload

# Frontend
make web
# or
npm run dev --prefix web

```

Open: http://localhost:3000

Usage

Go to Settings, choose seat count & assign Human/Bots, set blinds/stacks/seed.

Click Apply & Play to open Table.

Use action buttons; raise selections snap to fixed buckets.

At hand end, click Next Hand.

Export history from Settings (JSON/CSV), or inspect LOG_DB_PATH (SQLite).

Headless Autoplay (QA)
```bash
# 1,000 hands, PokerKit, logs to SQLite
make autoplay N=1000 ENGINE=PokerKit
```

Troubleshooting

HU order looks off → ensure ENGINE=PokerKit; reset session.

Weird bet sizes → buckets enforced; off-tree sizes snap to nearest legal.

Determinism → set RNG_SEED and reuse the same settings; replays should match bit-for-bit.

Distribution (.zip)

Use make dist to produce a slim .zip with our source only (no vendored third-party).

CI publishes this zip per PR.

On a fresh machine, unzip, create venv, then pip install -r requirements.txt (installs PokerKit, optional phevaluator), and run as above.

---

## `STATE-SCHEMA.md` (updated)
> Remove “PyPokerEngine” from engine field; keep schema stable. Based on your existing schema.

```md
# STATE SCHEMA (Authoritative)

This schema is **engine-agnostic**. Engines must adapt their native state to this structure.

## Top-Level

```json
{
  "game": { ... },
  "players": [ ... ],
  "history": [ ... ]
}
```

game (per hand)
| Field             | Type          | Notes                                                                                             |
| ----------------- | ------------- | ------------------------------------------------------------------------------------------------- |
| hand_id          | string        | Unique hand id (uuid or monotonic).                                                               |
| deck_seed        | string \| int | Seed used to shuffle this hand.                                                                   |
| engine            | string        | `"PokerKit"` (for logs/debug).                                                                    |
| evaluator         | string        | `"PokerKit"` \| `"HenryRLee"` (for logs/debug).                                                   |
| table             | object        | See below.                                                                                        |
| street            | string        | `"preflop" \| "flop" \| "turn" \| "river" \| "showdown"`.                                         |
| community         | string[]     | Board cards (e.g., `["As","Kd",...]`).                                                            |
| pot               | object        | `{"main": int, "sides": [{"amount": int, "eligible_seats": [int,...]}]}`                          |
| to_act           | int \| null   | Seat index or null at showdown/end.                                                               |
| legal_actions    | object        | `{ "can_fold": bool, "can_check": bool, "call_amount": int, "min_raise": int, "max_raise": int }` |
| spr               | number        | Stack-to-pot ratio at street start.                                                               |
| effective_matrix | number[][]  | Effective stacks per (i,j) pair, optional.                                                        |

table
| Field    | Type   | Notes                                                                      |
| -------- | ------ | -------------------------------------------------------------------------- |
| seats    | int    | 2/3/6/9/10                                                                 |
| blinds   | object | `{ "sb": int, "bb": int, "ante": int }`                                    |
| rake     | object | `{ "enabled": bool, "percent": number, "cap": int }` (rake disabled in M0) |
| dealer   | int    | Dealer button seat index                                                   |
| sb_seat | int    | Small blind seat index                                                     |
| bb_seat | int    | Big blind seat index                                                       |

players[] (length = table.seats; empty seats included)
| Field             | Type              | Notes                                                                 |
| ----------------- | ----------------- | --------------------------------------------------------------------- |
| seat              | int               | 0..N-1                                                                |
| kind              | string            | `"human" \| "bot" \| "empty"`                                         |
| profile           | string \| null    | For bots: `"Nit" \| "TAG" \| "LAG" \| "Station"`                      |
| alias             | string            | Display name                                                          |
| stack             | int               | Chips not yet committed                                               |
| committed_street | int               | Chips committed this street                                           |
| committed_total  | int               | Chips committed this hand                                             |
| hole              | string[] \| null | Visible only for human seat during hand; others at showdown per rules |
| status            | string            | `"active" \| "folded" \| "all-in"`                                    |
| position          | string            | `"BTN" \| "SB" \| "BB" \| "UTG" ...` (derived)                        |

history[] (ordered decisions, incl. blinds)
| Field           | Type         | Notes                                                                         |
| --------------- | ------------ | ----------------------------------------------------------------------------- |
| idx             | int          | 0..K-1                                                                        |
| street          | string       | As above                                                                      |
| actor           | int          | Seat index                                                                    |
| action          | string       | `"fold" \| "check" \| "call" \| "bet" \| "raise" \| "all-in" \| "post-blind"` |
| amount          | int\|null    | Chips for bet/raise/call; 0 or null for fold/check                            |
| bucket          | string\|null | Sizing bucket tag (`"B33" \| "B66" \| "BPOT" \| "R2.5x" \| "R3x" \| "JAM"`)   |
| to_call_after | int          | To-call for next player                                                       |
| pot_after      | int          | Pot after this action                                                         |
| time_ms        | int          | (Optional) decision time                                                      |
| rng_trace      | string\|null | Seed/roll log for deterministic replay                                        |
| snapped         | bool         | True if off-tree amount snapped to bucket                                     |
| meta            | object       | Optional map (e.g., board class, flags)                                       |

docs/BET-TREES.md (summary)

Preflop: Opens 2.2/2.5/3×; 3-bet ~3× IP / ~3.5× OOP; 4-bet 2.2–2.5×; 5-bet+ jam.

Postflop: Flop 33/66/100%; Turn 66/100%; River 66/100%; raises ~2.5–3×; jam.

Rounding: bucket → chips; honor min-raise and stacks; mark snapped=true when applied.

```

---

## `TASKS-M0.md` (updated)
> Remove PyPE; add Agent-Mode flow; keep one PR per ticket; CI zip artifact. Based on your existing list.

```md
---
# TASKS — M0

Work ticket-by-ticket. Open **one PR per ticket** with passing CI, updated docs, and tests.

**Agent Mode policy**
- The agent may **proceed to the next ticket** automatically if the current ticket’s PR is open with **green CI** and no blocking review feedback.
- Always **one PR per ticket** (do not batch multiple tickets into one PR).
- Each PR must attach the **slim .zip** artifact (our source only; no vendored third-party).

---

## TASK-01: Repository scaffolding & CI

**Deliver**
- Backend (FastAPI), Frontend (Next.js), `data/` (SQLite), `adapters/`, `docs/`
- CI: lint, format, type-check, unit tests (Py + JS)
- Make targets: `make api`, `make web`, `make test`, `make autoplay`, `make dist` (zip)

**Accept**
- CI green
- Basic “health” endpoint up
- Docs present: M0-SPEC, STATE-SCHEMA, RUNBOOK, QA-CHECKLIST skeleton
- Zip artifact produced in CI

---

## TASK-02: State schema plumbing

**Deliver**
- Pydantic models mirroring `docs/STATE-SCHEMA.md`
- JSON export utility (per hand, per session)
- SQLite schema: sessions, hands, actions (include `engine`, `evaluator`)

**Accept**
```