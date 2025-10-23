# State Schema

The NLH Trainer serialises complete hand histories into JSON objects
for logging, export and replay.  This document describes the schema
of the `GameState` and `ActionRecord` structures.  The schema is
implemented using Pydantic models in `backend/models/state.py`.

## Enumerations

- **SeatType** – describes the type of occupant at a seat:
  - `human` – controlled by the trainee.
  - `bot` – controlled by the built‑in bot.
- **PlayerStatus** – indicates the current status of a player:
  - `active` – still in the hand.
  - `folded` – has folded.
  - `all_in` – has committed all chips.
- **Street** – enumerates the phases of a hand:
  - `preflop`, `flop`, `turn`, `river`, `showdown`, `complete`.
- **ActionType** – enumerates supported actions:
  - `check`, `call`, `bet`, `raise`, `fold`, `post_blind`, `all_in`, `deal`.
  - In the Pydantic model the `raise` action is named `raise_` to avoid
    clashing with the Python keyword, but the JSON representation uses
    `"raise"`.

## GameState

A `GameState` captures the final public state of a hand.

| Field          | Type                               | Description                                                 |
|----------------|------------------------------------|-------------------------------------------------------------|
| `hand_id`      | `string`                           | Unique identifier (e.g. `H1`, `H2`, …).                     |
| `deck_seed`    | `string?`                          | Seed used for deterministic shuffling (may be `null`).      |
| `table`        | [`TableState`](#tablestate)        | Static table configuration.                                 |
| `dealer_seat`  | `int`                              | Seat index of the dealer button for the hand.               |
| `sb_seat`      | `int`                              | Seat index posting the small blind.                         |
| `bb_seat`      | `int`                              | Seat index posting the big blind.                           |
| `street`       | `Street`                           | Final street reached (currently always `preflop` or `flop`).|
| `players`      | `[PlayerState]`                    | List of players and their metadata.                         |
| `action_history` | `[ActionRecord]`                 | Sequence of actions performed during the hand.              |

### TableState

| Field       | Type | Description                    |
|-------------|------|--------------------------------|
| `seat_count`| `int`| Number of seats at the table.  |
| `sb`        | `int`| Small blind amount.            |
| `bb`        | `int`| Big blind amount.              |
| `ante`      | `int`| Ante amount (unused in M0).     |

### PlayerState

| Field     | Type       | Description                                   |
|-----------|------------|-----------------------------------------------|
| `seat`    | `int`      | Seat index of the player.                      |
| `type`    | `SeatType` | Whether the player is `human` or `bot`.        |
| `alias`   | `string`   | Display name (e.g. “Hero”, “Bot1”).            |
| `stack`   | `int`      | Stack size at the start of the hand.           |
| `status`  | `PlayerStatus` | Current status (`active`, `folded`, `all_in`). |

## ActionRecord

Each entry in `action_history` is an `ActionRecord` describing a single
decision in the hand.

| Field          | Type            | Description                                                      |
|----------------|-----------------|------------------------------------------------------------------|
| `idx`          | `int`           | Zero‑based index of the action within the hand.                  |
| `street`       | `Street`        | Street on which the action occurred.                            |
| `actor_seat`   | `int`           | Seat index of the acting player.                                |
| `type`         | `ActionType`    | Type of action (e.g. `check`, `call`, `raise`).                 |
| `amount`       | `int?`          | Total commitment after the action (for bet/raise).               |
| `bucket`       | `string?`       | Label of the bet bucket used (e.g. `"2.5x"`, `"2.5xR"`).       |
| `to_call_after`| `int?`          | Amount to call for the next player after this action.            |
| `pot_after`    | `int?`          | Total pot size after the action.                                 |
| `time_ms`      | `int?`          | Elapsed time for the decision (unused in M0).                    |
| `rng_seed`     | `string?`       | RNG seed associated with the action for determinism.             |
| `snapped`      | `bool?`         | Whether the amount was snapped to a bucket.                      |
| `meta`         | `object?`       | Additional metadata (e.g. `{"allowed_buckets": ["call", "2.2x"]}`). |

## Serialisation Helpers

The `backend/models/state.py` module exposes two functions:

- **`export_json(GameState) -> str`** – Serialises a `GameState`
  instance to a JSON string suitable for export.
- **`import_json(str) -> GameState`** – Deserialises a JSON string
  back into a `GameState` object.

These helpers are used by the export endpoints and by internal tests
to verify round‑trip determinism.
