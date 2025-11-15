
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
details on backends and capabilities.

| Variable                | Description                                                                                                                                                                                           | Default   | Typical use                                                                                               |
|-------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------|-----------------------------------------------------------------------------------------------------------|
| `EQUITY_BACKEND_POLICY` | Backend selection policy: `auto`, `pokerkit`, `henry`, or `pbots`. `auto` tries each backend in order and picks the first that can handle the request (ranges/multiway ⇒ pbots; otherwise henry/pokerkit). | `"auto"`  | Leave as `auto` in dev; pin to a specific backend in CI to exercise particular code paths.               |
| `EQUITY_ITERS`          | Default number of Monte Carlo iterations for non-exact runs. Can be overridden per request (`iters` field in `/api/equity`).                                                                          | `20000`   | Increase for more accurate MC results; decrease for faster responses or when running many tests.         |
| `EQUITY_SEED`           | Optional RNG seed for Monte Carlo simulation. When set, repeated calls with identical inputs produce identical MC results (subject to backend behaviour).                                             | not set   | Set in tests/benchmarks for determinism; leave unset in interactive environments to avoid correlation.   |
| `EQUITY_TIMEOUT_MS`     | Optional soft timeout (milliseconds). Backends may stop sampling once this budget is exceeded, returning the best estimate so far.                                                                    | not set   | Use in CI or batch jobs to bound worst-case latency on large trees.                                      |
| `HREVAL_LIB_PATH`       | Absolute path to the HenryRLee native evaluator library (e.g. `/usr/local/lib/libhreval.so`). If missing or invalid, the Henry backend is disabled and `EQUITY_BACKEND_POLICY=henry` will fall back.  | not set   | Set only in environments where you’ve installed the Henry library and want its exact HU fast path.       |

---

## Coach / preflop advisor configuration

These variables control the preflop advisor. See
[PREFLOP-ADVISOR.md](PREFLOP-ADVISOR.md) for chart format and decision logic.

| Variable                 | Description                                                                                                                                                                                                                                                                   | Default | Typical use                                                                                                                        |
|--------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------|------------------------------------------------------------------------------------------------------------------------------------|
| `COACH_ENABLED`          | Global gate for coaching APIs. When `false`, `GET /api/coach/preflop` returns HTTP `501` and no charts are loaded.                                                                                                                                                           | `false` | Enable in dev/demos when you want advice; keep `false` in environments that don’t expose coaching to end users.                   |
| `PREFLOP_CHART_PATHS`    | Colon- or semicolon-separated list of chart file paths to load at startup (e.g. `devdata/charts/hu_example.json`). At least one valid file must be present for chart-based advice.                                                                                           | empty   | Point to your HU charts in dev or on a coaching node; leave empty if you don’t ship charts.                                       |
| `PREFLOP_EQ_DEFEND_THRESH` | Equity threshold for the fallback policy (0–1). When chart advice is missing and equity fallback runs, hero defends (call/continue) if equity ≥ threshold; otherwise fold.                                                                                                   | `0.48`  | Tune based on pool and risk tolerance (e.g. slightly lower to defend more vs aggressive open ranges).                             |
| `PREFLOP_FALLBACK_REQUIRED` | Boolean knob that controls behaviour when chart advice is missing **and** equity fallback can’t run (e.g. no range-capable backend). When `true`, the advisor raises and the API returns `501` instead of guessing. When `false`, it returns a conservative default (usually fold) with `source="rule"`. | `true`  | Use `true` in CI and “strict” environments; use `false` if you prefer a best-effort, conservative recommendation instead of `501`. |

---

## Logging & snapshots

These variables control optional logging of equity and preflop advice
snapshots. Snapshots are not part of the core state; they appear only in JSON
exports for debugging, analysis, or audit.

| Variable                    | Description                                                                                                                                                                                                                                                   | Default | Typical use                                                                                                  |
|-----------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------|--------------------------------------------------------------------------------------------------------------|
| `LOG_EQUITY_SNAPSHOT`       | When `true`, successful `POST /api/equity` calls that include `hand_id` and `idx` are persisted by the logger. Export endpoints (`/api/export/hand/*.json`, `/api/export/session/*.json`) then surface this data under `equity_snapshot` for the matching action. | `false` | Enable temporarily when analysing hands or validating the preflop advisor against equity outputs.           |
| `LOG_EQUITY_SNAPSHOT_REDACT`| When `true`, callers that log snapshots should avoid storing raw hole cards/ranges and instead use abstract identifiers (e.g. hand keys, range names). Enforcement is done by callers; this flag just signals that redaction is desired.                      | `false` | Set to `true` in production or shared environments to reduce sensitive information in logged snapshots.     |
| `LOG_PREFLOP_ADVICE`        | When `true`, successful `GET /api/coach/preflop` responses are persisted and attached as `preflop_advice` objects in JSON exports for the corresponding `(hand_id, idx)` action.                                                                            | `false` | Enable when you want a replayable record of advice used during training/coaching sessions.                  |

Notes:

- Snapshots are **optional** and backwards-compatible. If logging is disabled,
  export JSON simply omits `equity_snapshot` / `preflop_advice`.
- CSV exports intentionally do **not** grow new columns for snapshots; JSON is
  the source of truth for this data.

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
# Optional; uncomment for deterministic MC results:
# EQUITY_SEED=42
# EQUITY_TIMEOUT_MS=500

# Preflop coach
COACH_ENABLED=true
PREFLOP_CHART_PATHS=devdata/charts/hu_example.json
PREFLOP_EQ_DEFEND_THRESH=0.48
PREFLOP_FALLBACK_REQUIRED=false

# Snapshot logging (opt-in)
LOG_EQUITY_SNAPSHOT=true
LOG_PREFLOP_ADVICE=true
LOG_EQUITY_SNAPSHOT_REDACT=true

Frontend configuration should mirror the backend in development:
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000
NEXT_PUBLIC_ENABLE_HAND_AUTO=true
NEXT_PUBLIC_DEV_TOOLS=true

Older variables like ALLOW_DEV_AUTO and MAX_BOT_STEPS have been removed;
use HAND_AUTO_ENABLED and BOT_MAX_STEPS instead.
