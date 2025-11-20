# docs/COACH-ADVICE-PAYLOAD.md
# Coach Advice Payload (AdviceV1)

**Status:** Draft v1 (M3)  
**Audience:** Backend, frontend, tooling, and QA  
**Purpose:** Define a single, versioned payload that describes coaching advice for any decision on any street (preflop → river), HU or multiway.

This document is the **canonical reference** for the “Advice” object returned by coaching endpoints and stored in exports.

---

## 1. Scope & Goals

The Advice payload is designed to:

- Represent a **single decision** in a hand (identified by `hand_id` + `idx`).
- Cover **all streets**:
  - `preflop`, `flop`, `turn`, `river`, plus `showdown`/`unknown` as needed.
- Work for **any number of players**:
  - Heads-up or multiway (3–6 players).
- Unify several existing concepts:
  - Preflop coach output (`/api/coach/preflop`).
  - Equity snapshots (`/api/equity`).
  - Future postflop coaching (HU and multiway).
- Provide a **stable contract** for:
  - `/api/coach/advice`
  - Frontend overlay
  - Logging and exports (`coach_advice` snapshot)

The payload is intentionally **versioned** so it can evolve without breaking older clients or exports.

---

## 2. Versioning & Status

### 2.1. Version

All Advice objects include a `version` field:

- `version: 1` for this initial specification.
- Future changes that are **not backward compatible** must bump this value.

Clients must be prepared to:

- Accept `version >= 1`.
- Gracefully degrade or ignore unknown fields.

### 2.2. Status

Advice objects are **always returned with a `status` field**, even when no actionable recommendation is available.

Status values:

- `ok`  
  Advice is valid and actionable (recommendation present).

- `disabled`  
  Coach is globally disabled by configuration (e.g. `COACH_ENABLED=false`).

- `unsupported`  
  The specific decision is not supported by the current coach configuration or backends  
  (e.g. multiway equity not available, street not implemented).

- `not_found`  
  The referenced hand/decision (`hand_id`, `idx`) could not be found.

- `timeout`  
  Coach attempted to compute advice but exceeded a time budget (e.g. solver/equity timeout).

- `error`  
  Unexpected internal error; advice is not trustworthy.

**HTTP semantics:**

- For **normal runtime states** (`ok`, `disabled`, `unsupported`, `timeout`, `not_found`), the endpoint **should prefer `200 OK`** and encode the state in `status`.
- HTTP `5xx` should be reserved for genuine infrastructure failures.
- HTTP `501` is allowed when a route is _globally_ not implemented or gated by config.

---

## 3. Top-Level Shape (AdviceV1)

This is the conceptual shape of AdviceV1. Exact language-specific types live in code, but must follow this structure.

```text
AdviceV1 {
  version: 1
  status: 'ok' | 'disabled' | 'unsupported' | 'not_found' | 'timeout' | 'error'

  meta: {
    street: 'preflop' | 'flop' | 'turn' | 'river' | 'showdown' | 'unknown'
    n_players: number
    hero_seat: number
    source: 'chart' | 'equity' | 'rule' | 'mixed'
  }

  recommendation?: {
    bucket: string                        // 'fold' | 'call' | 'check' | '2.5x' | '2.5xR' | 'jam' | ...
    strategy_bar?: Array<{
      action: string                      // bucket label (e.g. 'fold', 'call', '2.5xR')
      weight: number                      // 0..1, typically summing to 1
    }>
  }

  equity?: {
    backend: string                       // e.g. 'ompeval', 'eval7', 'pokerkit'
    mode: 'hands' | 'ranges'
    hero: number                          // 0..1, hero's equity vs the field
    players?: Array<{
      seat: number                        // seat index as used in engine/state
      equity: number                      // 0..1, per-player equity
    }>
    vs_field?: number                     // 0..1, hero vs everyone else combined (optional view)
    exact?: boolean                       // true if exact algorithm, false if Monte Carlo
    iters?: number | null                 // MC iterations when applicable; null/omitted for exact
  }

  thresholds?: {
    pot_odds?: number                     // 0..1 required equity to continue (call/bet/raise)
    spr?: number                          // stack-to-pot ratio at this decision (optional)
  }

  rationale?: string                      // human-readable explanation of the advice
}
Notes:
•	recommendation, equity, thresholds, and rationale are optional at the type level.
o	For status='ok', recommendation.bucket is expected to be present.
o	For non-ok statuses, they may be omitted or partially filled for debugging.
________________________________________
4. Field Reference
This section defines semantics for each group and field.
4.1. meta
Describes the context of the decision as understood by the coach.
•	meta.street
o	preflop | flop | turn | river
o	showdown may be used for informational snapshots when all cards are known.
o	unknown is allowed in edge cases where street cannot be resolved (should be rare).
•	meta.n_players
o	Number of active players in the pot at this decision.
o	Excludes players who have folded or left the hand.
o	Used by the frontend to distinguish HU vs multiway display.
•	meta.hero_seat
o	Seat index of the hero, consistent with engine/log and frontend.
•	meta.source
o	Primary origin of the advice:
	chart – From preflop charts.
	equity – From equity calculations (hero hand vs ranges).
	rule – From simple rule-based logic (no equity/solver).
	mixed – A combination (e.g. chart + equity, or equity + rules).
4.2. recommendation
Coach’s suggested line for this decision.
•	recommendation.bucket
o	Canonical action label, must match the existing bucket mapping used by the UI.
o	Examples (not exhaustive):
	fold
	call
	check
	2.2x, 2.5x, 3.0x
	2.2xR, 2.5xR, 3.0xR (raise sizes)
	jam
o	The frontend maps this label to a specific button/action.
•	recommendation.strategy_bar
o	Optional distribution over action buckets.
o	Each entry:
	action: bucket label.
	weight: 0..1. Weights are usually normalised to sum to ~1.
o	For deterministic recommendations, it may be a single bucket with weight=1.0.
o	For mixed strategies, it can express recommended frequencies (e.g. call 70%, raise 30%).
4.3. equity
View of equity at the decision.
•	equity.backend
o	Name of the backend that produced the equity:
	e.g. ompeval, eval7, pokerkit.
•	equity.mode
o	hands – all players are fixed hands.
o	ranges – at least one player is a range, not a single hand.
•	equity.hero
o	Hero’s equity vs the rest of the field, in [0,1].
o	For HU, this is equivalent to hero vs the single villain.
o	For multiway, this is hero’s marginal equity in the multiway simulation.
•	equity.players
o	Optional per-player equities.
o	Each entry:
	seat: seat number.
	equity: equity for that seat in [0,1].
o	For HU, this will usually contain exactly 2 entries.
o	For multiway, it may contain up to the number of active seats (e.g., 3–6).
•	equity.vs_field
o	Optional helper for UI: hero vs “everyone else combined” in [0,1].
o	Can be derived from equity.hero + tie information; the precise convention is backend-dependent.
o	Frontend may choose to display either hero or vs_field as the primary bar; both must be internally consistent.
•	equity.exact
o	true when the backend used an exact algorithm.
o	false when using Monte Carlo or approximate methods.
o	May be omitted when not meaningful.
•	equity.iters
o	Number of Monte Carlo iterations used, if applicable.
o	null or omitted for exact computations.
4.4. thresholds
Decision thresholds and derived metrics.
•	thresholds.pot_odds
o	Required equity to continue (e.g. to call) in [0,1].
o	For a simple call/fold decision:
	pot_odds ≈ to_call / (pot_total + to_call)
	Where pot_total is the pot before hero acts, and to_call is the additional amount hero must commit to continue.
o	Coaches can compare equity.hero against thresholds.pot_odds to classify ev_hint or drive bucket selection.
•	thresholds.spr
o	Stack-to-pot ratio at this decision (optional).
o	Defined as:
	spr ≈ effective_stack / pot_total
o	Useful mostly postflop to reason about jam vs smaller raises, pot control, etc.
4.5. rationale
Human-readable explanation of the advice.
•	Intended for:
o	Frontend overlay (text section).
o	Debugging and QA.
o	Exports and offline analysis.
•	May include:
o	Street and node description (e.g. “BB vs SB open, 25bb deep”).
o	Explanation of chart node or villain range profile.
o	Equity, pot odds, and a narrative of why the bucket was chosen.
o	Notes about multiway caution, stack depths, etc.
•	For status != 'ok', rationale may still be provided to explain why advice is disabled or unsupported.
________________________________________
5. Relationship to Existing Endpoints & Snapshots
5.1. /api/coach/preflop
•	Existing endpoint:
o	Returns a preflop-specific advice object with:
	source, bucket, strategy_bar, rationale.
•	Relationship to AdviceV1:
o	These fields map directly to:
	meta.source
	recommendation.bucket
	recommendation.strategy_bar
	rationale
o	For now, /api/coach/preflop does not return the full AdviceV1 shape.
•	Migration path:
o	/api/coach/advice becomes the universal route.
o	Preflop calls through /api/coach/advice will wrap preflop advisor results into AdviceV1.
o	/api/coach/preflop remains for compatibility (and may internally reuse the same code).
5.2. /api/coach/advice
•	Target universal coaching endpoint:
o	GET /api/coach/advice?hand_id=...&idx=...
•	Returns:
o	A single AdviceV1 object describing the decision at (hand_id, idx).
•	Behaviour:
o	Preflop:
	Uses preflop advisor and returns AdviceV1 with meta.source='chart' | 'equity' | 'rule'.
o	Postflop HU:
	Uses postflop equity-based coach; meta.source='equity'.
o	Postflop multiway:
	Uses multiway coach path when available or returns status='unsupported'.
o	Disabled or misconfigured:
	Returns AdviceV1 with status='disabled' or status='error' as appropriate.
5.3. /api/equity
•	Existing endpoint:
o	POST /api/equity returns a standalone equity response with backend/mode/players/board, etc.
•	Relationship to AdviceV1:
o	AdviceV1’s equity block is effectively an embedded, normalised view of the same information:
	backend, mode, exact/iters, per-player equities.
•	Migration path:
o	Overlay and coach logic will increasingly rely on equity inside AdviceV1 rather than direct /api/equity calls.
o	/api/equity remains for tooling, dev utilities, and explicit equity queries.
5.4. Exports & snapshots
Existing export fields:
•	preflop_advice
o	Snapshot of preflop advisor’s legacy payload.
•	equity_snapshot
o	Snapshot of /api/equity calls.
New field:
•	coach_advice
o	Snapshot of AdviceV1 as returned by /api/coach/advice for that decision.
Usage:
•	For all-streets advice, downstream tools should prefer coach_advice as the canonical “what the user saw”.
•	preflop_advice and equity_snapshot remain for:
o	Backwards compatibility.
o	Raw equity debugging.
________________________________________
6. Evolution Guidelines
To keep AdviceV1 stable and evolvable:
1.	Add fields, don’t repurpose.
o	Adding new optional fields to meta, recommendation, equity, thresholds, or at the top level is fine.
o	Avoid changing the semantics of existing fields.
2.	Use version for breaking changes.
o	If a change would:
	Remove fields,
	Change enum values,
	Change meaning of an existing field,
then introduce version: 2 and document it here.
3.	Keep status first-class.
o	New behaviours (e.g. “partially cached”, “solver fallback”) should be expressed via:
	status where appropriate.
	Additional fields in meta or equity for detail, rather than new top-level booleans.
4.	Frontend & exports tolerance.
o	Frontend should:
	Treat unknown status values as error.
	Ignore unknown fields.
o	Exports should:
	Persist the AdviceV1 blob as-is, without attempting to normalise away fields.
________________________________________
7. Minimal Expectations per Phase
This section describes what must be present in AdviceV1 in different rollout phases.
7.1. Preflop (legacy parity)
•	Required when status='ok' and meta.street='preflop':
o	meta.n_players, meta.hero_seat, meta.source
o	recommendation.bucket
o	rationale
•	Optional/initially null:
o	recommendation.strategy_bar (if not available from charts).
o	equity, thresholds.
7.2. Postflop HU coach v1
•	Required when status='ok' and HU flop/turn/river:
o	meta.street, meta.n_players, meta.hero_seat, meta.source='equity'
o	recommendation.bucket
o	equity.hero
o	thresholds.pot_odds
o	rationale explaining equity vs pot odds and decision.
7.3. Multiway coach
•	Required when status='ok' and meta.n_players > 2:
o	All of the above (where applicable), plus:
	equity.players with per-seat equities.
	equity.vs_field (recommended) or a documented convention for interpreting equity.hero in multiway.
If any of the above cannot be satisfied, the coach should prefer status='unsupported' rather than returning partial/incorrect advice with status='ok'.
________________________________________
8. Summary
•	AdviceV1 is the unified, versioned payload for all coaching.
•	It is returned by /api/coach/advice, partially mirrored by /api/coach/preflop, and stored in exports as coach_advice.
•	It combines:
o	Context (meta),
o	Recommendation (recommendation),
o	Equity view (equity),
o	Thresholds (thresholds),
o	Explanation (rationale),
under a single status and version.
•	All future coaching work (postflop, multiway, solver integration) should build on top of this payload rather than invent new shapes.

