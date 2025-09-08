# CONFIGURATION

This app is a local, single-user training simulator for No-Limit Hold’em (M0).
We keep third-party engines/evaluators/solvers **outside** our repo and talk to them via adapters.

---

## 1) Environment Variables (runtime switches)

| Key            | Values                 | Default     | Notes |
|----------------|------------------------|-------------|-------|
| ENGINE         | `PokerKit`             | `PokerKit`  | Primary gameplay engine (wrapped behind our Engine Interface). |
| EVALUATOR      | `PokerKit` \| `HenryRLee` | `PokerKit`  | Showdown/equity sanity; M0 uses lightweight eval only. |
| TEXASSOLVER_PATH | absolute path        | *(unset)*   | **M1+ only**. Local path to user-provided TexasSolver binary. |
| LOG_DB_PATH    | file path              | `./data/m0.sqlite` | SQLite log path. |
| RNG_SEED       | integer                | random      | Seed for deterministic replays. |

> Note: We **do not** support PyPokerEngine in M0.

---

## 2) Engines

Engines are **plug-ins** under `adapters/engines/*`.

### Primary: PokerKit
- Install (runtime): `pip install pokerkit`
- Adapter: `adapters/engines/pokerkit_adapter.py`
- Mode: `ENGINE=PokerKit`
- Why: modern, maintained, builtin evaluator, deterministic.

---

## 3) Evaluators

### Default: PokerKit evaluator
- Ships with PokerKit, no extra setup.
- Used for showdown and sanity checks.

### Optional: HenryRLee
- Install: `pip install phevaluator`
- Adapter: `adapters/evaluator/pheval_adapter.py`
- Mode: `EVALUATOR=HenryRLee`
- Use in M0: QA cross-checks / fast sampling (not for decisions).

---

## 4) TexasSolver (M1+ only; **not used in M0**)

We **do not** bundle TexasSolver (AGPL). End-users point the adapter to a local binary.

- Env: `TEXASSOLVER_PATH=/abs/path/to/TexasSolver/bin/TexasSolver`
- In M0, the solver adapter is stubbed and never invoked.
- See `docs/LICENSING-NOTES.md` and `docs/THIRD-PARTY-INTEGRATION.md`.

---

## 5) Frontend/Backend

- Backend: FastAPI + Pydantic
- Frontend: Next.js + Tailwind
- Logs/Cache: SQLite (`LOG_DB_PATH`), optional JSON/CSV export.

---

## 6) Determinism

- Set `RNG_SEED` to reproduce deals + bot randomization.
- “Re-deal same hand” uses the stored per-hand seed from logs.

---

## 7) Distribution (.zip) policy

- The CI produces a **slim .zip** artifact containing **our source only** (no vendored third-party code).
- Third-party components (PokerKit, phevaluator) are installed at runtime via `pip`, or skipped in “base” smoke tests that don’t require them.
- Include lockfiles / requirements for reproducible installs.