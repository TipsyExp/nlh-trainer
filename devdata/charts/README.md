# Dev Preflop Charts

This directory contains **development-only** preflop chart fixtures used for
testing and local experiments. These charts are **not** intended for
production or distribution; they should be excluded from any slim/dist builds.

---

## Files

### `hu_example.json`

A minimal example chart for a **heads-up 25bb single-raised pot vs SB** spot.

Structure:

```jsonc
{
  "meta": {
    "format_version": 1,
    "name": "HU 25bb SRP vSB",
    "game_type": "NLH",
    "stack_bb": 25,
    "rake": "0",
    "positions": ["SB", "BB"],
    "notes": "Example heads-up 25bb single-raised pot vs SB chart for dev/testing."
  },
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

•	meta describes global assumptions (stack, rake, positions, etc.).
•	Each entry in rows describes:
o	hand: canonical hand key (AJo, A5s, QQ, etc.).
o	node: a logical spot identifier (here, "sb_open").
o	bucket: primary recommended action bucket ("2.5x", "jam", "fold", etc.).
o	strategy_bar: a bucket → probability map that should roughly sum to 1.0.
________________________________________
Using these charts in development
The preflop advisor reads chart paths from the PREFLOP_CHART_PATHS environment
variable. You can point it at this file in local dev, for example:


export PREFLOP_CHART_PATHS="devdata/charts/hu_example.json"
export COACH_ENABLED=true
Then, with the backend running, the coach endpoint can use these charts to
produce chart-based advice (via /api/coach/preflop once wired).
Multiple chart files can be provided by separating paths with : (or ; on
Windows); the advisor will load all of them:
export PREFLOP_CHART_PATHS="devdata/charts/hu_example.json:devdata/charts/another_chart.json"
Notes
•	This directory is dev-only and should remain excluded from slim / production
distributions unless explicitly allowlisted.
•	The format is intentionally simple so new charts can be generated or edited by
hand while iterating on the preflop advisor.

