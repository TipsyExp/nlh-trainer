# docs/CONFIGURATION.md
# Configuration

The trainer backend is configured via environment variables. All variables are
optional; sensible defaults are chosen for development, but production
deployments should set explicit values (usually via a `.env` file or process
manager configuration).

---

## Hand auto-advance (gating)

| Variable            | Description                                                                                                                                                                         | Default | Typical use                                                                                      |
|---------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------|--------------------------------------------------------------------------------------------------|
| `HAND_AUTO_ENABLED` | Enables the `/api/hand/auto` endpoint and causes bots to auto-advance after each human action. When `false`, `/api/hand/auto` returns HTTP `501` and the frontend must not call it. | `false` | Set to `true` for local dev / small test setups; keep `false` if you want explicit UI control. |

---

## Bot behaviour

| Variable             | Description                                                                                                                                                                     | Default         | Typical use                                                                                         |
|----------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------|-----------------------------------------------------------------------------------------------------|
| `BOT_MODE`           | Controls whether bots act automatically. Accepts `"heuristic"` (built-in policy) or `"none"` (no bot actions; human-vs-human only).                                            | `"heuristic"`   | Use `"heuristic"` in dev and demos; set to `"none"` when you want full manual control or pure replays. |
| `BOT_PROFILE`        | Name of the bot policy to use (when `BOT_MODE != "none"`). Known profiles include `"CALLCHECK"` and `"TAG"` (tight-aggressive).                                                | `"CALLCHECK"`   | Pin to a profile for reproducible behaviour; use different profiles for strength/difficulty testing. |
| `BOT_MAX_STEPS`      | Maximum number of bot actions allowed in a single auto-advance loop. Prevents runaway loops in pathological cases.                                                             | `100`           | Leave at default; lower for stricter guards, raise only if you add extremely deep bot sequences.    |
| `BOT_TIME_BUDGET_MS` | Soft time budget (milliseconds) for a single bot decision. Policies exceeding this budget should return a safe fallback action instead of thinking indefinitely.               | `150`           | Increase slightly if you add expensive policies; keep low in CI and production to avoid stalls.     |

---

## Debugging

| Variable            | Description                                                                                                                                             | Default | Typical use                                                                    |
|---------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------|---------|--------------------------------------------------------------------------------|
| `ENGINE_DEBUG_HTTP` | When `true`, exposes debug endpoints (e.g. `/api/debug/engine/events`) that emit structured engine events and invariants. Adds overhead; disable in prod. | `false` | Enable locally when chasing bugs or capturing hands for analysis.             |

---

## Equity configuration

These variables control the equity service. See [EQUITY.md](EQUITY.md) for
details on backends and capabilities. The same service is used by `/api/equity`,
preflop equity fallback, and the postflop coach.

**Backends & policy**

| Variable                | Description                                                                                                                                                                                                                                     | Default  | Typical use                                                                                          |
|-------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------|------------------------------------------------------------------------------------------------------|
| `EQUITY_BACKEND_POLICY` | Backend selection policy: `auto`, `ompeval`, `eval7`, or `pokerkit`. `auto` tries each backend in order and picks the first that can handle the request (ranges/multiway ⇒ `ompeval`; otherwise falls back to `eval7`/`pokerkit` as available). | `"auto"` | Leave as `auto` in dev; pin to a specific backend in CI to exercise particular code paths.           |
| `EQUITY_ITERS`          | Default number of Monte Carlo iterations for non-exact runs. Can be overridden per request (`iters` field in `/api/equity`).                                                                                                                    | `20000`  | Increase for more accurate MC results; decrease for faster responses or when running many tests.     |
| `EQUITY_TIMEOUT_MS`     | Optional soft timeout (milliseconds). Backends may stop sampling once this budget is exceeded, returning the best estimate so far.                                                                                                              | not set  | Use in CI or batch jobs to bound worst-case latency on large trees.                                   |

**OMPEval (native) knobs**

| Variable                 | Description                                                                                                                                                                                                                                 | Default | Typical use                                                                                      |
|--------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------|--------------------------------------------------------------------------------------------------|
| `OMPEVAL_THREADS`        | Number of threads OMPEval should use in Monte Carlo / enumeration where applicable. `0` lets OMPEval auto-detect hardware parallelism.                                                                                                     | `0`     | Set to a small number on CI or shared machines; leave at `0` locally to use all cores.          |
| `OMPEVAL_STDERR_TARGET`  | Optional early-stop target for Monte Carlo standard error (as a fraction, e.g. `0.0005` = 0.05%). If set, OMPEval may stop before `iters` when the estimate stabilizes; if unset, fixed-iteration behaviour is used.                        | not set | Use in CI to keep runs short but stable; leave unset for strictly fixed-iteration runs.         |

**Notes**

- `ompeval` supports ranges and multiway equities up to **6 players**. Larger tables are out of scope for this backend and should be simplified (e.g., fold-out players).
- `eval7` is a pure-Python/Cython fallback that handles hands and basic ranges; it is slower and primarily intended for environments without a native build toolchain.
- `pokerkit` remains a pure-Python safety net (hands-focused) and is always available.

---

## Coaching configuration (preflop + postflop)

All coaching endpoints (`/api/coach/preflop` and `/api/coach/advice`) are
globally gated by `COACH_ENABLED`. Additional knobs control preflop charts and
postflop behaviour.

### Preflop advisor

These variables control the preflop advisor. See
[PREFLOP-ADVISOR.md](PREFLOP-ADVISOR.md) for chart format and decision logic.

| Variable                   | Description                                                                                                                                                                                                                                                                               | Default | Typical use                                                                                                                        |
|----------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------|------------------------------------------------------------------------------------------------------------------------------------|
| `COACH_ENABLED`            | Global gate for coaching APIs. When `false`, `GET /api/coach/preflop` and `GET /api/coach/advice` are effectively disabled (advice route returns a `disabled` status or HTTP `501`, depending on phase), and no charts are loaded.                                                       | `false` | Enable in dev/demos when you want any advice; keep `false` in environments that don’t expose coaching to end users.               |
| `PREFLOP_CHART_PATHS`      | Colon- or semicolon-separated list of chart file paths to load at startup (e.g. `devdata/charts/hu_example.json`). At least one valid file must be present for chart-based advice.                                                                                                       | empty   | Point to your HU charts in dev or on a coaching node; leave empty if you don’t ship charts.                                       |
| `PREFLOP_EQ_DEFEND_THRESH` | Equity threshold for the fallback policy (0–1). When chart advice is missing and equity fallback runs, hero defends (call/continue) if equity ≥ threshold; otherwise fold.                                                                                                               | `0.48`  | Tune based on pool and risk tolerance (e.g. slightly lower to defend more vs aggressive open ranges).                             |
| `PREFLOP_FALLBACK_REQUIRED`| Boolean knob that controls behaviour when chart advice is missing **and** equity fallback can’t run (e.g. no range-capable backend). When `true`, the advisor raises and the API returns `501` instead of guessing. When `false`, it returns a conservative default (usually fold) with `source="rule"`. | `true`  | Use `true` in CI and “strict” environments; use `false` if you prefer a best-effort, conservative recommendation instead of `501`. |

### Postflop coach (HU + multiway)

These variables control the postflop coach used by `/api/coach/advice` for
flop/turn/river spots. The coach is equity-driven and layered on top of the
equity service.

| Variable                           | Description                                                                                                                                                                                                                                                                         | Default   | Typical use                                                                                                                     |
|------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------|---------------------------------------------------------------------------------------------------------------------------------|
| `POSTFLOP_COACH_ENABLED`           | Enables the postflop coach for heads-up spots when `COACH_ENABLED=true`. When `false`, `/api/coach/advice` will still work for preflop, but postflop decisions return a non-actionable status (e.g. `unsupported`) instead of equity-based advice.                                    | `false`   | Turn on in dev when you want flop/turn/river help; keep off initially in prod while validating behaviour.                      |
| `POSTFLOP_COACH_ITERS`             | Default number of Monte Carlo iterations for HU postflop equity queries issued by the coach. Uses the same backends and policy as `/api/equity`, but with this dedicated iteration budget.                                                                                        | `20000`   | Increase for finer-grained postflop equities; decrease if advice calls are too slow or you are running many hands in batch.   |
| `POSTFLOP_COACH_TIMEOUT_MS`        | Soft time budget (milliseconds) for a single postflop coach equity call. When exceeded, the coach should return the best estimate so far or mark the decision as `timeout` rather than blocking indefinitely.                                                                      | not set   | Use in CI or latency-sensitive environments to bound worst-case postflop advice latency.                                       |
| `POSTFLOP_COACH_PROFILE`           | Default villain profile key for postflop range assumptions (e.g. `"TAG"`, `"CALLCHECK"`). The coach uses this to construct opponent ranges for equity calculations.                                                                                                                 | `"TAG"`   | Pin to a profile that matches your target pool; tweak when experimenting with different villain models.                        |
| `POSTFLOP_COACH_MULTIWAY_ENABLED`  | Enables multiway postflop coaching (3–6 players) when a multiway-capable equity backend (e.g. `ompeval`) is available. When `false`, multiway spots are treated as `unsupported` even if HU spots are coached.                                                                    | `false`   | Keep off for the first HU-focused rollout; turn on once you are happy with multiway ranges and performance.                   |
| `POSTFLOP_COACH_MULTIWAY_ITERS`    | Default number of Monte Carlo iterations for multiway postflop equity queries. Usually lower than HU to keep latency under control when more players are involved.                                                                                                                | `15000`   | Tune based on performance; raise gradually if multiway equities look too noisy.                                                |
| `POSTFLOP_COACH_MULTIWAY_POLICY`   | Policy for multiway advice when equity is not available or backends are missing. Example values: `"auto"` (try equity, fall back to rule/unsupported), `"rule-only"` (no equity), `"equity-only"` (mark unsupported when equity can’t run). Implemented options may be a subset. | `"auto"`  | Leave as `"auto"` in most environments; tighten to `"rule-only"` or `"equity-only"` if you want more predictable behaviour.   |

Notes:

- All postflop coach knobs are only consulted when `COACH_ENABLED=true`.
- Equity backends and iteration/time budgets for postflop are **hints**; the
  coach will pick the best available backend under `EQUITY_BACKEND_POLICY`.

---

## Logging & snapshots

These variables control optional logging of equity and coaching advice
snapshots. Snapshots are not part of the core state; they appear only in JSON
exports for debugging, analysis, or audit.

| Variable                      | Description                                                                                                                                                                                                                                                                                         | Default | Typical use                                                                                                  |
|-------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------|--------------------------------------------------------------------------------------------------------------|
| `LOG_EQUITY_SNAPSHOT`         | When `true`, successful `POST /api/equity` calls that include `hand_id` and `idx` are persisted by the logger. Export endpoints (`/api/export/hand/*.json`, `/api/export/session/*.json`) then surface this data under `equity_snapshot` for the matching action.                                    | `false` | Enable temporarily when analysing hands or validating the preflop/postflop coach against raw equity outputs. |
| `LOG_EQUITY_SNAPSHOT_REDACT`  | When `true`, callers that log snapshots should avoid storing raw hole cards/ranges and instead use abstract identifiers (e.g. hand keys, range names). Enforcement is done by callers; this flag just signals that redaction is desired.                                                            | `false` | Set to `true` in production or shared environments to reduce sensitive information in logged snapshots.     |
| `LOG_PREFLOP_ADVICE`          | When `true`, successful `GET /api/coach/preflop` responses are persisted and attached as `preflop_advice` objects in JSON exports for the corresponding `(hand_id, idx)` action.                                                                                                                    | `false` | Enable when you want a replayable record of legacy preflop advice used during training/coaching sessions.   |
| `LOG_COACH_ADVICE`            | When `true`, successful `GET /api/coach/advice` responses are persisted and attached as `coach_advice` objects (the full `AdviceV1` payload) in JSON exports for the corresponding `(hand_id, idx)` action. Preflop, flop, turn, and river decisions can all carry this unified advice snapshot.       | `false` | Turn on when you want a single, all-streets advice record for offline analysis, QA, or UI debugging.        |

Notes:

- Snapshots are **optional** and backwards-compatible. If logging is disabled,
  export JSON simply omits `equity_snapshot`, `preflop_advice`, and
  `coach_advice`.
- CSV exports intentionally do **not** grow new columns for snapshots; JSON is
  the source of truth for this data.
- When both `LOG_PREFLOP_ADVICE` and `LOG_COACH_ADVICE` are true, preflop
  decisions may have **both** `preflop_advice` (legacy shape) and
  `coach_advice` (unified `AdviceV1`) populated in exports.

---

## Example development environment (recommended)

A typical `.env` for local development might look like:

```bash
# Core engine / bot behaviour
ENGINE_DEBUG_HTTP=true
BOT_MODE=heuristic
BOT_PROFILE=CALLCHECK
BOT_MAX_STEPS=100
BOT_TIME_BUDGET_MS=150
HAND_AUTO_ENABLED=true

# Equity settings
EQUITY_BACKEND_POLICY=auto
EQUITY_ITERS=20000
# Optional runtime limits for MC:
# EQUITY_TIMEOUT_MS=500

# OMPEval tuning (optional; native backend)
# OMPEVAL_THREADS=0           # 0 = auto
# OMPEVAL_STDERR_TARGET=0.001 # stop MC early when <= 0.1% std error

# Coaching (preflop + postflop)
COACH_ENABLED=true

# Preflop charts
PREFLOP_CHART_PATHS=devdata/charts/hu_example.json
PREFLOP_EQ_DEFEND_THRESH=0.48
PREFLOP_FALLBACK_REQUIRED=false

# Postflop coach (HU-focused in early phases)
POSTFLOP_COACH_ENABLED=true
POSTFLOP_COACH_ITERS=20000
POSTFLOP_COACH_PROFILE=TAG
# POSTFLOP_COACH_TIMEOUT_MS=250

# Multiway coaching (opt-in once HU is stable)
# POSTFLOP_COACH_MULTIWAY_ENABLED=false
# POSTFLOP_COACH_MULTIWAY_ITERS=15000
# POSTFLOP_COACH_MULTIWAY_POLICY=auto

# Snapshot logging (opt-in)
LOG_EQUITY_SNAPSHOT=true
LOG_PREFLOP_ADVICE=true
LOG_COACH_ADVICE=true
LOG_EQUITY_SNAPSHOT_REDACT=true

# Frontend
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000
NEXT_PUBLIC_ENABLE_HAND_AUTO=true
NEXT_PUBLIC_DEV_TOOLS=true
