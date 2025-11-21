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

The trainer supports these equity backends:

- **OMPEval** (native C++ extension; primary; ranges + multiway)
- **Eval7** (pure Python/Cython; fallback; ranges; small multiway)
- **PokerKit** (pure Python; last-resort fallback; hands-only HU)

### OMPEval backend

File: `backend/services/equity/backends/ompeval_backend.py`  
Optional native module: `backend/native/ompeval/` (pybind11 wrapper)

Capabilities:

- Accepts both fixed hands and range strings.
- Supports heads-up and multiway pots (up to **6 players**).
- Exact enumeration when feasible; otherwise Monte Carlo sampling.
- Multithreaded; exposes samples/boards/sec and related stats in `raw`.
- Range syntax: OMPEval uses **Equilab-like** syntax. The service includes a
  small shim to accept common PokerStove-like inputs and normalize them.

When the native module is not available (e.g., not built), this backend is
disabled automatically and skipped by the selection policy.

### Eval7 backend

File: `backend/services/equity/backends/eval7_backend.py`  
Optional dependency: `eval7` (pip-installable)

Capabilities:

- Accepts fixed hands and range strings.
- Heads-up and small multiway (Monte Carlo); slower than OMPEval.
- Used as a portable fallback when OMPEval is unavailable.

### PokerKit backend

File: `backend/services/equity/backends/pokerkit_backend.py` (if present)  
Dependency: `pokerkit` (pure Python, already in base requirements)

Capabilities:

- Hands-only (no ranges).
- Typically used for HU sanity checks and as a last-resort fallback.

### Capability summary

| Backend    | Hands | Ranges | Multiway | Exact support | Notes                               |
|------------|:-----:|:------:|:--------:|:-------------:|-------------------------------------|
| OMPEval    |  ✔    |   ✔    |  ✔ (≤6)  | Yes / MC      | Native C++; fastest & multi-thread. |
| Eval7      |  ✔    |   ✔    |   ✔*     | Yes / MC      | Fallback; slower; pip-installable.  |
| PokerKit   |  ✔    |   ✖    |    ✖     | Yes / MC      | Pure-Python last-resort fallback.   |

\* Small multiway via Monte Carlo; performance varies.

“Exact / MC” means the backend may fully enumerate the remaining board (`exact`)
or fall back to Monte Carlo sampling (`MC`) based on feasibility.

---

## Backend selection policy

`EquityService` chooses a backend for each request based on:

- The configured policy: `EQUITY_BACKEND_POLICY`.
- The capabilities required by the request:
  - Hands vs ranges.
  - Number of players (HU vs multiway).
  - Whether exact enumeration was requested.

Supported policies:

- `auto` – **recommended**. Iterate over available backends in this order and
  use the first that can satisfy the request:

  1. `ompeval` (if the native module is built and importable)
  2. `eval7` (if installed)
  3. `pokerkit` (hands-only fallback)

- `ompeval` – Force the OMPEval backend. If unavailable or unsupported for the
  request shape, the call fails.
- `eval7` – Force Eval7. If unavailable, the call fails.
- `pokerkit` – Force PokerKit (hands-only HU). If the request needs ranges or
  multiway, the service fails with a descriptive error.

If none of the instantiated backends can handle the request (e.g., ranges are
requested but no ranges-capable backend is available), the service raises an
error which surfaces through `/api/equity` as a 4xx/5xx with a readable message.

---

## Environment variables

The equity subsystem is controlled via environment variables. These are read at
process startup by `EquityService` and related modules.

### Core knobs

- `EQUITY_BACKEND_POLICY`

  - Values: `auto`, `ompeval`, `eval7`, `pokerkit`.
  - Controls which backend(s) may be used.

- `EQUITY_ITERS`

  - Default number of Monte Carlo samples for non-exact runs when a request
    omits `iters`.

- `EQUITY_SEED`

  - Optional RNG seed for Monte Carlo. When set, identical requests should be
    reproducible for a given backend and iteration count.

- `EQUITY_TIMEOUT_MS`

  - Optional soft timeout hint (milliseconds) for Monte Carlo runs.

> Backends may expose additional per-request controls (e.g., threads or target
> standard error) through `raw` metadata. See each backend’s notes if/when
> surfaced.

---

## HTTP API integration

The equity service is exposed over HTTP via:

- `POST /api/equity`

The endpoint accepts either fixed hands or ranges and returns a normalized
result shape, regardless of which backend computed the equity.

### Request shape (summary)

Body (JSON):

- `players`: list of player specs (each *must* choose exactly one):

  ```json
  { "hand": ["Ah", "Ad"] }
  { "range": "JJ+" }


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

The trainer supports these equity backends:

- **OMPEval** (native C++ extension; primary; ranges + multiway)
- **Eval7** (pure Python/Cython; fallback; ranges; small multiway)
- **PokerKit** (pure Python; last-resort fallback; hands-only HU)

### OMPEval backend

File: `backend/services/equity/backends/ompeval_backend.py`  
Optional native module: `backend/native/ompeval/` (pybind11 wrapper)

Capabilities:

- Accepts both fixed hands and range strings.
- Supports heads-up and multiway pots (up to **6 players**).
- Exact enumeration when feasible; otherwise Monte Carlo sampling.
- Multithreaded; exposes samples/boards/sec and related stats in `raw`.
- Range syntax: OMPEval uses **Equilab-like** syntax. The service includes a
  small shim to accept common PokerStove-like inputs and normalize them.

When the native module is not available (e.g., not built), this backend is
disabled automatically and skipped by the selection policy.

### Eval7 backend

File: `backend/services/equity/backends/eval7_backend.py`  
Optional dependency: `eval7` (pip-installable)

Capabilities:

- Accepts fixed hands and range strings.
- Heads-up and small multiway (Monte Carlo); slower than OMPEval.
- Used as a portable fallback when OMPEval is unavailable.

### PokerKit backend

File: `backend/services/equity/backends/pokerkit_backend.py` (if present)  
Dependency: `pokerkit` (pure Python, already in base requirements)

Capabilities:

- Hands-only (no ranges).
- Typically used for HU sanity checks and as a last-resort fallback.

### Capability summary

| Backend    | Hands | Ranges | Multiway | Exact support | Notes                               |
|------------|:-----:|:------:|:--------:|:-------------:|-------------------------------------|
| OMPEval    |  ✔    |   ✔    |  ✔ (≤6)  | Yes / MC      | Native C++; fastest & multi-thread. |
| Eval7      |  ✔    |   ✔    |   ✔*     | Yes / MC      | Fallback; slower; pip-installable.  |
| PokerKit   |  ✔    |   ✖    |    ✖     | Yes / MC      | Pure-Python last-resort fallback.   |

\* Small multiway via Monte Carlo; performance varies.

“Exact / MC” means the backend may fully enumerate the remaining board (`exact`)
or fall back to Monte Carlo sampling (`MC`) based on feasibility.

---

## Backend selection policy

`EquityService` chooses a backend for each request based on:

- The configured policy: `EQUITY_BACKEND_POLICY`.
- The capabilities required by the request:
  - Hands vs ranges.
  - Number of players (HU vs multiway).
  - Whether exact enumeration was requested.

Supported policies:

- `auto` – **recommended**. Iterate over available backends in this order and
  use the first that can satisfy the request:

  1. `ompeval` (if the native module is built and importable)
  2. `eval7` (if installed)
  3. `pokerkit` (hands-only fallback)

- `ompeval` – Force the OMPEval backend. If unavailable or unsupported for the
  request shape, the call fails.
- `eval7` – Force Eval7. If unavailable, the call fails.
- `pokerkit` – Force PokerKit (hands-only HU). If the request needs ranges or
  multiway, the service fails with a descriptive error.

If none of the instantiated backends can handle the request (e.g., ranges are
requested but no ranges-capable backend is available), the service raises an
error which surfaces through `/api/equity` as a 4xx/5xx with a readable message.

---

## Environment variables

The equity subsystem is controlled via environment variables. These are read at
process startup by `EquityService` and related modules.

### Core knobs

- `EQUITY_BACKEND_POLICY`

  - Values: `auto`, `ompeval`, `eval7`, `pokerkit`.
  - Controls which backend(s) may be used.

- `EQUITY_ITERS`

  - Default number of Monte Carlo samples for non-exact runs when a request
    omits `iters`.

- `EQUITY_SEED`

  - Optional RNG seed for Monte Carlo. When set, identical requests should be
    reproducible for a given backend and iteration count.

- `EQUITY_TIMEOUT_MS`

  - Optional soft timeout hint (milliseconds) for Monte Carlo runs.

> Backends may expose additional per-request controls (e.g., threads or target
> standard error) through `raw` metadata. See each backend’s notes if/when
> surfaced.

---

## HTTP API integration

The equity service is exposed over HTTP via:

- `POST /api/equity`

The endpoint accepts either fixed hands or ranges and returns a normalized
result shape, regardless of which backend computed the equity.

### Request shape (summary)

Body (JSON):

- `players`: list of player specs (each *must* choose exactly one):

  ```json
  { "hand": ["Ah", "Ad"] }
  { "range": "JJ+" }
# Two explicit hands (heads-up)
python -m backend.scripts.equity_cli \
  --hand AhAd \
  --hand KhQh \
  --board AsKd2c \
  --iters 200000

# Ranges vs ranges (requires a ranges-capable backend: OMPEval or Eval7)
python -m backend.scripts.equity_cli \
  --range "JJ+" \
  --range random \
  --iters 50000

Flags (current implementation):
•	--hand H – add a fixed hand (repeat per player).
•	--range R – add a range (repeat per player).
•	--board ... – set known board cards.
•	--dead ... – set dead cards, if any.
•	--iters N – set Monte Carlo iterations.
•	--exact – request exact enumeration when supported.
Makefile helper
The Makefile includes a convenience target that wraps the CLI:
# Hands variant
make equity HANDS='AhAd,KhQh' BOARD='AsKd2c' EXACT=1

# Ranges variant (needs OMPEval/Eval7)
make equity RANGES='JJ+,random' ITERS=50000

Environment variables:
•	HANDS, RANGES, BOARD, DEAD, EXACT, ITERS
(see target comments for details)
Benchmark script
For performance and correctness studies, use:
•	backend/scripts/benchmark_equity.py
Basic usage:
# Tiny built-in matrix, CSV to stdout
python -m backend.scripts.benchmark_equity

# Explicit policies and output file
python -m backend.scripts.benchmark_equity \
  --policies auto,ompeval,eval7 \
  --out bench_equity.csv

The script:
•	Defines a small set of scenarios (HU hands, HU ranges, simple multiway).
•	Iterates over provided EQUITY_BACKEND_POLICY values.
•	Runs EquityService.calc_equity(...) and records timing and summary stats.
Columns include (authoritative list in the script):
•	scenario, policy, status, error
•	backend, mode, supports_ranges
•	n_players, board_len
•	exact, iters, samples
•	elapsed_ms, evals_per_sec
•	eq_sum, equities
•	(optionally) error vs exact for tiny HU comparisons
CI uses small, fast defaults via make bench-equity and uploads the CSV as a
non-gating artifact in the ranges-capable job.
________________________________________
Determinism & accuracy
Monte Carlo equity is inherently noisy; exact enumeration is not. To reason
about determinism and accuracy:
•	Use exact mode when possible
o	exact=true (API) / --exact (CLI) requests enumeration.
o	Backends will honor this when feasible; otherwise Monte Carlo is used.
•	Control Monte Carlo variance
o	iters: more iterations ⇒ lower variance but slower.
o	EQUITY_ITERS: global default when iters is omitted.
•	Seed the RNG for reproducibility
o	EQUITY_SEED: when set, MC runs should be repeatable for a given backend.
•	Use benchmarks and cross-checks
o	Unit tests and the benchmark script compare results across backends on
small boards and simple scenarios.
________________________________________
Logging & exports
When enabled, equity calls can be logged and surfaced in export endpoints.
Relevant configuration:
•	LOG_EQUITY_SNAPSHOT (boolean):
o	When true, POST /api/equity calls that include both hand_id and idx
are recorded as equity snapshots under that (hand_id, idx).
•	LOG_EQUITY_SNAPSHOT_REDACT (boolean):
o	Hint for callers about whether to store fully detailed or redacted
snapshots (e.g., omit explicit hole cards / ranges in production).
Exports:
•	GET /api/export/hand/{hand_id}.json and
GET /api/export/session/{session_id}.json include, for each action:
o	equity_snapshot: a deserialized snapshot object, when present.
Snapshots are not included in CSV exports; JSON exports are the source of
truth for equity logging.
For more details on logging, see CONFIGURATION.md and the export section in
API-CONTRACT.md.
________________________________________
Troubleshooting
Common issues and how to interpret them:
•	“no equity backend available for requested mode”
o	You requested ranges or multiway equities but neither OMPEval (native) nor
Eval7 is available, or you forced pokerkit.
o	Fix: build/enable the OMPEval module (recommended), or install eval7;
otherwise switch the policy to auto or adjust the request.
•	Backend unexpected (e.g., fell back to pokerkit)
o	The OMPEval native module wasn’t importable, or Eval7 isn’t installed.
o	Fix: verify the native build on Linux/WSL/macOS (Windows users may prefer
WSL), or pip install eval7.
•	High variance / inconsistent results
o	Monte Carlo runs with small iters and no fixed EQUITY_SEED.
o	Fix: increase iters, set EQUITY_SEED, or request exact=true where
feasible.
•	Long-running or timing-out requests
o	Large trees with high iters or slower fallback backends.
o	Fix: reduce iters, set EQUITY_TIMEOUT_MS, prefer OMPEval, and leverage
exact mode for small boards.
•	Player limit
o	OMPEval supports up to 6 players. For larger tables, reduce the player
count or fall back to simpler analyses.

## M3 notes: EquityService usage in the postflop coach

In addition to the public `/api/equity` endpoint, `EquityService` is also used
**internally** by the coaching stack:

- **Postflop coach (HU, flop/turn/river)**
  - The coach builds a `DecisionContext` for a given `(hand_id, idx)` and constructs:
    - Hero as a **fixed hand** (from `DecisionContext.hero_hole_cards`).
    - Villain as a **range string** (using presets in `backend/coach/postflop/ranges.py`).
  - It then calls `EquityService.calc_equity(...)` (or a small helper) to obtain:
    - `backend` (e.g. `"ompeval"`),
    - `mode` (`"hands"` or `"ranges"`),
    - per-player equities, which are mapped into the `AdviceV1.equity` block.

- **Configuration knobs**
  - The same configuration flags that affect `/api/equity` also apply to the coach’s internal equity calls, for example:
    - `EQUITY_BACKEND_POLICY` – backend selection (`auto`, `ompeval`, `eval7`, `pokerkit`).
    - `EQUITY_ITERS` – default Monte Carlo iteration count when the coach does not specify one.
    - `EQUITY_TIMEOUT_MS` – soft timeout hint; exceeded budgets should lead to `status="timeout"` or `status="unsupported"` in `AdviceV1` rather than crashing.
  - Additional postflop-specific flags (e.g. `POSTFLOP_COACH_ENABLED`, per-street iteration budgets) may further constrain whether the coach uses equity or falls back to simple rules.

This means that changing equity-related configuration can impact both:

1. Direct `/api/equity` responses, and  
2. The quality and availability of postflop advice returned by `/api/coach/advice` (for spots where the coach relies on hero-vs-range equity).
