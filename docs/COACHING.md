
# Coaching

This document describes how coaching works end-to-end:

- What the coach returns (the **Advice** payload).
- Which endpoints exist and how they relate.
- How backend coaching logic builds on a shared **decision context**.
- How the **Table overlay** consumes advice.
- How this ties into logging and exports at a high level.

For the full *canonical* Advice payload spec, see **`docs/COACH-ADVICE-PAYLOAD.md`**.

---

## 1. Advice payload (AdviceV1)

All long-term coaching is built around a single, versioned payload:

- **Type:** `AdviceV1`
- **Version:** `version: 1`
- **Status:** `status: 'ok' | 'disabled' | 'unsupported' | 'not_found' | 'timeout' | 'error'`

High-level shape (conceptual):

- `status`: whether the advice is actionable.
- `meta`: street, number of active players, hero seat, advice source.
- `recommendation`:
  - `bucket` – canonical action label (`fold`, `call`, `check`, `2.2x`, `2.5xR`, `jam`, …).
  - `strategy_bar` – list of `{ action, weight }` entries (weights typically sum to ≈ 1.0).
- `equity`: hero and per-player equities, backend, mode, iters, etc.
- `thresholds`: pot odds and optional SPR.
- `rationale`: human-readable explanation.

The Pydantic model for this lives in:

- `backend/schemas/advice.py` → `AdviceV1`, `AdviceMeta`, `AdviceRecommendation`, etc.

The detailed field list and semantics live in **`COACH-ADVICE-PAYLOAD.md`**, which should be treated as the canonical spec for the unified coach payload.

### Current state vs target

- `/api/coach/advice` **already** returns `AdviceV1` on the wire and is the primary route used by the table overlay.
- Internally:
  - Preflop advice is produced by `PreflopAdvisorService` and then wrapped into `AdviceV1`.
  - Postflop advice is produced by the postflop coach (`backend/coach/postflop/service.py`) directly as `AdviceV1`.
- The legacy `/api/coach/preflop` route still returns its original preflop-only shape (subset of `AdviceV1`) for compatibility.

---

## 2. Endpoints

### 2.1 `GET /api/coach/advice` (universal route, AdviceV1)

**Purpose:** Return coaching advice for a specific decision on any street, using the unified `AdviceV1` payload.

- **Method:** `GET`
- **Query params:**
  - `hand_id` (string, required) – hand identifier (e.g. `"H1"`).
  - `idx` (int, required) – 0-based decision index within the hand.

The backend:

1. Checks whether coaching is enabled via `COACH_ENABLED` (see `backend.config` and `CONFIGURATION.md`).
2. Builds a shared **decision context** from `hand_id` and `idx` (see section 3).
3. Routes to:
   - **Preflop advisor** (preflop decisions).
   - **Postflop coach** (flop/turn/river decisions).
   - A generic “unsupported” path for everything else (showdown/unknown).

#### Response shape

On success, the route returns an `AdviceV1` object, e.g.:

```json
{
  "version": 1,
  "status": "ok",
  "meta": {
    "street": "preflop",
    "n_players": 2,
    "hero_seat": 0,
    "source": "chart"
  },
  "recommendation": {
    "bucket": "2.5x",
    "strategy_bar": [
      { "action": "2.5x", "weight": 1.0 }
    ]
  },
  "equity": null,
  "thresholds": null,
  "rationale": "Open 2.5x from BTN per chart."
}
Status semantics:
•	status = "ok" – advice is actionable and includes at least:
o	meta.street, meta.n_players, meta.hero_seat, meta.source
o	recommendation.bucket and (usually) recommendation.strategy_bar
o	rationale
•	status = "disabled" – coach globally disabled via COACH_ENABLED; advice is not actionable.
•	status = "unsupported" – the decision is not currently supported by the coach (e.g. charts missing, certain multiway spots, or streets not implemented).
•	status = "not_found" – the (hand_id, idx) pair could not be resolved into a valid decision context (invalid hand or index).
•	status = "timeout" – reserved for future paths that enforce strict time budgets (e.g. solver-based postflop).
•	status = "error" – unexpected internal error while setting up context or computing advice.
HTTP status codes (current implementation)
/api/coach/advice uses a mix of HTTP and AdviceV1.status:
•	Coach disabled (COACH_ENABLED=false)
o	HTTP 501 with AdviceV1.status="disabled".
•	Decision context issues
o	Bad / missing decision context (hand_id / idx mismatch):
	HTTP 400 with status="not_found".
o	Unexpected context build failure:
	HTTP 500 with status="error".
•	Normal coaching flow (context OK)
o	Preflop / postflop / unsupported:
	HTTP 200 with status ∈ {"ok","unsupported","not_found","error"} depending on how the coach handled the spot.
The intention is that, for normal situations once context is resolved:
•	HTTP 200 is used, with status inside AdviceV1 explaining whether the spot was supported or not.
•	Non-200 HTTP codes indicate global gating (501) or structural/context problems (400, 500).
Street-specific behaviour
Preflop (street = "preflop")
•	Implementation:
o	Delegates to PreflopAdvisorService (backend/coach/preflop/service.py).
o	Wraps the advisor result into AdviceV1.
•	Meta:
o	meta.street = "preflop"
o	meta.source ∈ {"chart","equity","rule"}
o	meta.n_players, meta.hero_seat from decision context.
•	Recommendation:
o	recommendation.bucket comes from the advisor (e.g. "fold", "call", "2.5x", "jam").
o	recommendation.strategy_bar is a list derived from the advisor’s strategy_bar mapping.
•	Equity / thresholds:
o	equity and thresholds may be null initially (preflop equity is handled separately by equity endpoints or future coach versions).
•	Rationale:
o	rationale is the preflop advisor’s explanation (chart node, fallback, etc.).
Postflop (street ∈ {"flop","turn","river"})
•	Implementation:
o	Delegates to the postflop coach v1:
	backend/coach/postflop/service.py → get_postflop_advice(ctx).
•	Meta:
o	meta.street = "flop", "turn" or "river".
o	meta.n_players and meta.hero_seat from decision context.
o	meta.source is typically "equity" for equity-driven advice.
•	Recommendation:
o	recommendation.bucket is chosen from the engine’s allowed buckets for that decision.
o	strategy_bar is a small list of { action, weight } entries (often a pure strategy in v1).
•	Equity:
o	equity.hero and (optionally) equity.players filled from EquityService.
o	Backend/mode/iters metadata is carried through where useful.
•	Thresholds:
o	thresholds.pot_odds provided when a call/fold decision is being priced and to_call/pot_total are available.
o	thresholds.spr may be provided when stack information is available.
•	Status:
o	status="ok" – HU / multiway spot that the postflop coach supports and can price.
o	status="unsupported" – spot outside current scope (e.g. configuration disables multiway, or no suitable equity backend).
o	status="error" – internal error in equity or coach logic.
Other streets (showdown / unknown)
•	For now:
o	/api/coach/advice returns HTTP 200 with status="unsupported" and meta.street reflecting the context (or "unknown").
o	recommendation and equity are omitted or null.
________________________________________
2.2 GET /api/coach/preflop (legacy / specialised)
The preflop advisor endpoint is preserved for compatibility and testing. It exposes the preflop-only advice shape directly, without wrapping into AdviceV1.
•	Method: GET
•	Query params: hand_id (required), idx (optional, default 0).
•	Response shape:
{
  "source": "chart",
  "bucket": "2.5x",
  "rationale": "chart:HU_25bb_srp_vsb; node=sb_open; hand=AJo",
  "strategy_bar": {
    "fold": 0.15,
    "call": 0.55,
    "2.5x": 0.30
  }
}
Where:
•	source ∈ {"chart","equity","rule"}
•	bucket is the recommended action bucket.
•	strategy_bar is a plain object bucket → weight.
•	rationale explains how the advice was derived.
Relationship to AdviceV1:
The fields map directly:
•	source → meta.source
•	bucket → recommendation.bucket
•	strategy_bar → recommendation.strategy_bar
•	rationale → rationale
/api/coach/preflop:
•	Is gated by COACH_ENABLED.
•	Uses PreflopAdvisorService internally.
•	Does not include equity / thresholds in its payload.
•	Is effectively a specialised, preflop-only view of the same logic that powers preflop advice on /api/coach/advice.
________________________________________
2.3 POST /api/coach/test_solve (dev-only, solver adapter)
This is a developer-only endpoint used to exercise the TexasSolver adapter directly. It does not participate in the AdviceV1 flow and is not intended for production UI.
•	Method: POST
•	Body: a SolveRequestModel containing:
o	street ∈ {"flop","turn","river"}
o	board, pot, ip_stack, oop_stack
o	ip_range, oop_range, bucket_labels, spot
•	Response: a solver-centric payload:
{
  "recommended_bucket": "2.5xR",
  "strategy": { "fold": 0.1, "2.5xR": 0.9 },
  "ev_map": { "fold": 0.0, "2.5xR": 1.23 },
  "meta": {
    "status": "ok",
    "cached": false,
    "latency_ms": 12.3,
    "node_key": null
  }
}
This endpoint is useful for:
•	Solver experiments.
•	Low-level QA of solver integration.
•	It does not log coach_advice snapshots and is separate from the unified coach flow.
________________________________________
3. Decision context helper
Backend coaching logic does not work directly on raw engine state. Instead, it uses a shared decision context helper.
•	Module: backend/coach/decision_context.py
•	Primary entrypoint:
o	build_decision_context(hand_id: str, idx: int) -> DecisionContext
3.1 Shape (conceptual)
The helper produces a normalized context object (a DecisionContext dataclass) with at least:
•	Hand identity
o	hand_id – the exported hand identifier (e.g. "H1").
o	idx – 0-based decision index.
•	Game framing
o	street – "preflop" | "flop" | "turn" | "river" | "showdown" | "unknown".
o	n_players – number of active players in the pot.
o	hero_seat – seat index of the human / hero.
•	Cards
o	hero_hole_cards – hero’s hand, when known for the street.
o	board – current board cards as a flat list (0–5 cards).
•	Betting situation
o	pot_total – pot size before the hero acts.
o	to_call – chips required for hero to continue (0 when checking behind / first to act).
o	min_raise – total commitment required to meet the minimum-raise rule (may be None when not applicable).
o	allowed_buckets – canonical bucket labels available to the hero ("fold", "call", "check", "2.2x", "2.5xR", "jam", …).
•	Stack / commitment (where available)
o	Effective stacks and/or per-seat stacks, as needed for equity and SPR.
o	Per-seat committed amounts so far in the hand or on the current street.
•	Status
o	A list of active seats.
o	Flags to indicate whether this decision is terminal.
The exact type lives in backend/coach/decision_context.py. This section intentionally stays conceptual so other docs and the UI don’t depend on every internal field.
3.2 Data sources
The decision context is derived from:
•	The engine adapter (backend.adapters.engines.get_adapter()).
•	Session state (backend.api.session.get_session_state) for human_seat.
•	The public state shape defined in docs/STATE-SCHEMA.md and assembled via backend.api.hand._to_public_state.
Over time, additional sources (e.g. log replay from the DB) may be layered in so that context can be reconstructed for historical decisions, not just the live state.
3.3 Consumers
Key consumers of DecisionContext:
•	/api/coach/advice:
o	Always builds a context first, then routes to preflop or postflop coach based on ctx.street.
•	Preflop advisor (PreflopAdvisorService):
o	Uses context for node classification and sanity checks (SB vs BB, stack depth, etc.).
•	Postflop coach (backend/coach/postflop/service.py):
o	Uses hero hand, board, pot, to_call, allowed_buckets, and stacks to compute equities and recommend actions.
•	Solver integration (backend/coach/node_builder.py, if used):
o	Builds solver requests based on the same context (for dev/test solver flows).
•	Logging / exports (future):
o	May attach context-derived metadata to snapshots or use hand_id/idx to tie coach_advice back to a known decision.
The goal is that all coaching and solver paths share one truthful, consistent view of each decision.
________________________________________
4. Postflop coach v1 (equity-based)
The first postflop coach implementation (PostflopCoachService) uses DecisionContext plus EquityService to produce AdviceV1.
•	Module: backend/coach/postflop/service.py
•	Inputs:
o	DecisionContext for the target decision.
•	Scope (v1):
o	Streets: flop, turn, river.
o	Players: heads-up and (optionally) multiway, depending on configuration and available backends.
4.1 Inputs and assumptions
From DecisionContext, the postflop coach uses:
•	street – "flop", "turn", or "river".
•	hero_seat, n_players, active seats.
•	hero_hole_cards – fixed hero hand.
•	board – known board cards.
•	pot_total, to_call, min_raise, allowed_buckets.
•	Positional anchors (button / blinds) where needed for IP/OOP classification.
•	Stacks and commitments, when available, for SPR and shove vs small-bet decisions.
Villain(s) are represented using ranges derived from:
•	A configurable profile (e.g. POSTFLOP_COACH_PROFILE="TAG").
•	Street and node context (e.g. preflop aggressor / defender roles).
Ranges are defined in helper modules such as:
•	backend/coach/postflop/ranges.py
•	(For multiway) backend/coach/postflop/multiway_profiles.py (planned / optional).
4.2 Equity engine
The coach uses EquityService (backend/services/equity/service.py) internally:
•	Backends are selected according to EQUITY_BACKEND_POLICY and capabilities:
o	Typically ompeval when ranges or multiway equities are requested.
•	Iteration counts and timeouts:
o	Respect POSTFLOP_COACH_ITERS, POSTFLOP_COACH_MULTIWAY_ITERS, POSTFLOP_COACH_TIMEOUT_MS, and the global equity settings.
•	Typical usage patterns:
o	HU hero-hand vs villain-range on given board.
o	Multiway hero-hand vs multiple villain ranges, if enabled and supported.
The equity result is then distilled into:
•	equity.hero (0–1).
•	equity.players – per-seat equities when available (especially for multiway).
•	Backend/mode/iters metadata as appropriate.
4.3 Decision logic (simplified)
The postflop coach v1 uses relatively simple heuristics:
•	Facing a bet (call/fold/raise decision):
o	Compute pot odds threshold:
	thresholds.pot_odds ≈ to_call / (pot_total + to_call) (when closing the action).
o	Compare hero_equity vs pot-odds threshold with some margin:
	Far below threshold → prefer a fold bucket if available.
	Near threshold → prefer call.
	Far above threshold → include one or more raise buckets (e.g. "2.5xR", "3.0xR", "jam") if allowed.
•	No bet facing hero (check / bet):
o	Use crude hand-strength / draw categories (top pair+, strong draws, air) to:
	Bet with strong value / strong draws when betting buckets exist.
	Check weaker or marginal hands.
•	Multiway (when enabled and supported):
o	Build a players array for the equity engine (hero hand + villain ranges).
o	Compute multiway equities.
o	Typically recommend more conservative folds when hero is not closing the action and equity is marginal.
4.4 Output as AdviceV1
The service returns an AdviceV1 instance:
•	version = 1
•	status:
o	"ok" for supported spots with a clear recommendation.
o	"unsupported" when configuration or backend capabilities don’t allow coaching for this spot.
o	"error" if something unexpected goes wrong.
•	meta:
o	street ∈ {"flop","turn","river"}.
o	n_players, hero_seat from context.
o	source = "equity" (for equity-based advice).
•	recommendation:
o	bucket from allowed_buckets ("fold", "call", "check", "2.5xR", "jam", …).
o	strategy_bar – typically a small number of actions with weights.
•	equity:
o	hero – hero’s total equity.
o	players – optional per-seat entries for multiway.
o	backend, mode, exact, iters – backend metadata where available.
•	thresholds:
o	pot_odds when relevant.
o	spr when stack information is supplied.
•	rationale:
o	Human-readable explanation: “Hero equity X% vs required Y%; recommend [bucket]”, etc.
/api/coach/advice uses this service as the postflop backend for AdviceV1.
________________________________________
5. Coach UI (Table overlay)
5.1 Location & toggle
•	The coach UI lives in the table page as a help overlay.
•	User-controlled toggle:
o	When Off:
	The overlay is hidden.
	The frontend does not call /api/coach/advice for overlay purposes.
o	When On:
	The overlay fetches advice for the current decision.
The overlay also reads /api/meta (or equivalent) to learn:
•	Whether coaching is generally enabled.
•	Which features are available (e.g. advice route, equity support, version numbers).
5.2 Behaviour
When the overlay is On and a given decision is visible (identified by hand_id and idx):
1.	Primary call
o	GET /api/coach/advice?hand_id=…&idx=…
o	Interprets the response as AdviceV1.
2.	Optional preflop fallback
o	If the environment is old or /api/coach/advice is unavailable and the street is preflop, the frontend may:
	Call GET /api/coach/preflop.
	Wrap the legacy payload into AdviceV1 client-side for display.
o	This is mostly relevant to transitional setups; in current code, /api/coach/advice is the standard path.
3.	Refetch rules
o	Advice is refetched when:
	hand_id changes.
	idx (decision index) changes.
	The overlay toggle or meta configuration changes.
o	There is no polling; advice is event-driven by decision changes.
5.3 What the user sees
When AdviceV1.status = "ok":
•	Recommended action
o	Derived from recommendation.bucket using existing bucket → UI mapping.
o	Used to highlight the recommended button on the table.
•	Strategy bar
o	Rendered from recommendation.strategy_bar as a bar chart of bucket weights.
•	Equity section
o	For HU:
	Single hero-equity bar from equity.hero.
o	For multiway (when equity.players is present and n_players > 2):
	Hero vs field summary.
	Optional per-seat equity list.
•	Pot odds / hints
o	When thresholds.pot_odds is present, the UI may show:
	“Required equity to continue”, compared against equity.hero.
•	Rationale
o	Text block from rationale, explaining the recommendation in plain language.
When AdviceV1.status != "ok":
•	The overlay shows a compact status message instead of action / equity details:
o	"disabled" – “Coach disabled.”
o	"unsupported" – “Unsupported spot.”
o	"timeout" – “Coach timed out.”
o	"not_found" – “Decision not found.”
o	"error" – “Coach error; advice unavailable.”
5.4 Status mapping (UI)
The overlay uses AdviceV1.status as the canonical status field:
•	ok → show full advice (bucket, strategy, equity, rationale).
•	disabled → show disabled message; no advice.
•	unsupported → show unsupported message.
•	timeout → show timeout message.
•	not_found → show “decision not found” (typically dev / stale link).
•	error → show generic error message.
Network / HTTP errors:
•	For network failures or non-JSON 5xx responses:
o	The overlay treats them as a transient “unavailable” error.
o	The table itself remains functional.
________________________________________
6. Logging & exports (high-level)
Coaching integrates with logging and exports to make behaviour testable and debuggable.
6.1 Snapshot types
There are three main snapshot types:
•	equity_snapshot – from POST /api/equity (when LOG_EQUITY_SNAPSHOT=true).
•	preflop_advice – from GET /api/coach/preflop (when LOG_PREFLOP_ADVICE=true).
•	coach_advice – from GET /api/coach/advice (when LOG_COACH_ADVICE=true).
Each snapshot is tied to a specific (hand_id, idx) decision row in the log DB.
6.2 Logging configuration
Controlled by backend.config (see CONFIGURATION.md):
•	LOG_EQUITY_SNAPSHOT:
o	When true, successful /api/equity calls with hand_id and idx are logged via log_equity_snapshot.
o	Exposed in exports as equity_snapshot.
•	LOG_EQUITY_SNAPSHOT_REDACT:
o	When true, log_equity_snapshot stores a redacted version (no raw cards/ranges).
•	LOG_PREFLOP_ADVICE:
o	When true, successful /api/coach/preflop responses are logged via log_preflop_advice.
o	Exposed as preflop_advice on exports.
•	LOG_COACH_ADVICE:
o	When true, successful /api/coach/advice responses are logged via log_coach_advice.
o	Exposed as coach_advice on exports, storing the full AdviceV1 payload.
Logging helpers live in:
•	backend/logger.py:
o	log_equity_snapshot(hand_id, idx, snapshot)
o	log_preflop_advice(hand_id, idx, advice)
o	log_coach_advice(hand_id, idx, advice_v1)
All logging is best-effort:
•	Schema issues or DB errors are swallowed.
•	Logging must never break the main application flow.
6.3 Exports
Export endpoints (/api/export/hand/{hand_id}.json and /api/export/session/{session_id}.json) surface these snapshots:
Per action (actions[*]) in export JSON:
•	equity_snapshot:
o	Mirrors the equity API response (possibly trimmed/redacted).
•	preflop_advice:
o	Mirrors the legacy preflop advisor payload.
•	coach_advice:
o	Mirrors the unified /api/coach/advice payload:
	Today: full AdviceV1 object.
	Previously: solver-centric shape in earlier phases (for older logs).
Key points:
•	All three fields are optional and appear only when:
o	Logging flags are enabled, and
o	The corresponding endpoints were actually called with hand_id/idx in scope.
•	When both LOG_PREFLOP_ADVICE and LOG_COACH_ADVICE are true:
o	Preflop decisions may have both:
	preflop_advice (legacy shape), and
	coach_advice (unified AdviceV1).
CSV exports (*.csv):
•	Intentionally minimal and do not include snapshot columns.
•	JSON exports are the source of truth for snapshot data.
6.4 Operational notes
For operational details (how to enable logging in prod, where DB files live, how to inspect snapshots), see:
•	docs/API-CONTRACT.md – HTTP contract and export examples.
•	docs/CONFIGURATION.md – configuration flags and sample .env.
•	docs/RUNBOOK.md – runbook for debugging and log inspection.
•	docs/COACH-ADVICE-PAYLOAD.md – detailed schema for the coach_advice payload.
