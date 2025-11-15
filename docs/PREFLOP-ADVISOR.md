
# Preflop Advisor

The preflop advisor provides normalized strategy advice for common heads-up
preflop spots. It is designed to be:

- **Chart-first** – use static range charts when available.
- **Rule / equity-aware** – fall back to simple rules and, when configured,
  equity thresholds.
- **Pluggable** – charts can be swapped without code changes, and the
  equity backend is shared with the main equity service.

This document describes the chart format, configuration flags, decision logic,
API behaviour and current limitations.

---

## High-level architecture

The advisor lives under:

- `backend/coach/preflop/`

Key pieces (names may vary slightly depending on implementation):

- **Chart loader**
  - Loads JSON/TOML chart files.
  - Validates basic metadata (format version, stack, positions).
  - Indexes rows by `(node, hand_key)` for fast lookup.

- **Advisor core**
  - Accepts a hand context (via `hand_id`/`idx`).
  - Resolves the relevant node (e.g. `sb_open`, `bb_vs_sb_open`).
  - Canonicalizes the hero hand into a chart key (e.g. `AJo`, `KTs`, `JJ`).
  - Applies **chart → equity → rule** logic to return advice.

- **Equity integration**
  - Uses `EquityService` for equity fallback where enabled and supported.
  - Only needed when charts are missing for a particular node/hand.

The advisor is exposed over HTTP via:

- `GET /api/coach/preflop`

and is gated by `COACH_ENABLED`.

---

## Chart format

Charts define preflop advice for a given configuration (stack, rake, positions)
and a specific node (e.g. SB open, BB defend). Files are JSON or TOML with two
top-level keys:

- `meta`
- `rows`

### `meta` section

The `meta` block describes global assumptions for the chart:

| Field           | Type    | Description                                           |
|----------------|---------|-------------------------------------------------------|
| `format_version` | int   | Schema version of the chart file.                     |
| `name`         | string  | Optional human-readable chart name.                   |
| `stack_bb`     | number  | Effective stack depth in big blinds (e.g. `25`).      |
| `rake`         | string  | Rake description (e.g. `"0"`, `"5% capped"`).         |
| `positions`    | array   | Ordered positions, typically `["SB","BB"]` for HU.    |
| `notes`        | string  | Optional free-form notes about the population, etc.   |

Example (JSON):

```json
{
  "meta": {
    "format_version": 1,
    "name": "HU_25bb_srp_vsb",
    "stack_bb": 25,
    "rake": "0",
    "positions": ["SB", "BB"],
    "notes": "Example HU chart for SB open / BB defend at 25bb."
  },
  "rows": [ /* ... */ ]
}

rows section
Each row describes advice for a canonical hand at a specific preflop node.
Field	Type	Description
hand	string	Canonical hand key, e.g. "JJ", "A5s", "AJo".
node	string	Logical node identifier, e.g. "sb_open", "bb_vs_sb_open".
bucket	string	Primary recommended action/bucket, e.g. "fold", "call", "2.5x".
strategy_bar	object	Map of bucket labels → weights (floats summing to ≈ 1.0).
Example row:
{
  "hand": "AJo",
  "node": "sb_open",
  "bucket": "2.5x",
  "strategy_bar": {
    "fold": 0.0,
    "2.2x": 0.2,
    "2.5x": 0.5,
    "3.0x": 0.3
  }
}
Internally, the advisor indexes rows by (node, hand) so lookups are O(1) for
chart hits.
________________________________________
Configuration flags
The preflop advisor is configured via environment variables. These are typically
parsed in backend/config.py and imported by the advisor.
Core coach flags
•	COACH_ENABLED
o	Gate for all coaching endpoints.
o	When false, GET /api/coach/preflop responds with HTTP 501
(“not implemented / disabled”).
•	PREFLOP_CHART_PATHS
o	Colon- or semicolon-separated list of chart files to load.
o	Example: devdata/charts/hu_example.json.
o	At least one file must be present for chart-based advice.
o	Invalid or missing paths cause the advisor to fall back (501/404)
depending on configuration.
Equity fallback flags
•	PREFLOP_EQ_DEFEND_THRESH
o	Float threshold in [0, 1] (e.g. 0.48).
o	Used when the advisor runs an equity calculation for a “defend vs fold”
decision.
o	If hero equity ≥ threshold → defend (call/jam).
o	If hero equity < threshold → fold.
•	PREFLOP_FALLBACK_REQUIRED
o	Controls behaviour when charts and equity fallback cannot produce a
recommendation.
o	Typical values (exact strings may vary in implementation):
	e.g. "raise" or "conservative" as high-level modes.
o	Effect:
	In a conservative mode, the advisor tends to return a safe default (often
fold) and mark source="rule".
	In a stricter mode, missing coverage might lead to conservative folds or
explicit errors.
The full behaviour is determined by the advisor implementation; this document
captures the intent: charts first, equity second, rule fallback last.
________________________________________
Decision logic
When GET /api/coach/preflop is called, the advisor follows roughly this flow:
1.	Check gating
o	If COACH_ENABLED=false, return HTTP 501.
2.	Resolve context from hand
o	Locate the hand by hand_id.
o	Use idx to find the relevant decision point.
o	Determine:
	Hero position (SB/BB).
	Board street (must be preflop).
	Node identifier (e.g. "sb_open", "bb_vs_sb_open").
	Hero hole cards, canonicalized into a key ("JJ", "A5s", "AJo", …).
3.	Chart lookup
o	Search loaded charts for a row matching (node, hand_key).
o	If found:
	Return advice with:
	source = "chart"
	bucket = row.bucket
	strategy_bar = row.strategy_bar
	rationale referencing chart metadata and node (e.g. chart name, stack).
4.	Equity fallback (optional)
o	If no chart row is found and equity fallback is enabled and supported:
	Construct assumed villain range for the node (implementation-specific).
	Call EquityService to compute hero equity vs that range.
	If equity ≥ PREFLOP_EQ_DEFEND_THRESH:
	Suggest a defend bucket (e.g. "call" or "2.5x").
	Set source = "equity".
	Include equity and threshold details in rationale.
	Otherwise:
	Suggest "fold" (or similarly conservative action).
	Set source = "equity".
o	Equity fallback requires:
	A ranges-capable backend (pbots_calc) and compatible EQUITY_BACKEND_POLICY.
	A valid villain range model for the node.
5.	Rule fallback
o	If neither chart nor equity fallback can produce advice:
	Apply a simple rule policy controlled by PREFLOP_FALLBACK_REQUIRED.
	Examples:
	Return "fold" with source="rule" for uncharted / unsupported spots.
	Return a benign default (e.g. "fold" or "call") depending on node.
	Include a rationale explaining the rule (e.g. “conservative default
because no chart and no equity fallback were available”).
If all of the above fail (e.g. misconfigured charts and no fallback allowed),
the advisor returns an error status (typically 404 or 501) with a descriptive
message.
________________________________________
API behaviour
Endpoint
•	GET /api/coach/preflop
Query parameters
•	hand_id (required)
o	Identifies the current hand.
o	Must refer to a hand started via /api/hand/start.
o	Used to locate hero position, hole cards, and node.
•	idx (optional, default 0)
o	Zero-based decision index within the hand.
o	Allows multiple decisions (e.g. different preflop actions) to be targeted.
Example request:
GET /api/coach/preflop?hand_id=H1&idx=0
Successful response (200 OK)
On success, the payload is an advice object:
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
Fields:
•	source
o	"chart" – advice taken directly from a chart row.
o	"equity" – advice derived from an equity calculation vs assumed range.
o	"rule" – advice from a simple rule fallback when charts/equity are not
available or permitted.
•	bucket
o	Primary recommended action bucket (e.g. "fold", "call", "2.2x",
"2.5x", "3.0x", "jam").
o	Bucket naming is consistent with bet sizing labels used by the engine.
•	rationale
o	Short human-readable string explaining the source:
	Chart name, node, and hand for chart advice.
	Equity percentage, threshold and villain range description for equity
fallback.
	Rule description for rule-based fallbacks.
•	strategy_bar
o	Map of bucket labels → weights (floats).
o	Typically sums to 1.0 (within rounding error).
o	For rule or equity fallbacks this may be a degenerate distribution (e.g.
a single bucket with weight 1.0) unless the implementation models mixes.
Error responses
Typical status codes:
Status	When	Example
200	Advice successfully computed	Advice object as above.
400	Bad input (hand_id missing, invalid idx)	{"detail":"..."}
404	No advice possible for this spot (chart+fallback unavailable/disabled)	{"detail":"no advice for node/hand"}
501	Coaching globally disabled or charts unusable	{"detail":"coach disabled"} or similar
Exact wording is implementation-defined; errors should be descriptive and
stable enough for QA.
________________________________________
Logging & exports
When snapshot logging is enabled, preflop advice is stored and surfaced via
export endpoints.
Configuration
•	LOG_PREFLOP_ADVICE (boolean)
o	When true, successful GET /api/coach/preflop responses that are
associated with a (hand_id, idx) pair are recorded in the logger DB.
o	Each snapshot is tied to that (hand_id, idx) and later exposed in
exports.
Internally, logger helpers (e.g. log_preflop_advice) write a JSON payload
for each advice call, including source, bucket, strategy_bar and
rationale.
Export format
•	GET /api/export/hand/{hand_id}.json
o	Returns a JSON object with:
	hand_id
	state – serialized hand state.
	actions – list of actions.
o	For each action, when a preflop advice snapshot exists:
{
  "idx": 0,
  "street": "pre",
  "actor_seat": 0,
  "action": "bet",
  "amount": 250,
  "...": "...",
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
•	GET /api/export/session/{session_id}.json
o	Returns analogous per-hand data; each hand’s actions array may include
preflop_advice fields where logging is enabled.
CSV exports (/api/export/hand/{hand_id}.csv and session CSV) intentionally
do not include extra columns for snapshots; JSON exports are the source of
truth for advice logging.
________________________________________
Assumptions & limitations
The current advisor is intentionally modest and focused on HU preflop:
•	Heads-up only
o	Charts are built for heads-up SB vs BB.
o	Multiway and 6-max / full ring support are out of scope for this milestone.
•	Assumption-bound charts
o	Each chart is tied to specific assumptions: stack size, rake, positions.
o	Advice is only guaranteed to be meaningful when requests match these
assumptions (e.g. same effective stack, HU positions).
o	Mismatched configurations may lead to missing rows (404) or rule fallbacks.
•	Not a solver
o	The advisor is not running a full GTO solver.
o	Charts are static references; equity fallback uses simple thresholds; rules
are conservative defaults.
o	Treat advice as reasonable guidance, not as ground truth strategy.
•	Equity fallback requires ranges
o	Equity fallback is only available when:
	The equity backend supports ranges (pbots_calc installed).
	EQUITY_BACKEND_POLICY allows a ranges-capable backend (auto or
pbots).
o	In hands-only configurations (e.g. EQUITY_BACKEND_POLICY=pokerkit), the
advisor will skip equity fallback and rely on charts or rules.
•	Logging and privacy
o	When LOG_PREFLOP_ADVICE=true, advice snapshots are persisted and surfaced
in exports.
o	Downstream consumers must handle these snapshots carefully (e.g. do not
leak opponent ranges or private notes if that becomes part of the payload).
________________________________________
Operational checklist
When bringing the preflop advisor up in a new environment:
1.	Configure charts
o	Place chart files (e.g. hu_example.json) under a suitable directory.
o	Set PREFLOP_CHART_PATHS to include those files.
2.	Enable coach (if desired)
o	Set COACH_ENABLED=true for environments where advice is needed.
o	Keep it false in environments that should not expose coaching (e.g. some
production deployments).
3.	Configure equity fallback (optional)
o	Install optional equity deps (pbots_calc) if you want equity fallback.
o	Ensure EQUITY_BACKEND_POLICY is compatible (auto/pbots).
o	Set PREFLOP_EQ_DEFEND_THRESH to a sensible value (e.g. 0.48).
4.	Enable logging (optional)
o	Set LOG_PREFLOP_ADVICE=true to attach advice snapshots to exports.
5.	Smoke test
o	Start a HU session, play a simple preflop node and call:
	GET /api/coach/preflop?hand_id=H1&idx=0
o	Verify:
	200 with source="chart" for chart-covered hands.
	200 with source="equity" for chart gaps when equity fallback is
available.
	Appropriate 404/501 codes when coach is disabled or misconfigured.

