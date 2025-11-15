TASKS — M2
Milestone M2: Equity & Preflop Advisor (Pluggable, Testable, Multi-backend)
Change order: Complete TASK-21 → TASK-23 first (core equity service), then TASK-24 → TASK-27 (multiway, CI/bench), and finally TASK-28 → TASK-30 (docs/UI/dx).
________________________________________
Goals
•	Provide a pluggable equity service with multiple backends (pbots_calc, HenryRLee C evaluator, PokerKit fallback).
•	Bootstrap a preflop advisor that works today (charts + rules) and is easy to swap for a solver later.
•	Cover HU now; enable multiway equity and range inputs to future-proof for 6-max/full ring.
•	Keep CI green with optional deps absent; everything must skip/fallback gracefully.
•	Surface results through API, CLI, UI, logs, and exports so the system is easy to test and compare.
________________________________________
TASK-21 (M2): Equity Backends Integration
Deliver
•	Package: backend/equity/
o	backends/pbots_calc_backend.py (ranges + hands; exact or MC; supports multiway).
o	backends/henry_backend.py (HenryRLee C evaluator via ctypes; hands only; HU exact fast path).
o	backends/pokerkit_backend.py (pure-Python fallback; hands only; exact for tiny boards else MC).
o	service.py – EquityService with policy EQUITY_BACKEND_POLICY=auto|pbots|henry|pokerkit.
o	Capability advertise: supports_ranges, supports_multiway, exact_supported, max_players.
•	Env gates:
o	HREVAL_LIB_PATH=/abs/path/libhreval.so for Henry; if missing → backend disabled.
o	Optional reqs file: backend/requirements-optional.txt (adds pbots_calc).
•	Determinism knobs: EQUITY_ITERS, EQUITY_SEED, EQUITY_TIMEOUT_MS.
•	Result shape (normalized):
{
  "backend": "pbots",
  "method": "exact|mc",
  "players": [
    {"seat": 0, "equity": 0.6521, "wins": 123, "ties": 4},
    {"seat": 1, "equity": 0.3479, "wins": 65,  "ties": 4}
  ],
  "board": ["As","Kd","2c"],
  "exhaustive_boards": false
}
Accept
•	Unit tests cover: hands HU (all backends present/absent), ranges HU (pbots only), backend selection policy.
•	Graceful disable when libs missing; auto chooses first compatible backend.
________________________________________
TASK-22 (M2): Equity API + CLI
Deliver
•	API router: POST /api/equity
o	Accepts either explicit hands or pbots-style ranges; optional board/dead cards.
o	Query args: iters, seed, timeout_ms.
o	Returns normalized result + backend capabilities/flags.
•	CLI: backend/scripts/equity_cli.py
o	Examples:
python -m backend.scripts.equity_cli --hand AhAd --hand KhQh --board AsKd2c --iters 200000
python -m backend.scripts.equity_cli --range "JJ+" --range random --iters 50000
•	Wire router in backend/main.py behind no special gate (falls back to available backend).
Accept
•	Contract tests exercise both hands and range inputs.
•	CLI works locally with/without optional deps (falls back or errors clearly).
________________________________________
TASK-23 (M2): Preflop Advisor Bootstrap
Deliver
•	Package: backend/coach/preflop/
o	Chart loader: load JSON/TOML charts with metadata (format version, stack, rake, positions).
o	Rule policy: HU defaults (open/3b/4b/defend) based on:
	chart hit → use chart bucket
	chart miss → equity threshold fallback via pbots_calc/PokerKit (e.g., defend if eq ≥ X% vs assumed range).
o	Normalized advice response:
{
  "source": "chart|rule|equity",
  "bucket": "2.2x|2.5x|3.0x|jam|fold|call",
  "rationale": "chart:HU_25bb_srp_vsb; hand=AJo; vs range=X",
  "strategy_bar": {"fold":0.15,"call":0.55,"2.5x":0.30}
}
•	Env/config:
o	PREFLOP_CHART_PATHS=/abs/path1:/abs/path2
o	PREFLOP_EQ_DEFEND_THRESH=0.48 (example)
•	API:
o	GET /api/coach/preflop?hand_id=H1&idx=0 → advice JSON (501 if coach globally disabled).
•	Docs: clearly mark charts as assumption-bound (stack, rake, positions).
Accept
•	HU preflop decisions return advice for common nodes (SB open, BB defend, 3b/4b).
•	Advice includes source and rationale; unit tests with small fixture charts.
________________________________________
TASK-24 (M2): Multiway Support & Range Parsing
Deliver
•	Extend range parser to support:
o	pbots syntax, groups (e.g., AQs+, JJ+), weights (optional), and random.
•	Multiway equity via pbots_calc:
o	N players, assigned ranges; compute per-player equities; respect dead cards.
•	API validates seat↔range mapping (order, duplicates, card collisions) and returns precise errors.
Accept
•	Tests: 3-way and 4-way equity vs known pbots samples (golden approximations with tolerance).
•	Error cases produce clear 4xx messages.
________________________________________
TASK-25 (M2): Benchmarks & Correctness Harness
Deliver
•	Script: backend/scripts/benchmark_equity.py
o	Matrix: {backend} × {board density} × {iters} × {players}
o	Outputs CSV with backend, players, exact/MC, iters, boards/sec, rmse_vs_exact.
•	Harness tests:
o	HU hand pairs enumerated on small boards → Henry exact vs pbots exact (where available) vs PokerKit fallback.
o	Define tolerances (e.g., MC RMSE ≤ 0.01 at 200k iters).
•	CI uploads benchmark CSV as artifact (non-gating) for inspection.
Accept
•	Benchmarks run locally; CI executes a short version (≤ 10s) and saves artifacts.
•	Documented tolerances; tests assert within bounds.
________________________________________
TASK-26 (M2): Logging & Exports
Deliver
•	Extend per-action logging:
o	Add equity_snapshot_json (optional) and preflop_advice_json.
•	Export endpoints include these snapshots when present.
•	Config flags:
o	LOG_EQUITY_SNAPSHOT=true|false
o	LOG_PREFLOP_ADVICE=true|false
Accept
•	At least one full hand shows advice/equity snapshots in exports.
•	Backwards-compatible schema; old replays still work.
________________________________________
TASK-27 (M2): CI Matrix & Optional Deps
Deliver
•	CI matrix:
o	pbots: false (default) → tests skip or use PokerKit fallback; no native libs required.
o	pbots: true (opt-in job) → install backend/requirements-optional.txt; enable range/multiway tests.
•	Skips gated on import-availability; clear skip reasons in logs.
•	Packaging check: dist stays free of native libs and chart files unless explicitly allowlisted.
Accept
•	Both matrix jobs green; skips are intentional and visible.
•	Dist size unchanged (or within small slack).
________________________________________
TASK-28 (M2): Documentation
Deliver
•	New: docs/EQUITY.md
o	Backends, capabilities, env, API/CLI examples, determinism tips.
•	New: docs/PREFLOP-ADVISOR.md
o	Chart format, metadata requirements, fallback rules, limitations.
•	Update:
o	docs/API-CONTRACT.md – add /api/equity and /api/coach/preflop sections.
o	docs/QA-CHECKLIST.md – add equity/advice checks.
o	docs/RUNBOOK.md – include CLI examples and troubleshooting.
o	README.md – short blurb + links.
Accept
•	Docs match live endpoints; examples captured via docs script where applicable.
•	CI docs drift check remains green.
________________________________________
TASK-29 (M2): UI Integration (Minimal)
Deliver
•	Table overlay (“Dev Tools” toggle):
o	Equity panel: per-seat equities for current decision (when inputs available).
o	Preflop panel: top bucket + strategy bar + source badge (chart/rule/equity).
•	Handle coach disabled/unsupported states with clear badges.
Accept
•	Overlay renders on local dev; hides itself when inputs unavailable.
•	No hard dependency on optional backends (UI degrades gracefully).
________________________________________
TASK-30 (M2): Developer Experience
Deliver
•	Make targets:
o	make equity-cli, make bench-equity, make coach-preflop
•	Pre-commit hook: run fast subset of equity tests (no native deps).
•	Sample assets:
o	Tiny HU chart fixtures under devdata/charts/ (explicitly excluded from dist).
Accept
•	Fresh clone → optional-deps-free path still passes make check.
•	Optional flow documented and easy to enable.
________________________________________
M2 Acceptance (Overall)
•	✅ With no optional deps (default):
o	All tests pass; equity endpoint works with PokerKit fallback for hands (ranges/multiway skip).
o	Preflop advisor responds via chart/rule path; clearly marks source.
o	Docs & runbook are accurate.
•	✅ With pbots_calc installed and Henry lib configured:
o	/api/equity supports ranges and multiway; HU hands match Henry on exact boards within tolerance.
o	Preflop advisor can use equity thresholds for chart misses.
o	Bench harness artifacts uploaded; UI overlay shows equities/advice.

