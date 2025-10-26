# NLH Trainer — API Contract (v0.1)

This document specifies the **public backend API** for the NLH Trainer as implemented in M0/M1 Task-12 (logging + export). It covers health checks, session management, hand play, and export endpoints.

> Notes  
> - Authentication: **none** (local/dev only).  
> - Base URL: service root (e.g., `http://localhost:8000`).  
> - All API routes are mounted under `/api` unless otherwise shown.  
> - Content type: `application/json` unless specified (CSV endpoints).  
> - Error payload: `{"detail": "message"}` with an appropriate HTTP status.

---

## Conventions & Types

- **IDs**
  - `session_id`: integer, returned by `/api/session` on creation.
  - `hand_id`: string (e.g., `"H1"`), returned by `/api/hand/start`.

- **Enums (JSON values)**  
  These appear as strings in JSON:
  - `Street`: `"preflop" | "flop" | "turn" | "river" | "showdown" | "complete"`
  - `ActionType`: `"check" | "call" | "bet" | "raise" | "fold" | "post_blind" | "all_in" | "deal"`
  - `SeatType`: `"human" | "bot"`
  - `PlayerStatus`: `"active" | "folded" | "all_in"`

- **Timestamps**  
  `created_at` fields are ISO-8601 UTC (e.g., `"2025-10-26T09:41:00+00:00"`).

- **Booleans**  
  `snapped` is exported as `true/false` in JSON and `0/1` in CSV.

---

## Health

### GET `/`
Returns a liveness check.

**200 OK**
```json
{"ok": true, "message": "NLH Trainer backend is up"}
