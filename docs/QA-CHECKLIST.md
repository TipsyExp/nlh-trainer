# QA Checklist

This checklist tracks the major behaviours currently covered by the test suite for the NLH-Trainer as of **M1**.  
Each item links to the corresponding tests under `backend/tests/`. When adding features or fixing bugs, please update this file so coverage stays accurate.

> **How to run tests**
> ```bash
> python -m pip install -r requirements.txt
> pytest backend/tests -q
> ```

---

## Coverage Matrix

| Feature / Behaviour | Test(s) | Status | Notes |
|---|---|---|---|
| **Health endpoint** responds OK | [`test_health.py`](../backend/tests/test_health.py) | ✅ | Basic liveness check. |
| **Per-decision logging** (street, actor, amounts, bucket, snapped, engine/evaluator, timestamps) | [`test_export_roundtrip.py`](../backend/tests/test_export_roundtrip.py), [`test_exports.py`](../backend/tests/test_exports.py), [`test_actions_logging_guard.py`](../backend/tests/test_actions_logging_guard.py) | ✅ | Verifies fields appear in exports and logging guards behave as expected. |
| **CSV/JSON export endpoints** (hand & session) with stable columns | [`test_exports.py`](../backend/tests/test_exports.py) | ✅ | Confirms header order/shape match current implementation. |
| **Deterministic round-trip** (export → replay with same seed) | [`test_export_roundtrip.py`](../backend/tests/test_export_roundtrip.py) | ✅ | Asserts canonical equivalence under fixed seed. |
| **Action validation** (illegal bucket/amount rejected) | [`test_engine.py`](../backend/tests/test_engine.py), [`test_engine_acceptance.py`](../backend/tests/test_engine_acceptance.py) | ✅ | Covers invalid inputs & acceptance paths. |
| **Bet-size buckets** exposed correctly | [`test_bet_buckets.py`](../backend/tests/test_bet_buckets.py), [`test_bucket_exposure.py`](../backend/tests/test_bucket_exposure.py) | ✅ | Actor’s allowed buckets and exposure. |
| **Bucket snapping** (off-tree amounts snapped to nearest bucket) | [`test_bucket_snapping.py`](../backend/tests/test_bucket_snapping.py) | ✅ | Ensures `snapped` flag and snapped amounts are correct. |
| **Pot progression** / pot exposure is consistent | [`test_pot_exposed.py`](../backend/tests/test_pot_exposed.py) | ✅ | Checks pot math across actions. |
| **State schema** (shape & invariants) | [`test_state_schema.py`](../backend/tests/test_state_schema.py) | ✅ | Sanity checks for fields required by docs. |
| **Range manager** (preflop chart load & sampling) | [`test_range_manager.py`](../backend/tests/test_range_manager.py) | ✅ | Loads charts and samples deterministically (seeded). |
| **Autoplay smoke** (bots play hands; metrics/logging) | [`test_autoplay.py`](../backend/tests/test_autoplay.py) | ✅ | Serial run to avoid DB contention flake. |
| **Engine smoke / integration** | [`test_engine_smoke.py`](../backend/tests/test_engine_smoke.py) | ✅ | End-to-end “it runs” checks. |

---

## CI Guardrails (informational)

These are enforced by CI but are not unit tests per se:

- **Docs Examples Drift**: CI job ensures examples in `docs/examples/` remain consistent with live API outputs.
- **Packaging Hygiene**: CI verifies the slim dist contents/shape (allowlist, forbidden dirs/files).
- **Coach Disabled Guard**: CI exercises the server with coaching disabled to ensure 501s/paths are sane.

---

## Known Gaps / To-Dos

The following are **not fully covered** yet and should get explicit tests as they are implemented or expanded:

- **Complex pot mechanics** beyond HU single-raised (e.g., multiple all-ins/side-pots in multi-way).  
- **Non-reopening raises** and tricky min-raise edge cases in later streets.  
- **6-max** seats and rotation invariants (acceptance + corner cases).  
- **Coach (TexasSolver) integration** once added (node-key hashing, cache hits/misses, adapter parsing, 501 behaviour when unsupported/disabled).  
- **Frontend UI** (React) components—tracked separately from backend tests.

When a gap is closed, add the new test links above and flip the status to ✅.

---
