# Preflop Advisor

The preflop advisor is a **chart-driven helper** that returns normalized advice
for common preflop spots. For M2.1 it is deliberately simple:

- Uses **static charts** (JSON files) as the only source of advice.
- Exposes advice through `/api/coach/preflop`.
- Is controlled via environment/config flags.
- Does **not** yet use equity or solvers for fallback decisions.

Later milestones will add:

- Equity-based fallback for chart gaps.
- Multiway / 6-max support.
- More chart formats and tooling.

---

## High-level design

The advisor is implemented in:

- `backend/coach/preflop/models.py` – data models for charts and advice.
- `backend/coach/preflop/charts.py` – chart loading and lookup helpers.
- `backend/coach/preflop/service.py` – `PreflopAdvisorService` entrypoint.
- `backend/api/coach.py` – HTTP API integration.

At a high level:

1. On startup, the advisor loads chart files from `PREFLOP_CHART_PATHS`.
2. Each chart describes metadata (`meta`) and a list of rows (`rows`).
3. When `/api/coach/preflop` is called, the advisor:
   - Builds a minimal **preflop context** for the current spot.
   - Selects a chart that matches the context.
   - Looks up a row `(node, hand_key)` and returns a normalized **advice** object.

If the advisor is disabled or charts are missing, `/api/coach/preflop` returns
`501` to make it obvious that preflop coaching is not available.

---

## Chart JSON format

Charts are plain JSON files with two top-level fields: `meta` and `rows`.

### `meta` (ChartMeta)

Example:

```json
{
  "meta": {
    "format_version": 1,
    "name": "HU 25bb SRP vSB",
    "game_type": "NLH",
    "stack_bb": 25,
    "rake": "0",
    "positions": ["SB", "BB"],
    "notes": "Example heads-up 25bb single-raised pot vs SB chart."
  }
}
Fields:
•	format_version – integer schema version (e.g. 1).
•	name – human-readable chart name.
•	game_type – game type identifier (e.g. "NLH").
•	stack_bb – effective stack in big blinds (e.g. 25).
•	rake – rake descriptor (e.g. "0", "5% capped").
•	positions – ordered list of seat labels (e.g. ["SB","BB"]).
•	notes – optional free-form notes (assumptions, pool, etc.).
rows (ChartRow)
Each row describes a single action recommendation for a canonical hand at a
specific node.
Example:

{
  "rows": [
    {
      "hand": "AJo",
      "node": "sb_open",
      "bucket": "2.5x",
      "strategy_bar": {
        "fold": 0.0,
        "call": 0.2,
        "2.5x": 0.8
      }
    }
  ]
}

Fields:
•	hand – canonical hand key:
o	Pairs: "JJ", "QQ", etc.
o	Suited: "A5s", "KQs", etc.
o	Offsuit: "AJo", "KTo", etc.
•	node – logical spot identifier, e.g.:
o	"sb_open" – SB open-raise spot.
o	"bb_vs_sb_open" – BB vs SB open.
o	Future nodes can follow similar naming.
•	bucket – primary recommended bucket label:
o	Examples: "2.2x", "2.5x", "3.0x", "jam", "fold", "call".
•	strategy_bar – strategy distribution:
o	Map of bucket -> weight where weights are in [0.0, 1.0].
o	The sum should be approximately 1.0 (validation is tolerant to floating
point noise).
Internally, charts are loaded into PreflopChart objects with indexes
on (node, hand_key) for fast lookup.
________________________________________
Configuration
The preflop advisor is controlled by environment/config values exposed in
backend/config.py (names shown here; exact location may vary):
COACH_ENABLED
•	Boolean gate for the coach API.
•	When false, /api/coach/preflop returns 501 and should not be called.
PREFLOP_CHART_PATHS
•	String containing one or more paths to chart JSON files.
•	Paths are separated by : (or ; – both are normalized internally).
•	Example:
export PREFLOP_CHART_PATHS="devdata/charts/hu_example.json"

•	Multiple charts:
export PREFLOP_CHART_PATHS="devdata/charts/hu_example.json:devdata/charts/another_chart.json"

If no charts can be loaded (paths empty or files missing/invalid), the advisor
treats charts as not configured. The coach endpoint should then return 501
with a clear message such as:
{ "detail": "preflop coach charts not configured" }


PREFLOP_EQ_DEFEND_THRESH (placeholder)
•	Float threshold (e.g. 0.48) intended for future equity-based fallback.
•	Not used in the chart-only MVP.
•	Later milestones will use this to decide when to defend vs an assumed range
when a chart entry is missing.
________________________________________
API: /api/coach/preflop
The preflop advisor is exposed through the existing coach router.
Request

GET /api/coach/preflop?hand_id=H1&idx=0


Query parameters:
•	hand_id – engine-specific hand identifier (same as used in other coach APIs).
•	idx – decision index within the hand (0-based). For now, this is used only
to derive a minimal context; it will become more meaningful when wired to
real engine state.
Responses
200 – Chart advice
Example:

{
  "source": "chart",
  "bucket": "2.5x",
  "rationale": "chart:HU 25bb SRP vSB; node=sb_open; hand=AJo; hand_id=H1; idx=0",
  "strategy_bar": {
    "fold": 0.0,
    "call": 0.2,
    "2.5x": 0.8
  }
}


Fields:
•	source – "chart" in the current MVP (future: "rule" / "equity").
•	bucket – primary recommended bucket.
•	rationale – short string explaining why this was recommended
(chart name, node, hand, query identifiers).
•	strategy_bar – bucket → weight map.
404 / 400 – No chart row for this spot
If the advisor cannot find any chart row for the derived context
(e.g. (node, hand_key)), it should return a clear error. Implementations may
use 404 (“no chart for this spot”) or 400 (“unsupported spot”) as long as:
•	The status code is consistent.
•	The detail message clearly describes the situation.
Example:

{ "detail": "no preflop chart entry for node=sb_open, hand=AQo" }

501 – Coach disabled or not configured
Two common 501 cases:
1.	COACH_ENABLED is false:
{ "detail": "preflop coach is disabled" }

2.  COACH_ENABLED is true but no charts are configured or loadable:
{ "detail": "preflop coach charts not configured" }

Current limitations (M2.1)
The chart-only MVP intentionally leaves out a few features that will be added
in later milestones:
•	No equity fallback yet
If a chart row is missing for a spot (hand/node), the advisor does not
run an equity calculation. It simply reports the absence of a chart entry.
•	Limited context
The advisor currently uses a minimal PreflopContext (hand key + node,
optional stack/positions). Future work will derive a richer context directly
from the engine state.
•	Heads-up only
The example charts are HU-only (SB vs BB). Multiway / 6-max charts and logic
will be introduced later alongside the multiway equity and range parsing work.
Despite these limitations, the advisor already provides:
•	A stable chart format.
•	A clear configuration story.
•	A testable and documented /api/coach/preflop endpoint.
This makes it straightforward to plug in more charts and gradually roll in
equity-based fallbacks, additional nodes, and more complex table configurations.

