# API Contract

This document describes the HTTP API exposed by the trainer backend. The
contract has been updated to reflect recent behavioural changes, including
total-amount semantics for bet sizing, clearer bot orchestration, unified
gating via environment variables, and optional equity / coaching helpers.

For the *universal* coaching payload shape (target), see
`COACH-ADVICE-PAYLOAD.md`.

---

## POST `/api/hand/action`

Submits an action on behalf of the human player. The request must specify the
acting seat, the type of action, and—when betting or raising—the **total
committed amount** (not the delta). Off-tree totals are snapped to the nearest
legal bucket.

### Request

```json
{
  "seat": 0,
  "action": "bet",
  "amount": 320
}
# API Contract

This document describes the HTTP API exposed by the trainer backend. The
contract has been updated to reflect recent behavioural changes, including
total-amount semantics for bet sizing, clearer bot orchestration, unified
gating via environment variables, and optional equity / coaching helpers.

For the *universal* coaching payload shape (target), see
`COACH-ADVICE-PAYLOAD.md`.

---

## POST `/api/hand/action`

Submits an action on behalf of the human player. The request must specify the
acting seat, the type of action, and—when betting or raising—the **total
committed amount** (not the delta). Off-tree totals are snapped to the nearest
legal bucket.

### Request

```json
{
  "seat": 0,
  "action": "bet",
  "amount": 320
•	} seat – seat index of the acting player.
•	action – one of "fold", "check", "call", "bet", or "raise". When
to_call is zero (including a true heads-up small blind open preflop), a
raise is normalised to a "bet".
•	amount – the total stack commitment target for "bet" or "raise".
The backend will map the request to one of the allowed buckets, snapping
off-tree totals up or down. Requests below the minimum raise total
trigger an HTTP 400 error.
An invalid amount yields a descriptive error, for example:
{ "detail": "min-raise not met: need ≥ 320, got 220" }
Response
The response reports the state after the human action and before
any subsequent bot actions. Bots are not auto-advanced by this endpoint
anymore; they are advanced explicitly via POST /api/hand/auto.
Example:
{
  "ok": true,
  "bots_applied": [],
  "state": {
    "table": {
      "seats": 2,
      "sb": 50,
      "bb": 100,
      "ante": 0,
      "button": 1,
      "sb_seat": 1,
      "bb_seat": 0
    },
    "players": [
      { "seat": 0, "hole_cards": ["Ah", "Ad"] },
      { "seat": 1, "hole_cards": ["XX", "XX"] }
    ],
    "street": "flop",
    "board": { "flop": ["Jh", "Qs", "8h"], "turn": [], "river": [] },
    "deck_seed": "T08:4",
    "pot_total": 420,
    "to_act": 1,
    "allowed": {
      "to_call": 220,
      "min_raise": 540,
      "allowed_buckets": ["fold", "call", "2.5xR", "3.0xR", "jam"]
    },
    "last_action": {
      "seat": 0,
      "type": "bet",
      "requested": 320,
      "committed": 320,
      "snapped": false,
      "bucket_label": "2.2x",
      "allowed_buckets": ["check", "2.2x", "2.5x", "3.0x", "jam"]
    }
  }
}
•	bots_applied – list of auto-applied bot actions taken by this call.
For POST /api/hand/action this is currently always an empty array; bots
are advanced via POST /api/hand/auto.
•	state – the full game state after the human move, described in
STATE-SCHEMA.md. This shape is shared with /api/hand/state.
last_action summarises the human action, including:
•	requested – total commitment target requested in the API call.
•	committed – actual total commitment applied after snapping to the nearest
bucket.
•	snapped – whether the request was snapped.
•	bucket_label – human-friendly label of the bucket used.
•	allowed_buckets – legal buckets at the time of the action.
Important: bucket labels (e.g. "2.2x", "2.5xR") are
human-readable sizing classes, not literal multipliers of the big blind.
The exact numeric totals are contextual (street, current price, last raise
size). Clients may compute a candidate total using the rules in “Bet Trees”,
but it is also fine to submit any total; the engine will snap it to the
nearest legal bucket and indicate this with last_action.snapped.
________________________________________
GET /api/hand/state
Returns the current game state and information about the actor whose turn it
is.
{
  "state": { /* same shape as in POST /api/hand/action */ },
  "actor": {
    "seat": 1,
    "to_call": 220,
    "min_raise": 540,
    "allowed_buckets": ["fold", "call", "2.5xR", "3.0xR", "jam"]
  }
}
•	state – full public state, as described in STATE-SCHEMA.md.
•	actor – redundant information about the current actor; its fields mirror
state.to_act and state.allowed.
________________________________________
POST /api/hand/start
Starts a new hand. If the session is configured with a bot mode other than
"none", the engine will automatically play out bot actions up to the first
human decision.
The response is:
{ "hand_id": "H1" }
where hand_id is a string identifier such as "H1".
________________________________________
POST /api/hand/auto
Auto-advances the engine by applying bot actions until it is the human
player's turn again (or the hand ends).
This endpoint is gated by the environment variable HAND_AUTO_ENABLED
(plus any runtime overrides). When disabled it returns HTTP 501 and should
not be called.
When enabled it returns the same structure as a normal action response:
{
  "ok": true,
  "bots_applied": [
    { "seat": 1, "action": "call", "amount": null }
  ],
  "state": { /* snapshot after these bot actions */ }
}
•	bots_applied – sequence of bot actions taken during this call.
•	state – post-bot snapshot, after all auto-advanced bot actions.
________________________________________
Conventions & notes (hand endpoints)
•	Min-raise formula
The minimum raise total is:
min_raise_total = current_price + max(bb, last_raise_size)
•	Attempting to raise below this threshold yields 400 with a descriptive
message.
•	Buckets
Allowed bet sizes are published as human-readable labels:
o	When to_call is 0 or when opening heads-up as the small blind,
open buckets are ["2.2x","2.5x","3.0x","jam"].
o	When facing a bet or raise (to_call > 0), raise buckets acquire an
"R" suffix, for example ["fold","call","2.5xR","3.0xR","jam"].
All labels refer to total commitment targets; the engine snaps arbitrary
totals to these buckets.
•	Snapping
Requests between buckets are snapped to the nearest bucket. The response
sets snapped=true when this occurs and reports the snapped committed
amount.
•	Snapshots & bots
o	POST /api/hand/action:
	Applies only the human action.
	Returns a state snapshot after the human move, before any further
bot decisions.
	bots_applied is always [].
o	POST /api/hand/auto:
	Applies one or more bot actions.
	Returns a state snapshot after those bot actions.
	bots_applied lists all bot moves applied in that call.
•	Gating
HAND_AUTO_ENABLED controls exposure of /api/hand/auto. The helper
_hand_auto_enabled() also honours a process-local environment override.
•	Debugging
When ENGINE_DEBUG_HTTP=true structured debug events are emitted by the
engine. See debugging docs for details.
Status codes (hand endpoints)
Status	When	Example body
400	Minimum raise total not met / invalid action / wrong seat	{ "detail": "min-raise not met: need ≥ 540, got 500" }
422	Validation error (shape/verb)	Pydantic validation message
501	/api/hand/auto disabled by gating	{ "detail": "hand auto endpoint disabled" }
Worked example: minimum raise total
Assume bb = 100, current price (total to call) is 320 and the previous
raise size was 220.
min_raise_total = current_price + max(bb, last_raise_size)
                = 320 + max(100, 220)
                = 540
Submitting "raise": 500 will return 400 with a descriptive message;
submitting 520 may snap to the legal bucket (e.g. 540) and report
snapped=true.
________________________________________
Equity API
The equity service is exposed over HTTP via POST /api/equity. It computes
hand or range equities using the configured backend policy. This endpoint is
primarily intended for development, testing and preflop/postflop coach
research. It is not required by the core table flow.
For background on backends and configuration, see EQUITY.md.
POST /api/equity
Request body
{
  "players": [
    { "hand": ["Ah", "Ad"] },
    { "hand": ["Kh", "Qh"] }
  ],
  "board": ["As", "Kd", "2c"],
  "dead": [],
  "iters": 20000,
  "exact": false,
  "timeout_ms": 500
}
•	players – list of player specifications. Each entry must have either:
o	hand: two card strings such as ["Ah","Ad"], or
o	range: a range string such as "JJ+" or "random".
All players in one request must use the same mode (all hands or all ranges).
•	board – optional list of known board cards (0–5 cards). Duplicates or
collisions with hole cards or dead cards are rejected.
•	dead – optional list of dead cards removed from the deck. Cards may not
appear in both board and dead.
•	iters – optional integer specifying the number of Monte Carlo samples for
non-exact runs. When omitted, the service uses the EQUITY_ITERS default.
•	exact – boolean requesting exact enumeration where supported. When true,
ranges may be rejected depending on backend; when unsupported, the service
falls back or errors with a clear 400.
•	timeout_ms – optional soft timeout hint (milliseconds). Backends may use
this to bound long-running simulations.
Multiway note: Multiway range equities (3–6 players) require a
multiway-capable backend (primarily ompeval). If an appropriate backend is
unavailable, a clear 400 is returned.
Query parameters (logging)
The equity endpoint also accepts optional query parameters used only for
logging and export snapshot association:
•	hand_id – optional string. When provided and LOG_EQUITY_SNAPSHOT=true,
successful equity calls are logged and associated with this hand.
•	idx – optional integer (0-based). Indicates which decision index within
the hand the snapshot belongs to.
These parameters do not affect the equity calculation itself.
Response
{
  "ok": true,
  "backend": "ompeval",
  "mode": "hands",
  "n_players": 2,
  "board": ["As","Kd","2c"],
  "dead": [],
  "exact": false,
  "iters": 20000,
  "players": [
    { "win": 123, "tie": 4, "equity": 0.6521 },
    { "win": 65,  "tie": 4, "equity": 0.3479 }
  ],
  "raw": {
    "backend_specific": "..."
  }
}
•	backend – name of the backend that produced the result
("ompeval", "eval7", or "pokerkit").
•	mode – "hands" when players specify fixed hands, "ranges" when ranges
are used.
•	n_players – number of players (minimum 2).
•	board, dead – echo the effective board and dead cards used.
•	exact – whether the result is based on full enumeration.
•	iters – effective number of Monte Carlo samples (may be null for exact).
•	players – list of per-player result objects:
o	win – number of wins (backend-specific units).
o	tie – number of ties.
o	equity – normalized equity in [0,1].
•	raw – backend-specific details (e.g., samples, stderr, threads).
Intended for debugging and benchmarking.
Errors
Typical error conditions:
Status	Condition	Example body
400	Invalid input (malformed cards, duplicate cards, mixed)	{ "detail": "duplicate cards across players/board/dead" }
400	Requested mode unsupported by available backend/policy	{ "detail": "no equity backend available for requested mode" }
Backend selection
The backend used is selected according to the EQUITY_BACKEND_POLICY
environment variable:
•	auto – default; tries backends in order (ompeval → eval7 → pokerkit)
and picks the first compatible one for the request (e.g., ranges/multiway
prefer ompeval).
•	ompeval – force the OMPEval backend (supports ranges + multiway up to 6 players).
•	eval7 – force the Eval7 backend (pure-Python/Cython; ranges supported; slower).
•	pokerkit – pure-Python fallback (hands-focused).
See EQUITY.md for full details.
________________________________________
Coaching APIs
The coaching APIs provide guidance on preflop and postflop decisions.
•	Long-term, all modern coaching flows use a single, versioned Advice
payload (AdviceV1) described in COACH-ADVICE-PAYLOAD.md.
•	The current /api/coach/advice implementation still returns a
solver-centric payload; AdviceV1 is the target shape.
GET /api/coach/advice (universal advice, transitional)
The universal coaching endpoint. Returns coach guidance for a given decision.
Query parameters
•	hand_id – required. Identifies the hand for which advice is requested.
Must correspond to a hand started via /api/hand/start.
•	idx – required integer (0-based). Decision index within the hand.
Internally the coach uses these to:
•	locate the current hand state,
•	build a shared decision context (street, hero seat, pot, to_call, board, etc.),
•	route to the appropriate coach (solver-backed postflop, future preflop path, or rule-based stub).
Current response shape (Task-2 / solver-centric)
Today, /api/coach/advice returns a solver-centric payload:
{
  "recommended_bucket": "2.5xR",
  "strategy": { "fold": 0.1, "2.5xR": 0.9 },
  "ev_map": { "fold": 0.0, "2.5xR": 1.23 },
  "meta": {
    "status": "ok",
    "cached": false,
    "latency_ms": 12.3,
    "node_key": "aabbcc...ff"
  }
}
•	recommended_bucket – chosen bucket label for the current decision.
•	strategy – bucket → weight map representing a mixed strategy.
•	ev_map – optional per-bucket EVs, when available.
•	meta:
o	status – "ok" | "disabled" | "unsupported" | "timeout" | "error".
o	cached – whether the result was served from the solver cache.
o	latency_ms – wall-clock latency for this advice computation.
o	node_key – deterministic key for this node (used by the solver cache).
Status / HTTP mapping (current behaviour):
•	200 with meta.status = "ok" – actionable solver advice.
•	501 with meta.status = "disabled" – coach disabled (COACH_ENABLED=false).
•	501 with meta.status = "unsupported" – spot unsupported (e.g., preflop or multiway in this phase).
•	504 with meta.status = "timeout" – solver path timed out.
•	500 with meta.status = "error" – unexpected internal error.
A separate CoachDisabledError or UnsupportedSpotError inside the solver
path is mapped into the same meta.status values and HTTP codes.
Target AdviceV1 shape (future)
In the unified model, this route will return a single AdviceV1 object:
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
Key points (when AdviceV1 is live):
•	version – payload version; currently 1.
•	status – coaching outcome for this decision:
o	"ok" – advice is actionable.
o	"disabled" – coach globally off via configuration.
o	"unsupported" – decision not supported (street, multiway, backend limits, etc.).
o	"not_found" – hand or decision not found.
o	"timeout" – solver/equity exceeded configured budget.
o	"error" – internal error (unexpected).
•	meta – minimal context (street, number of active players, hero seat, advice source).
•	recommendation – primary bucket plus strategy bar (action → weight).
•	equity – optional, filled when the coach used the equity service.
•	thresholds – optional; e.g. pot odds, SPR.
•	rationale – human-readable explanation.
Street- and mode-specific behaviour (target):
•	Preflop:
o	Delegates to the preflop advisor.
o	Wraps its output into AdviceV1 with meta.source = "chart" | "equity" | "rule".
o	equity and thresholds may be left null initially.
•	Postflop HU:
o	Uses an equity- or solver-based postflop coach.
o	Fills equity and thresholds.pot_odds where possible.
•	Postflop multiway:
o	Uses a multiway coach when enabled + supported by equity backends.
o	Emits per-seat equities in equity.players when available.
o	Otherwise returns status="unsupported".
As the implementation moves to AdviceV1, the HTTP model may also converge
towards “always 200 for normal outcomes, status inside the payload”.
Logging
When advice snapshot logging is enabled, successful calls to
/api/coach/advice may be logged as coach_advice snapshots and surfaced in
JSON exports (see below). The snapshot shape mirrors whatever the endpoint
returns:
•	currently: the solver-centric payload { recommended_bucket, strategy, ev_map, meta };
•	future unified model: the full AdviceV1 object.
Snapshot gating for /api/coach/advice is currently handled by internal
helpers (backend.coach.advice_store and logger configuration). A dedicated
LOG_COACH_ADVICE environment flag may be introduced in a later milestone.
________________________________________
GET /api/coach/preflop (legacy preflop advisor)
The preflop advisor provides heads-up preflop guidance using charts plus
optional equity / rule fallbacks. It is exposed via GET /api/coach/preflop
and gated by COACH_ENABLED.
For charts, configuration and decision logic, see PREFLOP-ADVISOR.md.
Query parameters
•	hand_id – required. Identifies the hand for which advice is requested.
Must correspond to a hand started via /api/hand/start.
•	idx – optional integer (default 0). Decision index within the hand.
Internally the advisor uses these to:
•	locate the current hand state,
•	derive the preflop node (e.g. sb_open, bb_vs_sb_open),
•	canonicalize the hero hand (e.g. "AJo", "KTs", "JJ").
Successful response (200 OK)
On success the endpoint returns a preflop-only advice object:
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
•	source – where the advice came from:
o	"chart" – from a chart row.
o	"equity" – from equity fallback vs an assumed villain range.
o	"rule" – from a simple rule fallback when chart/equity are not usable.
•	bucket – recommended primary action bucket ("fold", "call", "2.2x",
"2.5x", "3.0x", "jam", etc.).
•	rationale – short human-readable explanation of the advice source and rule.
•	strategy_bar – map of bucket → weight (float), typically summing to ≈ 1.0.
Relationship to AdviceV1:
•	These fields map directly into the universal advice shape:
o	source → meta.source
o	bucket → recommendation.bucket
o	strategy_bar → recommendation.strategy_bar
o	rationale → rationale
•	The legacy endpoint does not include equity or thresholds. Clients that
prefer a single universal shape should call /api/coach/advice and treat
/api/coach/preflop as a compatibility fallback.
Errors
Status	Condition	Example body
400	Bad input (invalid idx, malformed query)	{ "detail": "invalid idx" }
404	No advice available (no node, no fallback)	{ "detail": "no advice for node" }
501	Coaching disabled or charts unusable	{ "detail": "preflop coach is disabled" }
Exact error messages may vary but should remain descriptive.
Logging
When LOG_PREFLOP_ADVICE=true, successful advice responses associated with a
(hand_id, idx) pair are stored as snapshots via logger helpers. These
snapshots are surfaced in export JSON under the preflop_advice field for the
corresponding action.
________________________________________
Export endpoints & snapshots
The export endpoints expose per-hand and per-session replays, including (when
enabled) equity and coaching snapshots.
Exports are the source of truth for:
•	what the engine did at each decision,
•	what equities were computed,
•	what advice was shown (preflop + all streets).
GET /api/export/hand/{hand_id}.json
Returns a JSON document describing a single hand. The exact schema is defined
in the export module, but at a high level:
{
  "hand_id": "H1",
  "session_id": 1,
  "state": { /* initial + terminal state snapshot */ },
  "actions": [
    {
      "idx": 0,
      "street": "pre",
      "actor_seat": 0,
      "action": "bet",
      "amount": 250,
      "...": "...",
      "equity_snapshot": {
        "backend": "ompeval",
        "mode": "hands",
        "board": [],
        "dead": [],
        "players": [
          { "equity": 0.62 },
          { "equity": 0.38 }
        ],
        "raw": { "...": "..." }
      },
      "preflop_advice": {
        "source": "chart",
        "bucket": "2.5x",
        "rationale": "chart:HU_25bb_srp_vsb; node=sb_open; hand=AJo",
        "strategy_bar": {
          "fold": 0.15,
          "call": 0.55,
          "2.5x": 0.30
        }
      },
      "coach_advice": {
        /* shape mirrors /api/coach/advice:
           - currently: solver payload { recommended_bucket, strategy, ev_map, meta }
           - future: AdviceV1 payload as defined in COACH-ADVICE-PAYLOAD.md */
      }
    }
  ]
}
Notes:
•	equity_snapshot, preflop_advice, and coach_advice are all optional and
appear only when:
o	the relevant logging flags / helpers are enabled, and
o	the corresponding API calls were made with hand_id/idx in scope.
•	When logging is disabled, these fields are simply absent.
•	Shapes:
o	equity_snapshot mirrors the equity API response (possibly trimmed / redacted).
o	preflop_advice mirrors the legacy preflop API response.
o	coach_advice mirrors the /api/coach/advice response:
	solver-centric payload today;
	AdviceV1 once the unified coach API is wired.
Consumers that want a single all-streets view of advice should prefer
coach_advice. preflop_advice remains for older tools that only know about
the legacy preflop endpoint.
GET /api/export/session/{session_id}.json
Returns a JSON document describing a session. At a high level:
{
  "session_id": 1,
  "meta": { /* session metadata */ },
  "hands": [
    {
      "hand_id": "H1",
      "state": { /* ... */ },
      "actions": [
        {
          "idx": 0,
          "street": "pre",
          "actor_seat": 0,
          "action": "bet",
          "amount": 250,
          "...": "...",
          "equity_snapshot": { /* optional, as above */ },
          "preflop_advice": { /* optional, as above */ },
          "coach_advice": { /* optional, as above */ }
        }
      ]
    }
  ]
}
Each hand’s actions array follows the same conventions as the single-hand
export: optional equity_snapshot, preflop_advice, and coach_advice
objects per action.
CSV exports
CSV exports remain intentionally minimal and stable:
•	GET /api/export/hand/{hand_id}.csv
•	GET /api/export/session/{session_id}.csv
These do not include snapshot-specific columns for equity or coaching
advice. They retain the existing schema (action index, actor, action, amount,
street, etc.) and are not affected by snapshot logging.
JSON exports are the source of truth for snapshot data.
Snapshot configuration
The following environment variables control snapshot behaviour (see
CONFIGURATION.md for details):
•	LOG_EQUITY_SNAPSHOT – when true, successful /api/equity calls with
hand_id and idx are logged and attached as equity_snapshot.
•	LOG_EQUITY_SNAPSHOT_REDACT – when true, logged equity snapshots may
omit or abstract sensitive card/range information in production.
•	LOG_PREFLOP_ADVICE – when true, successful /api/coach/preflop calls
are logged and attached as preflop_advice.
Snapshots for /api/coach/advice are currently controlled by internal coach
logging helpers (backend.coach.advice_store and logger configuration). A
dedicated LOG_COACH_ADVICE flag may be added in a future milestone; refer to
CONFIGURATION.md for the latest configuration surface.
All snapshot fields are optional and backwards-compatible: old exports remain
valid and consumers should treat missing snapshots as “not logged”.

#### M3 notes: Postflop coach (HU) and AdviceV1

Once the M3 wiring is complete, `/api/coach/advice` will return the unified `AdviceV1` payload (see `COACH-ADVICE-PAYLOAD.md`) for both **preflop** and **postflop** decisions.

**Behaviour overview (target):**

- **Preflop (any supported spot)**
  - Advice is backed by the preflop advisor (`PreflopAdvisorService`).
  - Response is an `AdviceV1` object with:
    - `meta.street = "preflop"`
    - `meta.source ∈ {"chart","equity","rule"}` depending on how the recommendation was produced.
  - The legacy `/api/coach/preflop` endpoint is a specialised view over the same underlying logic.

- **Postflop HU (heads-up, flop/turn/river)**
  - Advice is backed by the **postflop coach** using `DecisionContext` + `EquityService`.
  - Response is an `AdviceV1` object with:
    - `meta.street ∈ {"flop","turn","river"}`
    - `meta.n_players = 2`
    - `meta.source = "equity"`
    - `recommendation.bucket` mapped to one of the engine’s allowed buckets (`fold`, `call`, `check`, bet/raise buckets, etc.).
    - `recommendation.strategy_bar` describing a (usually simple) mixed strategy.
    - `equity.hero` and `equity.players` filled from the equity engine.
    - `thresholds.pot_odds` filled when a call/fold decision is being priced.

- **Multiway postflop (3+ players)**
  - If a multiway-capable backend and coach configuration are available, the route may return full `AdviceV1` with `meta.n_players > 2` and a `players` equity list.
  - If multiway coaching is not available or disabled, the route should still respond with `200` and:
    - `status = "unsupported"`
    - `meta.street` and `meta.n_players` set appropriately
    - No `recommendation` / `equity` body, or those fields omitted.

**Status semantics (target):**

- `status = "ok"`  
  Advice is actionable and includes at least `meta`, `recommendation.bucket` and `rationale`. For HU postflop this implies a valid equity computation was completed or a safe fallback rule was applied.

- `status = "unsupported"`  
  The route is reachable but cannot provide advice for this spot under current configuration (e.g. multiway coach disabled, no suitable equity backend, or spot outside supported scope).

- `status = "disabled"`  
  Global coach gate disabled (e.g. `COACH_ENABLED=false`). The route may also return HTTP `501` in this case.

- Other statuses (`"timeout"`, `"not_found"`, `"error"`) follow the general `AdviceV1` contract and apply equally to preflop and postflop.

> **Note:** Preflop and postflop routes share the same `AdviceV1` schema; the main differences are in `meta.street`, `meta.source` and which optional blocks (`equity`, `thresholds`) are populated.
