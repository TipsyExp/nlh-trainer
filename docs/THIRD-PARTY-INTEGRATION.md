# THIRD-PARTY INTEGRATION

We keep upstreams “on top” of our codebase and integrate via thin, swappable adapters. We **do not vendor** external sources into this repository; builds install dependencies at runtime and binaries (when required) are supplied by the user.

---

## Upstreams

- **PokerKit** — <https://github.com/uoftcprg/pokerkit> (GPL-3.0-or-later)  
  Used as the default heads-up engine in M0/M1.

- **HenryRLee / PokerHandEvaluator** — <https://github.com/HenryRLee/PokerHandEvaluator> (Apache-2.0)  
  Optional hand evaluator (not required for core flow).

- **TexasSolver** — <https://github.com/bupticybee/TexasSolver> (AGPL-3.0) *(planned M1+)*  
  External solver used only when “Coach” is enabled. **Not** bundled; user provides local binary.

---

## Adapter Layout

adapters/
engines/
pokerkit_adapter.py # default engine (M0/M1)
evaluator/
pheval_adapter.py # optional evaluator shim (if used)
solver/
texassolver_adapter.py # planned (M1+), gated behind env flags


> There is **no** `third_party/` source vendoring in this repo. Adapters call upstream libraries/binaries via public APIs/CLIs.

---

## Install Modes

- **PokerKit** → `pip install pokerkit`
- **phevaluator** (optional) → `pip install phevaluator`
- **TexasSolver** (M1+) → User supplies a **local executable** and points the app at it:
  - `COACH_ENABLED=true`
  - `TEXASSOLVER_PATH=/absolute/path/to/texassolver`

If `COACH_ENABLED=false` (default), all coach/solver paths are inert and the app runs without TexasSolver.

---

## Environment Gating (Coach | planned M1+)

- `COACH_ENABLED` — default **false**. When **true**, coach endpoints/logic are wired.
- `TEXASSOLVER_PATH` — absolute path to the solver binary; required iff `COACH_ENABLED=true`.
- (Future) Cache controls:
  - `COACH_CACHE_MAX_ROWS` (default: 5000)
  - `COACH_CACHE_TTL_DAYS` (default: 30)

When gating conditions are not met (e.g., missing binary), coach endpoints should return **501 Not Implemented**.

---

## Compatibility Smoke (M0)

Baseline engine sanity checks (run in CI):

- **PokerKit**: deal N hands across seat counts (2/3/6/9/10); verify blinds order, button rotation, and side-pot accounting against golden expectations.

---

## Distribution (Slim .zip)

- CI publishes a **slim source archive** (see `DIST-CONTENTS.md` and `tools/build_dist.py`).
- No vendored upstream sources; no solver binaries.
- After unzip: `pip install -r requirements.txt` to fetch Python deps.

---

## Licensing Posture

- Adapters-only policy: we integrate via adapters and **do not** redistribute upstream sources/binaries.
- See `docs/LICENSING-NOTES.md` for details on GPL/AGPL exposure and how gating keeps the default build clean.
