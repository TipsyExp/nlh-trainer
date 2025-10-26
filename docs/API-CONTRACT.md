# API Contract

This document defines the public API for the NLH Trainer backend.  Each route is described with its HTTP method, URL path, query or body parameters, and example responses captured from live runs.  The examples below are drawn from the `docs/examples` directory to ensure they accurately reflect the current behaviour of the API.  When new endpoints are added or behaviour changes, this contract must be updated accordingly.

## Base URL

All endpoints are served under the `/api` path by the FastAPI application defined in `backend/main.py`.  The server returns JSON responses and uses standard HTTP status codes.

---

## Health Check

* **GET** `/api/health`

  Returns a simple JSON payload indicating that the service is running.  No parameters are required.

  **Response Example**

  ```json
  {"ok": true}
  ```

---

## Session Management

These endpoints reset or create a new game session.  A session groups hands together and configures game parameters like starting stacks and RNG seed.

### Create or Reset Session

* **POST** `/api/session`

  **Query Parameters**
  - `base_seed` (string, optional): When provided, all subsequent RNG values derive from this seed, ensuring repeatability of hands.  If omitted, a random seed is used.

  **Request Body**
  This endpoint does not require a JSON body.  Parameters are passed as query strings.

  **Response Fields**
  - `detail` (string): Human‐readable message indicating that a session was created or reset.
  - `ok` (boolean): Always `true` on success.
  - `session_id` (integer): Unique identifier for the newly created session.

  **Example Response**

  The following example is taken from `docs/examples/session_create.json`:

  ```json
  {"detail": "session created/reset", "ok": true, "session_id": 10}
  ```

---

## Hand Management

A hand represents a single round of poker within a session.  Hands must be explicitly started before any state or actions can be requested.

### Start a Hand

* **POST** `/api/hand/start`

  **Query Parameters**
  - `session_id` (integer, required): The session identifier returned by `POST /api/session`.

  **Response Fields**
  - `hand_id` (string): Unique identifier for the newly created hand.

  **Example Response**

  ```json
  {"hand_id": "H1"}
  ```

### Get Hand State

* **GET** `/api/hand/state`

  **Query Parameters**
  - `hand_id` (string, required): Identifier of the hand to inspect.

  **Response Fields**
  - `actor` (object): Describes the current player whose turn it is to act.  Contains:
    - `seat` (integer): Seat index of the acting player.
    - `to_call` (integer): Number of chips needed to call.
    - `allowed_buckets` (array of strings): Buckets (bet sizes) permitted for this action, e.g. `"2.2x"`, `"3.0xR"`, `"jam"`.  See [BET‑TREES](BET-TREES.md) for definitions.
    - `min_raise` (integer): Minimum raise amount allowed in this spot (in chips).
  - `state` (object): Complete game state snapshot.  See [STATE‑SCHEMA](STATE-SCHEMA.md) for field definitions.

  **Example Response**

  The following excerpt from `docs/examples/hand_state.json` illustrates the structure of the `actor` and `state` fields:

  ```json
  {
    "actor": {
      "seat": 0,
      "to_call": 0,
      "allowed_buckets": ["2.2x", "2.5x", "3.0x", "jam"],
      "min_raise": 20
    },
    "state": {
      "hand_id": "H1",
      "deck_seed": "DOCS-EXAMPLES",
      "street": "preflop",
      "players": [
        {"seat": 0, "type": "human", "alias": "Hero", "stack": 500, "status": "active", "hole_cards": ["Td", "2s"]},
        {"seat": 1, "type": "bot", "alias": "Bot", "stack": 500, "status": "active", "hole_cards": ["?", "?"]}
      ],
      "table": {"seat_count": 2, "sb": 5, "bb": 10, "ante": 0},
      "dealer_seat": 0, "sb_seat": 0, "bb_seat": 1,
      "pot_total": 15
    }
  }
  ```

### Apply an Action

* **POST** `/api/hand/action`

  **Query Parameters**
  - `hand_id` (string, required): Identifier of the hand to act on.

  **Request Body**
  - `action` (string, required): One of `"check"`, `"call"`, `"bet"`, `"raise"`, or `"fold"`.
  - `bucket` (string, optional): For bets or raises, the bucket label chosen (e.g. `"2.5x"` or `"jam"`).  Must be one of the values listed in `allowed_buckets`.

  **Response Fields**
  - `bots_applied` (array): Zero or more actions automatically taken by bots in response to the player’s action.  Each entry has a structure similar to entries in the `actions` list returned by export endpoints (see below).
  - `ok` (boolean): Always `true` when the action is valid.
  - `state` (object): Updated game state after all automatic responses.

  **Example Response**

  From `docs/examples/hand_action.json` after the human checks preflop:

  ```json
  {
    "bots_applied": [
      {"actor_seat": 1, "action": "check", "street": "preflop", "idx": 1},
      {"actor_seat": 1, "action": "check", "street": "flop",    "idx": 2}
    ],
    "ok": true,
    "state": {"street": "flop", "last_action": {"actor_seat": 1, "action": "check", "idx": 2}, ... }
  }
  ```

---

## Export Endpoints

Completed hands and sessions can be exported as JSON or CSV for downstream analysis or replay.  Both formats include a list of actions and the final state snapshot.  In the CSV, each action is one row; the JSON nests actions in an array and includes the full `state` object.

The CSV header order is stable and documented below.  It always begins with `hand_id` and includes `action` and `created_at` towards the end.  The `snapped` field appears as a boolean in JSON but as `0`/`1` in CSV.

### Export Hand (JSON)

* **GET** `/api/export/hand/{hand_id}.json`

  Returns a JSON object with:
  - `actions` (array): Each entry records one decision in the hand.  Fields include `idx`, `street`, `actor_seat`, `action`, `amount`, `bucket`, `to_call_after`, `pot_after`, `time_ms`, `rng_seed`, `snapped`, `meta`, `engine`, `evaluator`, and `created_at` (ISO‑8601 timestamp).
  - `state` (object): Final game state after the hand concludes.  See [STATE‑SCHEMA](STATE-SCHEMA.md).

  **Example**

  See `docs/examples/export_hand.json` for a full example.  Below is a small excerpt showing the first two actions:

  ```json
  {
    "actions": [
      {"idx": 0, "street": "preflop", "actor_seat": 0, "action": "call",  "amount": 10, "bucket": null, "to_call_after": 10, "pot_after": 25, "snapped": false, "engine": "rlcard", "evaluator": null, "created_at": "2025-10-24T12:34:56Z"},
      {"idx": 1, "street": "preflop", "actor_seat": 1, "action": "raise", "amount": 30, "bucket": "3.0x", "to_call_after": 20, "pot_after": 55, "snapped": false, "engine": "rlcard", "evaluator": null, "created_at": "2025-10-24T12:34:57Z"}
      ...
    ],
    "state": {"hand_id": "H1", ... }
  }
  ```

### Export Hand (CSV)

* **GET** `/api/export/hand/{hand_id}.csv`

  Produces a comma‑separated file where each row corresponds to one action.  The header columns are:

  ```csv
  hand_id,idx,street,actor_seat,action,amount,bucket,to_call_after,pot_after,time_ms,rng_seed,snapped,meta,engine,evaluator,created_at
  ```

  An example can be found in `docs/examples/export_hand.csv`.

### Export Session (JSON)

* **GET** `/api/export/session/{session_id}.json`

  Returns an array of exported hands for the given session.  Each entry has the same structure as the hand export described above.

  **Example**

  See `docs/examples/export_session.json`.

### Export Session (CSV)

* **GET** `/api/export/session/{session_id}.csv`

  Concatenates all actions from every hand in the session into a single CSV.  The header is identical to the hand export and appears once at the top of the file.

  **Header Example**

  ```csv
  hand_id,idx,street,actor_seat,action,amount,bucket,to_call_after,pot_after,time_ms,rng_seed,snapped,meta,engine,evaluator,created_at
  ```

---

## Notes

* All timestamps (`created_at`) are ISO‑8601 strings in UTC.  They are truncated to seconds in these examples for readability.
* Enum values such as `street` and action `type` are always returned as lowercase strings (`"preflop"`, `"flop"`, `"turn"`, `"river"`, `"showdown"`, etc.).
* The `snapped` field in JSON is a boolean (`true` or `false`), while in CSV it is represented as `1` for `true` and `0` for `false`.
* Buckets are defined in [BET‑TREES](BET-TREES.md).  Unknown or unsupported buckets will produce validation errors.
