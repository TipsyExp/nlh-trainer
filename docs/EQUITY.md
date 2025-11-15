# Equity Service

This document explains how the equity subsystem works in the NLH trainer: what
backends are available, how they are selected, how to call the HTTP and CLI
interfaces, and how to reason about performance and determinism.

The equity service is used in three main places:

- Directly via `POST /api/equity` (for dev tools, QA and experiments).
- Internally by the preflop advisor.
- Indirectly via scripts and benchmarks under `backend/scripts/`.

---

## High-level architecture

The core entry point is:

- `backend/services/equity/service.py` – defines `EquityService`, which:
  - Reads configuration from environment variables.
  - Instantiates one or more backend implementations.
  - Chooses a backend for each request based on the policy and the input shape.
  - Normalizes results into a common `EquityResult` structure.

Supporting types live in:

- `backend/services/equity/base.py` – defines:
  - `Card` – simple card representation (e.g. `"Ah"`, `"Td"`).
  - `PlayerSpec` – per-player input (fixed `hand` or `range` string).
  - `EquityResult` – normalized result object.

Backends are pluggable classes under `backend/services/equity/backends/` and can
be enabled or disabled independently depending on optional dependencies.

---

## Backends

The trainer supports three equity backends:

- `pbots_calc` (optional, fastest, supports ranges & multiway)
- `henry` (optional native C evaluator, hands-only HU)
- `pokerkit` (always available pure-Python fallback, hands-only HU)

### pbots_calc backend

File: `backend/services/equity/backends/pbots_calc_backend.py`  
Optional dependency: `pbots_calc` (installed via `backend/requirements-optional.txt`).

Capabilities:

- Accepts both fixed hands and pbots-style range strings.
- Supports heads-up and multiway pots (3+ players).
- Can run in:
  - **Exact mode** – full enumeration (`iters=0`).
  - **Monte Carlo mode** – sampling with a finite number of iterations.

This is the only backend that:

- Accepts `PlayerSpec(range=...)`.
- Supports multiway equity.
- Implements full pbots syntax (groups like `JJ+`, `A5s+`, `random`, etc.).

If `pbots_calc` is not importable, this backend is silently disabled and will be
skipped by the selection policy.

### Henry backend

File: `backend/services/equity/backends/henry_backend.py`  
Optional dependency: compiled HenryRLee evaluator library.

Capabilities:

- Hands-only (no ranges).
- Heads-up only.
- Prefers exact enumeration on small boards; otherwise uses Monte Carlo.
- Requires `HREVAL_LIB_PATH` to point at the native library (`libhreval.so` or
  equivalent). If loading fails, the backend is disabled.

Henry is primarily used as a high-speed exact HU backend for validation and
benchmarks when available.

### PokerKit backend

File: `backend/services/equity/backends/pokerkit_backend.py`  
Dependency: `pokerkit` (pure Python, shipped in `backend/requirements.txt`).

Capabilities:

- Hands-only (no ranges).
- Heads-up only.
- Pure Python, always available.
- Uses exact enumeration on small trees when possible, otherwise Monte Carlo.

PokerKit acts as the “always there” fallback so that `POST /api/equity` remains
usable even when no optional backends are installed.

### Capability summary

| Backend       | Hands | Ranges | Multiway | Exact support | Notes                            |
|--------------|:-----:|:------:|:--------:|:-------------:|----------------------------------|
| `pbots_calc` |  ✔    |   ✔    |    ✔     | Yes / MC      | Optional; uses `pbots_calc`.     |
| `henry`      |  ✔    |   ✖    |    ✖     | Yes / MC      | Optional native C evaluator.     |
| `pokerkit`   |  ✔    |   ✖    |    ✖     | Yes / MC      | Pure-Python fallback, always on. |

“Exact / MC” means the backend can sometimes fully enumerate the remaining
board (`exact`) and otherwise falls back to Monte Carlo sampling (`MC`).

---

## Backend selection policy

`EquityService` chooses a backend for each request based on:

- The configured policy: `EQUITY_BACKEND_POLICY`.
- The capabilities required by the request:
  - Hands vs ranges.
  - Number of players (HU vs multiway).
  - Whether exact enumeration was requested.

Supported policies:

- `auto` – **recommended**. Iterate over available backends in a predefined
  order and use the first one that can satisfy the request. The current order
  is:

  1. `pbots_calc` (if installed)
  2. `henry` (if `HREVAL_LIB_PATH` is configured and the library loads)
  3. `pokerkit` (fallback, always available)

- `pbots` – Force the pbots backend. If it is not available or cannot handle
  the request (e.g. invalid ranges), the call fails with a clear error.
- `henry` – Force the Henry backend (hands-only HU). If not available, the call
  fails.
- `pokerkit` – Force PokerKit (hands-only HU). If a request requires ranges or
  multiway, the service fails with a “no backend available for requested mode”
  style error.

If none of the instantiated backends report that they can handle the request
(e.g. ranges are requested but `pbots_calc` is not installed), the service
raises an error which surfaces through `/api/equity` as a 4xx/5xx response with
a descriptive message.

---

## Environment variables

The equity subsystem is controlled via environment variables. These are read at
process startup by `EquityService` and related modules.

### Core knobs

- `EQUITY_BACKEND_POLICY`

  - Values: `auto`, `pbots`, `henry`, `pokerkit`.
  - Controls which backend(s) may be used.
  - `auto` behaves as “try each backend in order, pick the first compatible
    one”.

- `EQUITY_ITERS`

  - Default number of Monte Carlo samples for non-exact runs.
  - Used when a request does not explicitly specify `iters`.
  - A larger value reduces variance but increases runtime.

- `EQUITY_SEED`

  - Optional RNG seed used for Monte Carlo simulations.
  - When set, identical requests are reproducible (subject to backend
    implementation details).

- `EQUITY_TIMEOUT_MS`

  - Optional soft timeout hint (milliseconds).
  - Backends may use this to truncate long-running Monte Carlo sampling.

### Backend-specific knobs

- `HREVAL_LIB_PATH`

  - Absolute path to the HenryRLee native evaluator library
    (e.g. `/usr/local/lib/libhreval.so`).
  - When set and loadable, the `henry` backend becomes available.
  - When missing or invalid, the Henry backend is disabled; `auto` skips it.

The full list of configuration options (including non-equity settings) is
documented in `CONFIGURATION.md`.

---

## HTTP API integration

The equity service is exposed over HTTP via:

- `POST /api/equity`

The endpoint accepts either fixed hands or ranges and returns a normalized
result shape, regardless of which backend actually computed the equity.

### Request shape (summary)

Body (JSON):

- `players`: list of player specs:

  ```json
  { "hand": ["Ah", "Ad"] }
  { "range": "JJ+" }


Each player must provide exactly one of:
•	hand: two explicit cards, or
•	range: pbots-style range string.
•	board: optional list of board cards, e.g. ["As", "Kd", "2c"].
•	dead: optional list of dead cards to exclude from the deck.
•	iters: optional override of the number of Monte Carlo iterations.
•	exact: bool; when true, request an exact computation where supported.
•	timeout_ms: optional per-request timeout hint.
Query parameters:
•	hand_id: optional string used for logging.
•	idx: optional zero-based integer index for logging.
•	Additional query parameters (like iters or timeout_ms) may be exposed by
the router; see API-CONTRACT.md for the exact schema.
Cards must be unique across players, board and dead. Invalid cards,
collisions or unsupported combinations (e.g. ranges without a ranges-capable
backend) result in 4xx errors.
Response shape (summary)
The normalized equity response contains:
•	ok: boolean status flag.
•	backend: backend used (pokerkit, henry, pbots).
•	mode: "hands" or "ranges".
•	n_players: number of players.
•	board / dead: echoed lists of cards used in the calculation.
•	exact: whether the result is based on a full enumeration.
•	iters: number of MC samples used (may be null or 0 for exact runs).
•	players: list of per-player objects:
o	win: raw win count or samples.
o	tie: raw tie count or samples.
o	equity: normalized equity in [0, 1].
•	raw: backend-specific data, e.g.:
o	simulations for pbots_calc.
o	trials for Monte Carlo fallbacks.
The full, precise contract (including error shapes and HTTP codes) is defined in
API-CONTRACT.md.
________________________________________
CLI & tooling
Equity CLI
The repository ships a small CLI front-end for the equity service:
•	backend/scripts/equity_cli.py
Typical usage:
# Two explicit hands (heads-up)
python -m backend.scripts.equity_cli \
  --hand AhAd \
  --hand KhQh \
  --board AsKd2c \
  --iters 200000

# Ranges vs ranges (requires pbots_calc)
python -m backend.scripts.equity_cli \
  --range "JJ+" \
  --range random \
  --iters 50000

Supported flags (current implementation):
•	--hand H – add a fixed hand (repeat for each player).
•	--range R – add a range (repeat for each player).
•	--board ... – set known board cards.
•	--dead ... – set dead cards, if any.
•	--iters N – set Monte Carlo iterations.
•	--exact – request exact enumeration when supported.
Internally, the CLI builds a PlayerSpec list and calls EquityService
directly; the output matches the normalized equity result (either printed as
JSON or a compact summary, depending on implementation).
Makefile helper
The Makefile includes a convenience target that wraps the CLI:
# Hands variant
make equity HANDS='AhAd,KhQh' BOARD='AsKd2c' EXACT=1

# Ranges variant
make equity RANGES='JJ+,random' ITERS=50000

Environment variables:
•	HANDS: comma-separated list of hands (at least two).
•	RANGES: comma-separated list of ranges (at least two).
•	BOARD: optional board cards.
•	DEAD: optional dead cards.
•	EXACT: 1 to request exact mode.
•	ITERS: Monte Carlo iterations for ranges / non-exact runs.
Benchmark script
For performance and correctness studies, use:
•	backend/scripts/benchmark_equity.py
Basic usage:
# Tiny built-in matrix, CSV to stdout
python -m backend.scripts.benchmark_equity

# Explicit policies and output file
python -m backend.scripts.benchmark_equity \
  --policies auto,pbots \
  --out bench_equity.csv

The script:
•	Defines a small set of scenarios (HU hands, HU ranges, simple 3-way).
•	Iterates over a set of EQUITY_BACKEND_POLICY values.
•	Runs EquityService.calc_equity(...) for each (policy, scenario) pair.
•	Records timing and summary statistics as CSV.
Columns include (see the script for the authoritative list):
•	scenario – scenario name.
•	policy – EQUITY_BACKEND_POLICY used.
•	status / error – whether the run succeeded and any error message.
•	backend / mode – actual backend and mode (hands vs ranges).
•	supports_ranges – backend capability flag (if introspection succeeds).
•	n_players, board_len – scenario dimensions.
•	exact, iters, samples – sampling details.
•	elapsed_ms, evals_per_sec – performance metrics.
•	eq_sum, equities – equity summary per player.
CI uses a small, fast matrix via the make bench-equity target and uploads the
CSV as a non-gating artifact in the pbots-enabled job.
________________________________________
Determinism & accuracy
Monte Carlo equity is inherently noisy; exact enumeration is not. To reason
about determinism and accuracy:
•	Use exact mode when possible
o	exact=true (API) or --exact (CLI) requests enumeration.
o	Backends will honor this when the game tree is small enough; otherwise they
may still fall back to Monte Carlo.
•	Control Monte Carlo variance
o	iters: more iterations ⇒ lower variance but slower.
o	EQUITY_ITERS: global default for omitted iters.
•	Seed the RNG for reproducibility
o	EQUITY_SEED: when set, backends use it to seed their random generators.
o	Repeating the same request with the same seed, backend and iteration count
should produce identical or extremely close results.
•	Use benchmarks and cross-checks
o	Unit tests and the benchmark script compare results across backends on
small boards.
o	For HU hands, you can compare PokerKit vs Henry vs pbots_calc exact
results to validate correctness.
________________________________________
Logging & exports
When enabled, equity calls can be logged and surfaced in export endpoints.
Relevant configuration:
•	LOG_EQUITY_SNAPSHOT (boolean):
o	When true, POST /api/equity calls that include both hand_id and idx
are recorded as equity snapshots.
o	Snapshots are tied to that (hand_id, idx) pair in the logger database.
•	LOG_EQUITY_SNAPSHOT_REDACT (boolean):
o	Hint for callers about whether to store fully detailed or redacted
snapshots. For example, redaction might omit explicit hole cards or range
strings in production environments.
Exports:
•	GET /api/export/hand/{hand_id}.json and
GET /api/export/session/{session_id}.json include, for each action:
o	equity_snapshot: a deserialized snapshot object, when present.
Snapshots are not included in CSV exports; JSON exports are the source of
truth for equity logging.
For more details on logging, see CONFIGURATION.md and the export documentation
in API-CONTRACT.md.
________________________________________
Troubleshooting
Common issues and how to interpret them:
•	“no equity backend available for requested mode”
o	You requested ranges or multiway equities but pbots_calc is not
installed, or you forced a hands-only backend via EQUITY_BACKEND_POLICY.
o	Fix: install pbots_calc (and configure CI to use the optional deps job),
or switch the policy to auto/pbots.
•	Backend unexpected (e.g. pokerkit instead of pbots_calc)
o	pbots_calc may not be importable, or its backend was disabled due to an
internal error.
o	Fix: verify backend/requirements-optional.txt is installed; check logs
for import errors; confirm EQUITY_BACKEND_POLICY is auto or pbots.
•	High variance / inconsistent results between runs
o	Monte Carlo runs with small iters and no fixed EQUITY_SEED.
o	Fix: increase iters, set EQUITY_SEED, or use exact=true when
supported.
•	Long-running or timing-out requests
o	Large trees with high iters or slow backends.
o	Fix: decrease iters, set EQUITY_TIMEOUT_MS, or prefer exact HU backends
where possible (Henry / pbots exact).

