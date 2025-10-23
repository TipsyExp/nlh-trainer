# QA Checklist

This checklist enumerates the key behaviours and test cases that must
be verified to ensure the NLH Trainer meets its specification.  Each
entry references a corresponding test in the CI suite or manual
procedure.

- **Session creation** – `POST /api/session` should accept valid
  parameters (seats, blinds, stacks, human seat, base_seed) and
  initialise the engine.  Invalid inputs (mismatched `stacks` length,
  out‑of‑range `human_seat`) return HTTP 400.
  - *Test:* `tests/test_session.py::test_create_session_valid` and
    `test_create_session_invalid`.
- **Hand lifecycle** – `POST /api/hand/start` returns a new `hand_id`
  and auto‑advances bots to the first human decision.  `GET
  /api/hand/state` returns the public snapshot and actor info.  `POST
  /api/hand/action` applies a human decision and logs it.
  - *Test:* `tests/test_hand.py::test_hand_flow`.
- **Per‑action logging** – Every decision (human or bot) inserts a
  row into the `actions` table with correct `idx`, `street`,
  `actor_seat`, `type`, `amount`, `bucket`, `snapped` and metadata
  fields.  Actions are in ascending order by `idx`.
  - *Test:* `tests/test_logging.py::test_action_logging`.
- **Export endpoints** – Completed hands and sessions can be
  exported as JSON (`/api/export/hand/{hand_id}.json`,
  `/api/export/session/{session_id}.json`) and CSV (`.csv` suffix).
  Unknown or incomplete hands return HTTP 404.  CSV exports include a
  header row followed by one row per action with fields in the order
  documented in [API‑CONTRACT.md](API-CONTRACT.md).
  - *Test:* `tests/test_export.py::test_hand_json_export`,
    `test_hand_csv_export`, `test_session_json_export`,
    `test_session_csv_export`.
- **Round‑trip determinism** – Exported hand histories can be
  deserialised using `import_json` and replayed through the engine to
  reproduce the final state (deck order and action sequence).  This
  ensures that the logged RNG seeds and actions capture the full
  hand.
  - *Test:* `tests/test_determinism.py::test_round_trip`.
- **Documentation accuracy** – Examples in
  `docs/API-CONTRACT.md`, `docs/BET-TREES.md`, `docs/BOT-POLICY.md`,
  and `docs/STATE-SCHEMA.md` must match actual API responses and
  model definitions.  The docs are linted and validated by
  `tests/test_docs.py::test_api_contract_examples`.
- **Packaging hygiene** – `make dist` must produce a slim
  distributable that excludes `third_party/`, `.venv/`, caches and
  other artefacts.  Unused dependencies are removed from
  `requirements.txt`.
  - *Test:* `tests/test_packaging.py::test_dist_contents`.

This checklist should be updated as new features (coach API, solver
cache, review UI, etc.) are implemented.  Each new endpoint or
configuration option must be accompanied by corresponding tests and
documentation.
