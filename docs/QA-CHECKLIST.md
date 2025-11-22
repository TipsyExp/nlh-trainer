# QA Checklist

Use this checklist to verify that the trainer backend and frontend behave
correctly with the updated API semantics.

---

## Hand flow

* [ ] A new hand can be started via `/api/hand/start` and returns a state with `to_act` equal to the hero seat.
* [ ] If `BOT_MODE != "none"`, bots are auto-advanced to the first human decision on hand start.
* [ ] `/api/hand/auto` returns HTTP `501` when `HAND_AUTO_ENABLED=false`.

---

## Action submission

* [ ] `amount` represents the **total** commitment when betting or raising; the engine snaps off-tree totals to the nearest bucket.
* [ ] Minimum raise rule enforcement: a raise below `min_raise` returns HTTP `400` with a message like `"min-raise not met: need ≥ X, got Y"`.
* [ ] When `to_call=0` (including heads-up SB open preflop), raise actions are normalised to `"bet"` and open buckets are `["2.2x","2.5x","3.0x","jam"]`.
* [ ] When facing a bet or raise (`to_call>0`), actions are normalised to `"raise"` and buckets have an `"R"` suffix: `["2.5xR","3.0xR","jam"]`.
* [ ] Off-tree requests set `last_action.snapped=true` and `last_action.committed` equals the snapped bucket total.
* [ ] CSV exports use **total** in the `amount` column (matches JSON), volatile columns are omitted (`created_at`, `time_ms`, `rng_seed`, `meta`), and EOLs are LF to avoid platform drift.

---

## Allowed actions

* [ ] `state.allowed` and the `actor` object correctly report `to_call`, `min_raise` and `allowed_buckets` for the current actor.
* [ ] After each action, `to_act` and `actor.seat` advance to the next seat, or become `null` when the hand ends.

---

## Debugging

* [ ] With `ENGINE_DEBUG_HTTP=true`, subscribe to `/api/debug/engine/events` and verify that an event is emitted for every transition (start, action, advance street, terminal).
* [ ] Invariants (`pot_non_decreasing`, `to_call_consistent`, `actor_valid`, `last_action_consistent`, `no_check_carryover`) are always `true`.
* [ ] Filtering events by street is case-insensitive.

---

## Buckets

* [ ] Open buckets (`to_call=0`) are `["2.2x","2.5x","3.0x","jam"]`.
* [ ] Facing a bet or raise, buckets are `["2.5xR","3.0xR","jam"]`.
* [ ] `allowed.allowed_buckets` and `actor.allowed_buckets` match and reflect the correct list.

---

## M2: Equity API

These checks cover the `/api/equity` endpoint and the equity service. Use this
together with `EQUITY.md`, `API-CONTRACT.md` and `RUNBOOK.md`.

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

## M2: Preflop advisor (`/api/coach/preflop`, legacy)

These checks cover the `GET /api/coach/preflop` endpoint and the coach
configuration. Use this together with `PREFLOP-ADVISOR.md`, `CONFIGURATION.md`
and `API-CONTRACT.md`.

### Coach enabled, charts configured

With environment:

* `COACH_ENABLED=true`
* `PREFLOP_CHART_PATHS` pointing to at least one valid HU chart (for example a dev chart)

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
  * [ ] The advisor returns HTTP `501` with a descriptive error (`"preflop coach charts not configured"` style).
  * [ ] No advice payload is emitted when charts cannot be loaded.

---

## M3: Unified coach & AdviceV1 (`/api/coach/advice`)

These checks cover the **unified** coaching endpoint that returns `AdviceV1`
for preflop and postflop decisions. See `COACH-ADVICE-PAYLOAD.md`,
`COACHING.md`, `API-CONTRACT.md` and `CONFIGURATION.md`.

### Global gating & disabled behaviour

Environment:

* [ ] With `COACH_ENABLED=false`:
  * [ ] `GET /api/coach/advice?hand_id=H1&idx=0` returns HTTP `501`.
  * [ ] The body is an `AdviceV1`-shaped object with:
    * [ ] `version = 1`
    * [ ] `status = "disabled"`
    * [ ] `meta.street = "unknown"`, `meta.n_players = 0`, `meta.hero_seat = 0`, `meta.source = "rule"`
    * [ ] `recommendation`, `equity`, `thresholds` all `null`
    * [ ] `rationale` explaining that coach is disabled.

### Decision context / error handling

With `COACH_ENABLED=true`:

* [ ] For a **valid** `hand_id` + `idx`:
  * [ ] `GET /api/coach/advice` returns HTTP `200`.
  * [ ] Response is a valid `AdviceV1` object (top-level `version`, `status`, `meta`, etc.).
* [ ] For an invalid `idx` (out of range) or stale `hand_id`:
  * [ ] Response is HTTP `400`.
  * [ ] Payload has:
    * [ ] `status = "not_found"`
    * [ ] `meta.street = "unknown"`, `meta.n_players = 0`, `meta.hero_seat = 0`, `meta.source = "rule"`
    * [ ] A descriptive `rationale` (e.g. “Decision context not found…”).
* [ ] If a runtime error occurs while building the context:
  * [ ] Response is HTTP `500`.
  * [ ] Payload has `status = "error"` and a descriptive `rationale` string.

### Preflop path (charts + equity fallback → AdviceV1)

With:

* `COACH_ENABLED=true`
* Preflop charts configured and valid (`PREFLOP_CHART_PATHS`)

For a preflop decision with a valid context:

* [ ] `GET /api/coach/advice?hand_id=H1&idx=0` returns:
  * [ ] `version = 1`
  * [ ] `status = "ok"` (for supported, well-formed spots)
  * [ ] `meta.street = "preflop"`
  * [ ] `meta.n_players` and `meta.hero_seat` match the current hand.
  * [ ] `meta.source ∈ {"chart","equity","rule"}` depending on path taken.
  * [ ] `recommendation.bucket` is one of the allowed buckets for that decision.
  * [ ] `recommendation.strategy_bar` is a list of `{ action, weight }` with weights summing to ≈ `1.0`.
  * [ ] `rationale` is a human-readable explanation.
  * [ ] `equity` and `thresholds` may be `null` at this stage (they are optional for preflop).

Preflop **alignment** with legacy endpoint:

* [ ] For a known preflop decision, compare:
  * [ ] `/api/coach/preflop` response vs `/api/coach/advice`’s `AdviceV1`:
    * [ ] `source` ≈ `meta.source`
    * [ ] `bucket` ≈ `recommendation.bucket`
    * [ ] `strategy_bar` ≈ `recommendation.strategy_bar`
    * [ ] `rationale` ≈ `rationale`
  * [ ] Minor differences are acceptable but they should agree semantically.

### Postflop HU path (equity-based coach → AdviceV1)

With:

* `COACH_ENABLED=true`
* `POSTFLOP_COACH_ENABLED=true`
* A heads-up hand reaching flop/turn/river

For a HU postflop decision (`street` ∈ {`"flop"`, `"turn"`, `"river"`}):

* [ ] `GET /api/coach/advice?hand_id=H1&idx=K` returns HTTP `200`.
* [ ] Payload:
  * [ ] `status = "ok"` for supported spots.
  * [ ] `meta.street` matches the actual street (`"flop"`, `"turn"`, or `"river"`).
  * [ ] `meta.n_players = 2`.
  * [ ] `meta.hero_seat` matches the session’s hero seat.
  * [ ] `meta.source = "equity"`.
  * [ ] `recommendation.bucket` is one of the allowed buckets (e.g. `"fold"`, `"call"`, `"check"`, `"2.5xR"`, `"jam"`).
  * [ ] `recommendation.strategy_bar` is a short list of `{ action, weight }`.
  * [ ] `equity` block is populated with:
    * [ ] `backend`, `mode`, `hero`, `players`, `exact`, `iters`.
    * [ ] At least two `players` entries with `seat` and `equity`.
  * [ ] `thresholds.pot_odds` is set when appropriate (e.g. facing a bet).
  * [ ] `thresholds.spr` is present when stack information is available.
  * [ ] `rationale` references hero equity vs pot odds in a sensible way.

When `POSTFLOP_COACH_ENABLED=false` but `COACH_ENABLED=true`:

* [ ] Preflop decisions still return `status="ok"` (chart/equity/rule).
* [ ] HU postflop decisions return HTTP `200` with:
  * [ ] `status = "unsupported"`
  * [ ] Correct `meta.street`, `meta.n_players`, `meta.hero_seat`.
  * [ ] `recommendation`, `equity`, `thresholds` are `null` or omitted.

### Multiway postflop behaviour

Depending on configuration and backends:

* [ ] When `POSTFLOP_COACH_MULTIWAY_ENABLED=false` and `n_players > 2`:
  * [ ] Postflop decisions return `status="unsupported"` (HTTP `200`).
  * [ ] `meta.street` and `meta.n_players` reflect the multiway context.
* [ ] When `POSTFLOP_COACH_MULTIWAY_ENABLED=true` and a multiway-capable backend is available:
  * [ ] For supported multiway spots, `AdviceV1` may include:
    * [ ] `meta.n_players > 2`
    * [ ] `equity.players` list with more than two entries.
  * [ ] Unsupported edge cases still return `status="unsupported"` but do not crash.

---

## M2/M3: Export snapshots (equity, preflop, unified coach)

These checks verify that equity, preflop, and unified coach advice snapshots are
correctly attached to JSON exports and that CSV exports remain stable.

### Logging disabled (baseline)

With:

* `LOG_EQUITY_SNAPSHOT=false`
* `LOG_PREFLOP_ADVICE=false`
* `LOG_COACH_ADVICE=false`

* [ ] Play a hand, optionally calling `/api/equity`, `/api/coach/preflop`, and `/api/coach/advice`.
* [ ] `GET /api/export/hand/{hand_id}.json`:
  * [ ] Hand JSON contains an `actions` array.
  * [ ] No action objects contain `equity_snapshot`, `preflop_advice`, or `coach_advice` fields.
* [ ] `GET /api/export/hand/{hand_id}.csv` and session CSV export:
  * [ ] Column set matches the baseline schema (no extra snapshot columns).
  * [ ] Amount columns still contain total commitment values; no regressions.

### Logging enabled – all knobs

With:

* `LOG_EQUITY_SNAPSHOT=true`
* `LOG_PREFLOP_ADVICE=true`
* `LOG_COACH_ADVICE=true`
* Optional: `LOG_EQUITY_SNAPSHOT_REDACT=true` in shared or prod-like environments.

1. **Generate snapshots**

   * [ ] Play at least one full hand with:
     * [ ] At least one preflop decision.
     * [ ] At least one postflop decision (flop/turn/river) if the coach is enabled there.
   * [ ] During that hand:
     * [ ] Call `POST /api/equity?hand_id=H1&idx=0` (or another index) with a valid body.
     * [ ] Call `GET /api/coach/preflop?hand_id=H1&idx=0` for a preflop decision.
     * [ ] Call `GET /api/coach/advice?hand_id=H1&idx=0` (preflop) and again at a postflop index.

2. **Verify hand JSON export**

   * [ ] `GET /api/export/hand/{hand_id}.json`:
     * [ ] At least one action in `actions` has an `equity_snapshot` object when the corresponding `/api/equity` call succeeded.
     * [ ] At least one **preflop** action has a `preflop_advice` object when `/api/coach/preflop` was called for that `(hand_id, idx)`.
     * [ ] Actions for which `/api/coach/advice` was called have a `coach_advice` object that:
       * [ ] Mirrors the `AdviceV1` payload returned by `/api/coach/advice` (same `version`, `status`, `meta`, `recommendation`, etc.).
       * [ ] For preflop decisions, may coexist with `preflop_advice`.
       * [ ] For postflop decisions, is present even though `preflop_advice` is absent.
     * [ ] Snapshot fields are valid JSON objects (not raw strings).

   * [ ] If `LOG_EQUITY_SNAPSHOT_REDACT=true`:
     * [ ] `equity_snapshot` omits or redacts raw card / range details as per logger rules (e.g. players marked `redacted`, board/range inputs redacted).

3. **Verify session JSON export**

   * [ ] `GET /api/export/session/{session_id}.json`:
     * [ ] Hands included in the session expose the same snapshot fields under each action.
     * [ ] Hands without any logged equity/coaching calls do not contain these fields, preserving backwards compatibility.

4. **CSV exports**

   * [ ] Hand and session CSV exports still do **not** contain snapshot columns.
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
