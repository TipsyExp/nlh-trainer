# TASKS — M1

Milestone M1: **Coach Bootstrap (Small, Solid, Testable)**

**Change order:** Complete **TASK-12 → TASK-15** first (M0 carryovers), then **TASK-16 → TASK-20** (Coach work).

---

## Goals

- Wire a local solver (TexasSolver) behind a strict adapter.
- Show advice at the table with caching so it’s fast after the first call.
- Let you autoplay hands vs heuristic bots using solver advice (to verify EV sanity).
- Add a simple Review page to inspect what happened when results look odd.
- Keep CI green with solver disabled (no binary in CI).
- **Carryover:** Finish M0 gaps (per-decision logging, JSON/CSV exports, docs, slim dist).

---

## TASK-12 (M1): Per-Action Logging + Export Endpoints
**Deliver**
- Implement per-decision SQLite writes during play (`actions` table): street, actor, amounts, bucket, `snapped`, RNG trace, `engine`, `evaluator`.
- Export API:
  - `GET /api/export/hand/{hand_id}.json`
  - `GET /api/export/hand/{hand_id}.csv`
  - `GET /api/export/session/{session_id}.json`
  - `GET /api/export/session/{session_id}.csv`
- Deterministic round-trip test: export → import → replay ⇒ identical state.

**Accept**
- Per-decision rows present for completed hands.
- All four export endpoints return correct payloads; CSV headers stable and documented.
- Round-trip determinism test passes.

---

## TASK-13 (M1): Documentation Completion & Alignment
**Deliver**
- `docs/API-CONTRACT.md` with every endpoint, params, and **example requests/responses** (incl. export endpoints).
- `docs/BET-TREES.md` (bucket definitions, snapping, min-raise) and `docs/BOT-POLICY.md` (profiles, knobs, examples).
- Update `docs/QA-CHECKLIST.md` to reflect current coverage (link to tests).
- Verify `docs/STATE-SCHEMA.md` matches Pydantic models; `docs/RUNBOOK.md` includes export & replay steps.

**Accept**
- Docs complete & consistent; examples match live API responses.
- QA checklist marks covered items with references to tests.

---

## TASK-14 (M1): Slim Distributable & Dependency Hygiene
**Deliver**
- Update `make dist` to **exclude**: `third_party/`, `.venv/`, caches, test artifacts, large binaries (use allowlist).
- Remove unused PyPokerEngine from `requirements.txt`; prune leftovers.
- Add `DIST-CONTENTS.md` listing what’s included/excluded and why.
- Fresh venv install + `make autoplay N=100` works headless with PokerKit.

**Accept**
- Dist zip contains only project code (no vendored third-party).
- Clean install succeeds; headless autoplay completes 100 hands without crash.

---

## TASK-15 (M1): CI Guards for Carryovers
**Deliver**
- CI jobs:
  - Test per-decision logging path (at least one full hand asserts `actions` rows).
  - Export endpoints contract tests (JSON/CSV shape & sample fixtures).
  - Packaging check: fail if `third_party/` or `.venv/` appear in dist.
  - Doc check: examples in `API-CONTRACT.md` validated against running API (golden/contract test).
- Keep COACH gated; CI must pass with `COACH_ENABLED=false`.

**Accept**
- CI green; contract & packaging checks enforced.
- No regressions to logging/exports/docs.

---

## TASK-16 (M1): TexasSolver Adapter (Limited Spots)
**Deliver**
- `adapters/solver/texassolver_adapter.py`
  - Env gate: `COACH_ENABLED=true` and `TEXASSOLVER_PATH=/abs/path/.../TexasSolver`
  - Support HU postflop:
    - Single-raised pots (SRP)
    - 3-bet pots
  - Input: canonical node (board, stacks, pot, positions, last aggressor, bucket tree slice)
  - Output: `{ recommended_bucket, strategy: {fold/call/buckets…}, ev_map }`
- `backend/coach/node_key.py` — pure function to hash a state into a stable `node_key`
- `backend/coach/cache.py` — get/set via SQLite (see Task-18 schema)
- Unit tests with golden string parsing (uses saved solver output)
- CI behavior: if `COACH_ENABLED!=true` or binary missing → return `UnsupportedSpot` or `CoachDisabled` (HTTP 501 at API)

**Accept**
- Adapter returns structured payload for supported HU spots.
- Graceful fallback for unsupported ones.
- Tests pass without solver present (skip/golden-based).

---

## TASK-17 (M1): Coach API + UI Overlay
**Deliver**
- API:
  - `GET /api/coach/advice?hand_id=H123&idx=7` → returns advice (or 501 if disabled/unsupported)
  - `POST /api/coach/test_solve` (for dev/testing; same response shape)
- Persist snapshot of advice per decision (only if `COACH_ENABLED=true`):
  - Extend actions table with `advice_json` or add new table `coach_advice(hand_id, idx, advice_json)`
- Frontend:
  - Coach toggle on Table page
  - Minimal Coach panel: top bucket + strategy bar + EV delta
  - If disabled/unsupported → show badge: “Coach: off / unsupported”

**Accept**
- Toggle works.
- Advice logs with hands if enabled.
- CI green when solver off (API returns 501, UI hides panel).

---

## TASK-18 (M1): Solver Cache (SQLite)
**Deliver**
- DB table: `solver_cache(node_key TEXT PRIMARY KEY, payload_json TEXT, created_at TEXT)`
- TTL / LRU policy (via env):
  - `COACH_CACHE_MAX_ROWS=5000`
  - `COACH_CACHE_TTL_DAYS=30`
- Cache layer wraps adapter (read-through / write-through)
- Optional script: `backend/scripts/warm_cache.py --preset hu_srp --boards 50 --spr 20,40`

**Accept**
- Identical nodes hit cache (log "cache hit").
- Migration doesn't break M0 logs.
- Unit tests: write/read path + TTL eviction.

---

## TASK-19 (M1): Review Page (Minimal)
**Deliver**
- `/review` route:
  - List recent hands from SQLite (hand_id, seats, final pot, winner summary)
  - Click → basic replayer: step through actions, show `advice_json` (or “n/a”)
- API:
  - `GET /api/review/hands?limit=100`
  - `GET /api/review/hand/{hand_id}` → returns actions + advice per idx

**Accept**
- Replayer shows sequence + advice snapshot if available.

---

## TASK-20 (M1): Autoplay vs Bots — Coach Mode
**Deliver**
- Extend `backend/scripts/autoplay.py`:
  - `--mode bots` (existing)
  - `--mode coach-vs-bots`
    - Hero uses coach argmax (or sampling via `--mix=argmax|sample`)
    - Opponents use heuristic bots
  - Other args: `--hands 1000`, `--seed`, `--seats`, `--sb`, `--bb`, `--stacks`
  - Output: CSV summary with `bb/100`, VPIP/PFR, agg, bucket mix, cache hits, avg EV delta
- Fails gracefully if coach not enabled (friendly CLI message)

**Accept**
- 100+ hand run completes.
- Output shows clean stats.
- Deterministic with same seed/tree.

---

## M1 Acceptance (Overall)

- ✅ With `COACH_ENABLED=false`:
  - All CI tests pass.
  - API/UI fallback cleanly with no solver present.
  - **Carryover complete:** per-action logging, export endpoints, docs, slim dist.

- ✅ With `COACH_ENABLED=true` and valid `TEXASSOLVER_PATH`:
  - Advice returns for supported HU postflop spots.
  - Cache hits recorded.
  - Autoplay coach-vs-bots works and exports metrics.
  - Review page lets you inspect full trace + solver advice.
