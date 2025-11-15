
# API Contract

This document describes the HTTP API exposed by the trainer backend. The
contract has been updated to reflect recent behavioural changes, including
total-amount semantics for bet sizing, pre-bot snapshots in responses, unified
gating via environment variables, and optional equity / preflop coaching
helpers.

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
•	seat – seat index of the acting player.
•	action – one of "fold", "check", "call", "bet", or "raise". When
to_call is zero (including a true heads-up small blind open preflop), a
raise is normalised to a "bet".
•	amount – the total stack commitment target for "bet" or "raise".
The backend will map the request to one of the allowed buckets, snapping
off-tree totals up or down. Requests below the minimum raise total trigger
an HTTP 400 error.
An invalid amount yields a descriptive error:
{ "detail": "min-raise not met: need ≥ 320, got 220" }
Response
The response reports the state before any bot actions are applied.
Subsequent bot moves are returned separately.
{
  "ok": true,
  "bots_applied": [
    { "seat": 1, "action": "call", "amount": null }
  ],
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
•  bots_applied – list of auto-applied bot actions after the human move. Each
entry contains the bot seat, the normalised action and its total amount (if
applicable).
•  state – the full game state, described in State Schema
•	last_action – summary of the human action, including the requested total,
the actual amount committed, whether snapping occurred, the bucket label and
the list of allowed buckets at the time.
Important: bucket labels (e.g. 2.2x, 2.5xR) are human-readable sizing
classes, not literal multipliers of the big blind. The exact numeric totals
are contextual (street, current price, last raise size). Clients may compute
a candidate total using the rules in Bet Trees
but it is also
fine to submit any total; the engine will snap it to the nearest legal bucket
and indicate this with last_action.snapped.
________________________________________
GET /api/hand/state
Returns the current game state and information about the actor whose turn it
is.
{
  "state": { /* same shape as above */ },
  "actor": {
    "seat": 1,
    "to_call": 220,
    "min_raise": 540,
    "allowed_buckets": ["fold", "call", "2.5xR", "3.0xR", "jam"]
  }
}
The actor object contains redundant information about the current actor; its
fields mirror state.to_act and state.allowed.
________________________________________
POST /api/hand/start
Starts a new hand. If the session is configured with a bot mode other than
"none", the engine will automatically play out all bot actions until the
first human decision.
________________________________________
POST /api/hand/auto
Auto-advances the engine by applying bot actions until it is the human
player's turn again. This endpoint is gated by the environment variable
HAND_AUTO_ENABLED. When disabled it returns HTTP 501 and should not be
called. When enabled it returns the same structure as a normal action
response:
{
  "ok": true,
  "bots_applied": [...],
  "state": { ... }
}
Conventions & notes
•	Min-raise formula – The minimum raise total is computed as
current_price + max(bb, last_raise_size). Attempting to raise below this
threshold yields a 400.
•	Buckets – Allowed bet sizes are published as human-readable labels. When
to_call is 0 or when opening heads-up as the small blind, open buckets
are ["2.2x","2.5x","3.0x","jam"]. When facing a bet or raise, the buckets
acquire an "R" suffix, for example "2.5xR". All labels refer to total
commitment targets.
•	Snapping – Requests between buckets are snapped to the nearest
bucket. The response sets snapped=true when this occurs and reports the
snapped committed amount.
•	Pre-bot snapshot – Both /api/hand/action and /api/hand/auto return
the state before any bot actions. Auto-played moves are listed in the
bots_applied array.
•	Gating – HAND_AUTO_ENABLED controls exposure of /api/hand/auto and
whether bots auto-advance after human actions. The initial auto-advance on
/api/hand/start always occurs when the session's bot_mode is not
"none".
•	Debugging – When ENGINE_DEBUG_HTTP=true structured debug events are
emitted. See debugging
Status	When	Example body
400	Minimum raise total not met	{ "detail": "min-raise not met: need ≥ 540, got 500" }
409	Action submitted when it isn’t hero’s turn	{ "detail": "not your turn" }
422	Validation error (shape/verb)	Pydantic validation message
501	/api/hand/auto disabled by gating	{ "detail": "auto-advance is disabled" }
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
primarily intended for development, testing and preflop advisor research. It
is not required by the core table flow.
For background on backends and configuration, see
EQUITY.md
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
o	range: a pbots-style range string such as "JJ+" or "random".
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
  "backend": "pokerkit",
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
("pokerkit", "henry", "pbots_calc").
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
•	raw – backend-specific details (e.g. simulations for pbots_calc or
trials for heads-up fallbacks). Intended for debugging and benchmarking.
Errors
Typical error conditions:
Status	Condition	Example body
400	Invalid input (malformed cards, duplicate cards across players/board/dead, mixed hands/ranges).	{ "detail": "duplicate cards across players/board/dead" }
400	Requested mode unsupported by any available backend under the current EQUITY_BACKEND_POLICY.	{ "detail": "no equity backend available for requested mode" }
Backend selection
The backend used is selected according to the EQUITY_BACKEND_POLICY
environment variable:
•	auto – default; tries backends in order (pbots_calc → henry → pokerkit)
and picks the first compatible one.
•	pbots – force pbots_calc (supports ranges + multiway).
•	henry – force the Henry evaluator (hands only).
•	pokerkit – pure-Python fallback (hands only).
See EQUITY.md
for full details.
________________________________________
Preflop coaching API
The preflop advisor provides heads-up preflop guidance using charts plus
optional equity / rule fallbacks. It is exposed via GET /api/coach/preflop
and gated by COACH_ENABLED.
For charts, configuration and decision logic, see
PREFLOP-ADVISOR.md
GET /api/coach/preflop
Query parameters
•	hand_id – required. Identifies the hand for which advice is requested.
Must correspond to a hand started via /api/hand/start.
•	idx – optional integer (default 0). Decision index within the hand.
Internally the advisor uses these to:
•	locate the current hand state,
•	derive the node (e.g. SB open, BB vs SB open),
•	canonicalize the hero hand (e.g. AJo, KTs, JJ).
Successful response (200 OK)
On success the endpoint returns a normalized advice object:
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
Errors
Status	Condition	Example body
400	Bad input (missing hand_id, invalid idx)	{ "detail": "hand_id is required" }
404	No advice available (no matching chart row and fallback unavailable)	{ "detail": "no advice for node" }
501	Coaching disabled or charts unusable (COACH_ENABLED=false, etc.)	{ "detail": "coach disabled" }
Exact error messages may vary but should remain descriptive.
Logging
When LOG_PREFLOP_ADVICE=true, successful advice responses associated with a
(hand_id, idx) pair are stored as snapshots via logger helpers. These
snapshots are surfaced in export JSON under the preflop_advice field for the
corresponding action (see below).
________________________________________
Export endpoints & snapshots
The export endpoints expose per-hand and per-session replays, including (when
enabled) equity and preflop advice snapshots.
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
        "backend": "pokerkit",
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
      }
    }
  ]
}
Notes:
•	equity_snapshot and preflop_advice are optional and appear only when:
o	The relevant logging flags are enabled (LOG_EQUITY_SNAPSHOT,
LOG_PREFLOP_ADVICE), and
o	The corresponding API calls were made with hand_id/idx in scope.
•	When logging is disabled, these fields are simply absent.
The shape of equity_snapshot mirrors the equity API response (possibly
trimmed/redacted). The shape of preflop_advice mirrors the preflop API
response.
GET /api/export/session/{session_id}.json
Returns a JSON document describing a session. At a high level:
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
        "backend": "pokerkit",
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
      }
    }
  ]
}
Notes:
•	equity_snapshot and preflop_advice are optional and appear only when:
o	The relevant logging flags are enabled (LOG_EQUITY_SNAPSHOT,
LOG_PREFLOP_ADVICE), and
o	The corresponding API calls were made with hand_id/idx in scope.
•	When logging is disabled, these fields are simply absent.
The shape of equity_snapshot mirrors the equity API response (possibly
trimmed/redacted). The shape of preflop_advice mirrors the preflop API
response.
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
          "preflop_advice": { /* optional, as above */ }
        }
      ]
    }
  ]
}
Each hand’s actions array follows the same conventions as the single-hand
export: optional equity_snapshot and preflop_advice objects per action.
CSV exports
CSV exports remain intentionally minimal and stable:
•	GET /api/export/hand/{hand_id}.csv
•	GET /api/export/session/{session_id}.csv
These do not include snapshot-specific columns for equity or preflop
advice. They retain the existing schema (action index, actor, action, amount,
street, etc.) and are not affected by snapshot logging.
JSON exports are the source of truth for snapshot data.
Snapshot configuration
The following environment variables control snapshot behaviour (see
CONFIGURATION.md
for details):
•	LOG_EQUITY_SNAPSHOT – when true, successful /api/equity calls with
hand_id and idx are logged and attached as equity_snapshot.
•	LOG_EQUITY_SNAPSHOT_REDACT – when true, logged equity snapshots may
omit or abstract sensitive card/range information in production.
•	LOG_PREFLOP_ADVICE – when true, successful /api/coach/preflop calls
are logged and attached as preflop_advice.
All snapshot fields are optional and backwards-compatible: old exports remain
valid and consumers should treat missing snapshots as “not logged”.

