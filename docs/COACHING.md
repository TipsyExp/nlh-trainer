# Coaching

This document describes how coaching works end-to-end:

- What the coach returns (the **Advice** payload).
- Which endpoints exist and how they relate.
- How backend coaching logic builds on a shared **decision context**.
- How the **Table overlay** consumes advice.
- How this ties into logging and exports at a high level.

For the full *target* Advice payload spec, see **`docs/COACH-ADVICE-PAYLOAD.md`**.

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
  - `bucket` – canonical action label (`fold`, `call`, `check`, `2.5x`, `2.5xR`, `jam`, …).
  - `strategy_bar` – action → weight distribution.
- `equity`: hero and per-player equities, backend, mode, iters, etc.
- `thresholds`: pot odds and optional SPR.
- `rationale`: human-readable explanation.

The Pydantic model for this lives in:

- `backend/schemas/advice.py` → `AdviceV1Model`

The detailed field list and semantics live in **`COACH-ADVICE-PAYLOAD.md`**, which should be treated as the canonical spec for the unified coach payload.

> **Important (current state vs target):**
>
> - The current `/api/coach/advice` implementation still returns a **solver-centric** payload (with a `meta.status` field and `strategy` / `ev_map`) rather than full `AdviceV1`.
> - The AdviceV1 model is already defined and will become the wire format for `/api/coach/advice` in a later milestone (M3).
> - Until that migration, clients should be able to consume the existing solver shape and be tolerant of the future AdviceV1 shape.

---

## 2. Endpoints

### 2.1 `/api/coach/advice` (universal route, transitional)

- **Method:** `GET`
- **Query:** `hand_id`, `idx` (current decision index).
- **Current response shape (solver-centric):**

  ```json
  {
    "recommended_bucket": "2.5xR",
    "strategy": { "fold": 0.1, "2.5xR": 0.9 },
    "ev_map": { "fold": 0.0, "2.5xR": 1.23 },
    "meta": {
      "status": "ok" | "disabled" | "unsupported" | "timeout" | "error",
      "cached": true,
      "latency_ms": 12.3,
      "node_key": "..."
    }
  }
•  Status codes (current implementation):
•	200 with meta.status="ok" on success.
•	501 with meta.status="disabled" when the coach is disabled.
•	501 with meta.status="unsupported" for unsupported spots.
•	504 with meta.status="timeout" when solver path times out.
•	500 with meta.status="error" on unexpected errors.
•  How it is implemented today:
•	Builds a canonical solver request using backend.coach.node_builder.build_solve_request_from_hand(hand_id, idx).
•	Uses backend.coach.texassolver_cache.resolve_with_cache plus TexasSolverAdapter to obtain a solver response.
•	Normalizes that into { recommended_bucket, strategy, ev_map, meta }.
•	Persists a small snapshot via backend.coach.advice_store.write_snapshot (node_key + solver payload).
•	Does not yet emit AdviceV1Model on the wire.
•  How it will behave in M3 (target):
•	The same route will return AdviceV1Model as defined in backend/schemas/advice.py:
{
  "version": 1,
  "status": "ok" | "disabled" | "unsupported" | "not_found" | "timeout" | "error",
  "meta": { "street": "...", "n_players": 2, "hero_seat": 0, "source": "..." },
  "recommendation": { "bucket": "...", "strategy_bar": [ ... ] },
  "equity": { ... },
  "thresholds": { ... },
  "rationale": "..."
}
•	
o	Status will move to the top level (status), with meta.status no longer required.
o	Street-specific behavior:
	Preflop:
	Delegates to the existing preflop advisor (PreflopAdvisorService).
	Wraps its Advice dataclass into AdviceV1 (meta.source='chart' | 'equity' | 'rule').
	Postflop HU:
	Uses solver / equity-based coaches built on the shared decision context.
	Fills equity and thresholds when available.
	Postflop multiway:
	Uses a multiway coach path when supported.
	Otherwise returns status='unsupported'.
•	During migration:
o	Backend may introduce an internal AdviceV1Model object even before the wire format flips.
o	Frontend should:
	Continue to understand the current solver payload with meta.status.
	Be ready to switch to AdviceV1 (top-level status, meta, recommendation, …) once the endpoint is upgraded.
When coaching is completely disabled at the service level (e.g. feature gated), the route may return 501 rather than 200 + status='disabled'.
2.2 /api/coach/preflop (legacy / specialised)
•	Method: GET
•	Query: hand_id, idx (preflop decision index).
•	Response: legacy preflop advice object:
{
  "source": "chart" | "equity" | "rule",
  "bucket": "2.5x",
  "strategy_bar": { "2.5x": 0.75, "jam": 0.25 },
  "rationale": "..."
}
Relationship to AdviceV1:
•	This is effectively a subset of AdviceV1:
o	source → meta.source
o	bucket → recommendation.bucket
o	strategy_bar → recommendation.strategy_bar
o	rationale → rationale
•	It exists for compatibility with older tooling and tests.
•	Internally, it uses PreflopAdvisorService (chart-first with optional equity fallback).
•	In the unified model, /api/coach/preflop may become a thin wrapper over the same logic that powers /api/coach/advice for preflop.
________________________________________
3. Decision context helper
Backend coaching logic does not work directly on raw engine state. Instead, it uses a shared decision context helper.
•	Module: backend/coach/decision_context.py
•	Primary entrypoints:
o	build_decision_context(hand_id, idx) – construct a context for a given decision.
o	Internal helpers that derive context from the current engine state as exposed by backend.api.hand.get_state and the engine adapter (PokerKitAdapter).
3.1 Shape (conceptual)
The helper produces a normalized context object (a DecisionContext dataclass) with at least:
•	Hand identity:
o	hand_id
o	idx (decision index; currently “current decision” in Task-2, later true replay index)
•	Game framing:
o	street ("preflop" | "flop" | "turn" | "river" | "showdown" | "unknown")
o	n_players (active players in the pot)
o	hero_seat
•	Cards:
o	hero_hole (hero’s hole cards, when known for the street).
o	board (current board cards as a flat 0–5 list).
•	Betting situation:
o	pot_total (before the hero acts).
o	to_call (chips required for hero to continue).
o	min_raise (total commitment required to meet the minimum raise rule; may be None in some spots).
o	allowed_buckets (canonical labels used by the UI and engine).
•	Stack / commitment (where available):
o	Effective stacks (IP/OOP) for solver requests.
o	Optional per-seat stacks & committed amounts (for EV/pot odds).
•	Status:
o	Which seats are active.
o	Whether the decision is terminal / already resolved.
The exact dataclass lives in backend/coach/decision_context.py; this section is intentionally conceptual so the UI and docs don’t depend on every field.
3.2 Current vs future sources of truth
•	Current Task-2 state:
o	Context is derived from the current engine state only.
o	idx is treated as a hint (“current decision index”) rather than performing true replay from logs.
o	Inputs:
	backend.adapters.engines.get_adapter().state()
	Session state (backend.api.session.get_session_state) for hero_seat.
	Public state shape documented in docs/STATE-SCHEMA.md.
•	Future extensions:
o	Logging / replay helpers will allow reconstructing state at a specific idx from the actions table.
o	Decision context will then be able to represent any historical decision in a hand rather than only the live one.
3.3 Consumers
•	/api/coach/advice – uses the context to drive coach logic and (eventually) construct AdviceV1Model.
•	Preflop advisor (PreflopAdvisorService) – uses context for node classification and sanity checks (e.g. SB open vs BB defend).
•	Postflop coach – uses hero hand, board, pot, and stacks for equity-based heuristics.
•	Solver integration (backend.coach.node_builder) – constructs SolveRequest objects (TexasSolver) from the same context.
•	(Later) Logging and exports – may attach serialized decision contexts to snapshots for debugging and offline analysis.
The goal is that all coaching and solver paths share one truthful view of a decision and avoid duplicating state derivation logic.
________________________________________
4. Coach UI (Table Overlay)
4.1 Location & toggle
•	Where: Table page, top-right panel.
•	Toggle: A user-controlled switch enables or disables guidance.
o	When Off: no calls to /api/coach/advice for overlay purposes.
o	When On: overlay fetches advice for the current decision.
The overlay also reads /api/meta to learn whether coaching is enabled and which capabilities are available (e.g. advice route presence and version, equity backend support).
4.2 Behavior
When the overlay is On:
•	For each visible decision (identified by hand_id + idx):
o	Primary call:
	GET /api/coach/advice?hand_id=…&idx=…
o	Fallback (preflop only):
	If /api/coach/advice is missing or returns 501/404 and the street is preflop, the UI may:
	Call /api/coach/preflop.
	Wrap that response into the AdviceV1 shape client-side for display if desired.
•	No polling:
o	The overlay refetches advice only when the decision index changes (or the overlay toggle/meta configuration changes).
o	Navigation between decisions (actions, auto-advance) drives advice refresh.
•	What the user sees when advice is actionable:
o	In the current solver payload:
	recommended_bucket highlights the suggested table button.
	strategy drives the strategy bar (bucket → weight).
	ev_map can be surfaced as EV hints per action.
o	In the AdviceV1 payload (target):
	recommendation.bucket and recommendation.strategy_bar drive the same UI.
	equity and thresholds power equity and pot-odds visualizations.
	rationale is displayed as textual explanation.
The overlay should be able to render the same UI regardless of street or player count, driven solely by either the current solver payload or the future AdviceV1 payload.
4.3 Status mapping (UI)
The overlay interprets coach status as follows.
Current implementation (meta.status in solver payload)
•	meta.status === "ok" – advice available; show recommendation / bar / EV.
•	meta.status === "disabled" – coach off via configuration; show “Coach disabled”.
•	meta.status === "unsupported" – specific decision not supported; show “Unsupported spot”.
•	meta.status === "timeout" – solver timed out; show “Timed out”.
•	meta.status === "error" – internal error; show generic error.
Target implementation (AdviceV1.status)
•	status === "ok" – advice available and rendered.
•	status === "disabled" – coach globally off.
•	status === "unsupported" – spot not supported under current coach policy/backends.
•	status === "timeout" – time/iteration budget exceeded.
•	status === "not_found" – hand or decision not found (typically dev / stale links).
•	status === "error" – internal error while computing advice.
Network / HTTP failures
•	For network failures or unexpected HTTP 5xx:
o	UI treats them as “Unavailable” and may surface a transient error message.
o	The overlay should remain robust and not break the table.
During migration, the overlay should:
•	Prefer status if a full AdviceV1 payload is present.
•	Otherwise, fall back to meta.status when dealing with the legacy solver payload.
________________________________________
5. Logging & Exports (high-level)
Coaching integrates with logging and exports to make behavior testable and debuggable.
•	When logging is enabled and /api/coach/advice is called for a given (hand_id, idx):
o	The current implementation persists a solver snapshot:
	node key
	solver payload { recommended_bucket, strategy, ev_map, meta }
o	In the unified AdviceV1 model, this will evolve into a coach_advice snapshot that stores the full AdviceV1 payload.
•	Existing snapshots:
o	preflop_advice – legacy preflop advisor payload (from /api/coach/preflop).
o	equity_snapshot – raw equity result from /api/equity.
o	Solver cache entries keyed by node_key in solver_cache.
Export endpoints (/api/export/hand, /api/export/session) will include these snapshots per action when present. Over time, coach_advice (AdviceV1) becomes the primary all-streets view of what was shown to the user, with solver-centric snapshots remaining as historical compatibility.
Details of the export format and logging flags live in:
•	docs/API-CONTRACT.md
•	docs/CONFIGURATION.md
•	docs/RUNBOOK.md
•	docs/COACH-ADVICE-PAYLOAD.md (for the AdviceV1 payload within coach_advice).
