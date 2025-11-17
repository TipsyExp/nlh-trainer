# QA Checklist

Use this checklist to verify that the trainer backend and frontend behave
correctly with the updated API semantics.

## Hand flow

* [ ] A new hand can be started via `/api/hand/start` and returns a state with `to_act` equal to the hero seat.
* [ ] If `BOT_MODE != "none"`, bots are auto-advanced to the first human decision on hand start.
* [ ] `/api/hand/auto` returns HTTP `501` when `HAND_AUTO_ENABLED=false`.

## Action submission

* [ ] `amount` represents the **total** commitment when betting or raising; the engine snaps off-tree totals to the nearest bucket.
* [ ] Minimum raise rule enforcement: a raise below `min_raise` returns HTTP `400` with a message like `"min-raise not met: need ≥ X, got Y"`.
* [ ] When `to_call=0` (including heads-up SB open preflop), raise actions are normalised to `"bet"` and open buckets are `["2.2x","2.5x","3.0x","jam"]`.
* [ ] When facing a bet or raise (`to_call>0`), actions are normalised to `"raise"` and buckets have an `"R"` suffix: `["2.5xR","3.0xR","jam"]`.
* [ ] Off-tree requests set `last_action.snapped=true` and `last_action.committed` equals the snapped bucket total.
* [ ] CSV exports use **total** in the `amount` column (matches JSON), volatile columns are omitted (`created_at`, `time_ms`, `rng_seed`, `meta`), and EOLs are LF to avoid platform drift.

## Allowed actions

* [ ] `state.allowed` and the `actor` object correctly report `to_call`, `min_raise` and `allowed_buckets` for the current actor.
* [ ] After each action, `to_act` and `actor.seat` advance to the next seat, or become `null` when the hand ends.

## Debugging

* [ ] With `ENGINE_DEBUG_HTTP=true`, subscribe to `/api/debug/engine/events` and verify that an event is emitted for every transition (start, action, advance street, terminal).
* [ ] Invariants (`pot_non_decreasing`, `to_call_consistent`, `actor_valid`, `last_action_consistent`, `no_check_carryover`) are always `true`.
* [ ] Filtering events by street is case-insensitive.

## Buckets

* [ ] Open buckets (`to_call=0`) are `["2.2x","2.5x","3.0x","jam"]`.
* [ ] Facing a bet or raise, buckets are `["2.5xR","3.0xR","jam"]`.
* [ ] `allowed.allowed_buckets` and `actor.allowed_buckets` match and reflect the correct list.

---

## M2: Equity API

These checks cover the `/api/equity` endpoint and the equity service. Use this
together with EQUITY.md, API-CONTRACT.md and RUNBOOK.md.

* [ ] `POST /api/equity` with two fixed hands and an empty board returns:
  * [ ] HTTP `200`.
  * [ ] `ok=true`.
  * [ ] `backend` is one of `pokerkit`, `eval7`, or `ompeval`.
  * [ ] `mode="hands"`.
  * [ ] `n_players` equals the number of players sent.
  * [ ] Each entry in `players` has `win`, `tie` and `equity` fields.
  * [ ] The sum of `players[*].equity` is ≈ `1.0` (within floating tolerance).
* [ ] With `"exact": true` and two-hand HU on a simple board:
  * [ ] Response has `exact=true`.
  * [ ] `iters` is `null` or `0` (backend-specific).
  * [ ] Repeated calls with the same input yield identical results (or minimal differences when backend cannot do fully exact).
* [ ] With `"exact": false` and `iters` set:
  * [ ] Repeated calls show small variance in `equity` unless `EQUITY_SEED` is set.
  * [ ] Increasing `iters` produces smoother, less noisy equities.
* [ ] Setting `EQUITY_BACKEND_POLICY=auto`:
  * [ ] When a ranges-capable backend is available (preferably `ompeval`, otherwise `eval7`), calls with `range` fields succeed and report `backend="ompeval"` (if built) or `backend="eval7"`, and `mode="ranges"`.
  * [ ] When no ranges-capable backend is available, a ranges request returns HTTP `400` with a clear “no backend available for requested mode”-style error.
* [ ] Setting `EQUITY_BACKEND_POLICY=pokerkit`:
  * [ ] Fixed-hand requests succeed with `backend="pokerkit"`.
  * [ ] Any ranges request fails with HTTP `400` and a clear message.
* [ ] Optional: with OMPEval native extension built, setting `EQUITY_BACKEND_POLICY=ompeval`:
  * [ ] Ranges and multiway (up to 6 players) succeed with `backend="ompeval"`.
  * [ ] Exact/MC behaviour matches expectations on tiny boards.
* [ ] Optional: with Eval7 installed, setting `EQUITY_BACKEND_POLICY=eval7`:
  * [ ] Ranges succeed with `backend="eval7"` (slower than OMPEval).
  * [ ] Results are reasonable vs OMPEval on small scenarios.

---

## M2: Preflop advisor

These checks cover the `GET /api/coach/preflop` endpoint and the coach
configuration. Use this together with PREFLOP-ADVISOR.md, CONFIGURATION.md and
API-CONTRACT.md.

### Coach enabled, charts configured

With environment:

* `COACH_ENABLED=true`
* `PREFLOP_CHART_PATHS` pointing to at least one valid HU chart (for example a dev chart).

* [ ] `GET /api/coach/preflop?hand_id=H1&idx=0` (for a real hand id) returns:
  * [ ] HTTP `200`.
  * [ ] A JSON object with keys: `source`, `bucket`, `rationale`, `strategy_bar`.
  * [ ] `strategy_bar` is a mapping from bucket labels to floats summing to ≈ `1.0`.
* [ ] For a known charted node and hand:
  * [ ] `source="chart"`.
  * [ ] `bucket` matches the chart row’s primary recommendation.
* [ ] For a hand that is deliberately left uncharted but eligible for equity fallback:
  * [ ] If a ranges-capable backend is available (`ompeval` or `eval7`) and fallback is configured, `source="equity"` and `rationale` mentions the threshold (`PREFLOP_EQ_DEFEND_THRESH`) and villain range.
  * [ ] The recommended `bucket` (call/defend vs fold) matches the threshold rule.
* [ ] When both chart and equity fallback are unavailable for a node:
  * [ ] Behaviour matches `PREFLOP_FALLBACK_REQUIRED` (for example, conservative default with `source="rule"` or a clean `404`/`501` error).

### Coach disabled / misconfigured

* [ ] With `COACH_ENABLED=false`, `GET /api/coach/preflop?hand_id=H1&idx=0` returns HTTP `501` with a clear “coach disabled”-style message.
* [ ] With `COACH_ENABLED=true` but `PREFLOP_CHART_PATHS` pointing to an invalid or missing chart:
  * [ ] The advisor returns HTTP `501` or another non-200 status with a descriptive error.
  * [ ] No advice payload is emitted when charts cannot be loaded.

---

## M2: Export snapshots

These checks verify that equity and preflop snapshots are correctly attached
to JSON exports and that CSV exports remain stable.

### Logging disabled (baseline)

With:

* `LOG_EQUITY_SNAPSHOT=false`
* `LOG_PREFLOP_ADVICE=false`

* [ ] Play a hand, optionally calling `/api/equity` and `/api/coach/preflop`.
* [ ] `GET /api/export/hand/{hand_id}.json`:
  * [ ] Hand JSON contains an `actions` array.
  * [ ] No action objects contain `equity_snapshot` or `preflop_advice` fields.
* [ ] `GET /api/export/hand/{hand_id}.csv` and session CSV export:
  * [ ] Column set matches the pre-M2 schema (no extra snapshot columns).
  * [ ] Amount columns still contain total commitment values; no regressions.

### Logging enabled

With:

* `LOG_EQUITY_SNAPSHOT=true`
* `LOG_PREFLOP_ADVICE=true`
* Optional: `LOG_EQUITY_SNAPSHOT_REDACT=true` in shared or prod-like environments.

1. **Generate snapshots**

   * [ ] Play at least one full hand.
   * [ ] During that hand:
     * [ ] Call `POST /api/equity?hand_id=H1&idx=0` (or another index) with a valid body.
     * [ ] Call `GET /api/coach/preflop?hand_id=H1&idx=0` (or a matching index).

2. **Verify hand JSON export**

   * [ ] `GET /api/export/hand/{hand_id}.json`:
     * [ ] At least one action in `actions` has an `equity_snapshot` object when the corresponding `/api/equity` call succeeded.
     * [ ] At least one action has a `preflop_advice` object when the corresponding `/api/coach/preflop` call succeeded.
     * [ ] Snapshot fields are valid JSON objects (not raw strings).
     * [ ] If `LOG_EQUITY_SNAPSHOT_REDACT=true`, redacted fields match expectations (no raw hole cards/ranges if the logger is configured to omit them).

3. **Verify session JSON export**

   * [ ] `GET /api/export/session/{session_id}.json`:
     * [ ] Hands included in the session expose the same snapshot fields under each action.
     * [ ] Hands without any logged equity/preflop calls do not contain these fields (or they are `null`), preserving backwards compatibility.

4. **CSV exports**

   * [ ] Hand and session CSV exports still do not contain snapshot columns.
   * [ ] Behaviour is identical whether logging flags are enabled or disabled.

---

## M2: CI and benchmarks (OMPEval native + Eval7 fallback)

These checks are primarily for CI and developer experience.

* [ ] In an **OMPEval-enabled** environment, `make bench-equity OUT=bench_equity.csv POLICIES=auto,ompeval,eval7`:
  * [ ] Completes successfully within a short time.
  * [ ] Produces `bench_equity.csv` with at least one data row.
  * [ ] CSV rows include fields such as `scenario`, `policy`, `backend`, `board_len`, `iters`, `elapsed_ms`, `evals_per_sec`, and `equities`.
  * [ ] `elapsed_ms` is non-negative, `evals_per_sec` is non-negative, and values look reasonable for a tiny benchmark.
* [ ] In the OMPEval-enabled CI job:
  * [ ] The native extension is built per `docs/BUILD-OMPEVAL.md`.
  * [ ] Backend tests pass with the native backend available.
  * [ ] The equity benchmark step runs and uploads a CSV artifact (for example `equity-bench-ompeval`).
* [ ] In the default CI job (no native extension / no optional deps):
  * [ ] Tests that require ranges/multiway **skip cleanly** (e.g., `importorskip` for OMPEval wrapper).
  * [ ] Remaining tests pass with PokerKit and/or Eval7 if installed.
  * [ ] The benchmark still runs with policies that are available (e.g., `auto` → `pokerkit`), producing a small CSV artifact or writing to stdout.
