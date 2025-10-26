# QA Checklist

This checklist enumerates the major features and behaviours covered by the test suite for the NLH Trainer as of milestone M1.  Each item links to relevant tests in `backend/tests`.  When adding new functionality or fixing bugs, update this document to reflect new coverage.

| Feature | Test Coverage | Status |
|--------|---------------|-------|
| **Per‑decision logging**: every action records street, actor seat, amounts, bucket, snapped flag, RNG trace, engine and evaluator identifiers | [`test_export_roundtrip.py`](../backend/tests/test_export_roundtrip.py) ensures that exported actions include the correct fields and that exported hands replay deterministically. | ✅ |
| **CSV and JSON export endpoints**: four export routes return correct payloads and stable header ordering | [`test_export_roundtrip.py`](../backend/tests/test_export_roundtrip.py) and [`test_export_csv_headers.py`](../backend/tests/test_export_csv_headers.py) verify CSV header ordering and that all endpoints deliver the expected data structures. | ✅ |
| **Deterministic round‑trip**: exporting a hand/session and replaying with the same seed produces identical canonical state | [`test_export_roundtrip.py`](../backend/tests/test_export_roundtrip.py) replays exported hands and compares the resulting canonical states. | ✅ |
| **Action validation**: illegal actions (wrong bucket, insufficient amount) are rejected with appropriate HTTP status codes | [`test_engine.py`](../backend/tests/test_engine.py) covers invalid action inputs and ensures proper error responses. | ✅ |
| **Autoplay**: script runs hands between bots and collects metrics; coach disabled by default | [`test_autoplay.py`](../backend/tests/test_autoplay.py) executes the autoplay script in different modes and checks output metrics. | ✅ |

## Additional Notes

* Coverage is focused on backend functionality.  Frontend UI and coach features have their own test suites not listed here.
* To run the tests locally, install dependencies from the project root (`python -m pip install -r requirements.txt`) and execute `pytest backend/tests -q`.
