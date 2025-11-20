# docs/COACHING.md
# Coaching

This document describes how coaching works end-to-end:

- What the coach returns (the **Advice** payload).
- Which endpoints exist and how they relate.
- How backend coaching logic builds on a shared **decision context**.
- How the **Table overlay** consumes advice.
- How this ties into logging and exports at a high level.

For the full Advice payload spec, see **`docs/COACH-ADVICE-PAYLOAD.md`**.

---

## 1. Advice payload (AdviceV1)

All coaching is built around a single, versioned payload:

- **Type:** `AdviceV1`
- **Version:** `version: 1`
- **Status:** `status: 'ok' | 'disabled' | 'unsupported' | 'not_found' | 'timeout' | 'error'`

High-level shape (conceptual):

- `status`: whether the advice is actionable.
- `meta`: street, number of active players, hero seat, advice source.
- `recommendation`:
  - `bucket` – canonical action label (`fold`, `call`, `check`, `2.5x`, `2.5xR`, `jam`, …).
  - `strategy_bar` – action → weight distribution.
- `equity`: hero and per-player equities, backend, mode, iters, etc.
- `thresholds`: pot odds and optional SPR.
- `rationale`: human-readable explanation.

Full field list and semantics live in **`COACH-ADVICE-PAYLOAD.md`**. This file should be treated as the canonical spec.

---

## 2. Endpoints

### 2.1 `/api/coach/advice` (universal route)

- **Method:** `GET`
- **Query:** `hand_id`, `idx` (current decision index).
- **Response:** a single `AdviceV1` object.

Behavior (target state for M3):

- Always returns `200 OK` for normal runtime outcomes, with `advice.status` conveying:
  - `ok` – advice is actionable.
  - `disabled` – coach globally off (config).
  - `unsupported` – decision not supported (street, n_players, backend limits, etc.).
  - `not_found` – hand or decision missing.
  - `timeout` – solver/equity budget exceeded.
  - `error` – internal error (unexpected).

- Street-specific behavior:
  - **Preflop:**
    - Delegates to the existing **preflop advisor**.
    - Wraps its result into `AdviceV1` (`meta.source='chart' | 'equity' | 'rule'`).
  - **Postflop HU:**
    - Uses the **postflop equity-based coach** (flop/turn/river, n_players == 2).
    - Fills `equity` and `thresholds` where possible.
  - **Postflop multiway:**
    - Uses multiway coach path when supported by backends and config.
    - Otherwise returns `status='unsupported'`.

When coaching is completely disabled at the service level (e.g. feature gated), the route may return `501` rather than `200 + status='disabled'`.

### 2.2 `/api/coach/preflop` (legacy / specialised)

- **Method:** `GET`
- **Query:** `hand_id`, `idx` (preflop decision index).
- **Response:** legacy preflop advice object:

  - `source`
  - `bucket`
  - `strategy_bar`
  - `rationale`

Relationship to AdviceV1:

- This is effectively a **subset** of `AdviceV1`:
  - `source` → `meta.source`
  - `bucket` → `recommendation.bucket`
  - `strategy_bar` → `recommendation.strategy_bar`
  - `rationale` → `rationale`
- It exists for compatibility with older tooling and tests.
- Internally, it may be a thin wrapper around the same logic that powers `/api/coach/advice`.

---

## 3. Decision context helper

Backend coaching logic does not work directly on raw engine state. Instead, it uses a shared **decision context** helper:

- **Module:** `backend/coach/decision_context.py`
- **Inputs:** `(hand_id, idx)`
- **Outputs:** a normalized context object with at least:

  - Hand identity:
    - `hand_id`
    - `idx`
  - Game framing:
    - `street` (preflop / flop / turn / river / terminal)
    - `n_players` (active players in the pot)
    - `hero_seat`, positions (BTN/SB/BB) if needed.
  - Cards:
    - Hero hole cards.
    - Board cards split by flop / turn / river.
  - Betting situation:
    - `pot_total` before hero acts.
    - `to_call` (total chips required to continue).
    - `min_raise` (total final amount, not just increment).
    - `allowed_buckets` (canonical labels used by UI).
  - Stack / commitment:
    - Per-seat stacks behind.
    - Per-seat committed amounts.
  - Status:
    - Active seats.
    - Whether the decision is terminal.

Consumers:

- `/api/coach/advice` – builds AdviceV1 from this context.
- Preflop advisor – uses the context for node classification and sanity checks.
- Postflop coach – uses hero hand, board, pot, and stacks for equity-based heuristics.
- Solver integration (`node_builder`) – constructs solve requests from the same context.
- (Later) Logging and exports – may reuse context to enrich snapshots.

The **goal** is that all coaching and solver paths share one truthful view of the decision and avoid duplicating state derivation logic.

---

## 4. Coach UI (Table Overlay)

### 4.1 Location & toggle

- **Where:** Table page, top-right panel.
- **Toggle:** A user-controlled switch enables or disables guidance.
  - When Off: no calls to `/api/coach/advice` for overlay purposes.
  - When On: overlay fetches advice for the current decision.

The overlay also reads `/api/meta` to learn whether coaching is enabled and which capabilities are available (e.g. advice route version, equity backend support).

### 4.2 Behavior

When the overlay is **On**:

- For each visible decision (identified by `hand_id` + `idx`):

  - Primary call:
    - `GET /api/coach/advice?hand_id=…&idx=…`
  - Fallback (preflop only):
    - If `/api/coach/advice` is missing or returns `501`/`404` and the street is **preflop**, the UI may:
      - Call `/api/coach/preflop`.
      - Wrap that response into the AdviceV1 shape client-side for display.

- No polling:
  - The overlay refetches advice **only when the decision index changes** (or the overlay toggle/meta configuration changes).
  - Navigation between decisions (actions, auto-advance) drives advice refresh.

- What the user sees (when `advice.status === 'ok'`):
  - **Recommended action:**
    - The chosen `recommendation.bucket` mapped to a highlighted table button.
  - **Strategy bar:**
    - A visual bar for `recommendation.strategy_bar` (bucket → weight), showing how often each action is recommended.
  - **Equity view:**
    - For HU:
      - A hero equity percentage/bar based on `equity.hero`.
    - For multiway:
      - Optional hero vs field bar (using `equity.hero` or `equity.vs_field`).
      - Optional per-seat equities from `equity.players`.
  - **Pot odds / hints:**
    - When present, `thresholds.pot_odds` and any EV hint classification (if defined) may be surfaced as helper text/badges.
  - **Rationale:**
    - A textual explanation from `advice.rationale` describing why the recommendation was made.

The overlay should be able to render **the same UI** regardless of street or player count, driven solely by the AdviceV1 payload.

### 4.3 Status mapping (UI)

The overlay interprets `advice.status` as follows:

- **`ok`**
  - Advice is available and rendered.
  - UI displays recommendation, strategy bar, and any equity information present.

- **`disabled`**
  - Coach is off via configuration (e.g. `COACH_ENABLED=false` or similar flags).
  - UI shows a “Coach disabled” indicator.
  - No additional requests are made until config/meta indicates it is enabled again.

- **`unsupported`**
  - The route is working but the specific decision is not supported by the current coach configuration or backends:
    - Street not implemented yet.
    - Multiway spot where multiway coaching is off or backend unavailable.
    - Any other policy-level exclusion.
  - UI shows “Unsupported spot” (or equivalent) and may hide the detailed advice sections for that decision.

- **`timeout`**
  - Coach attempted to compute advice (solver/equity) but hit a time/iteration budget.
  - UI shows a “Timed out” indicator.
  - Cached results (if any) may still be used for other decisions.

- **`not_found`**
  - Hand or decision index could not be located.
  - UI shows a “Decision not found” indicator; typically only seen in dev / stale links.

- **`error`**
  - Internal error while computing advice.
  - UI shows a generic “Error” indicator and does not attempt to interpret partial fields.

- **Network / HTTP failures**
  - For network failures or HTTP 5xx unrelated to normal coach states:
    - UI treats them as “Unavailable” and may surface a transient error message.
    - The overlay should remain robust and not break the table.

The previous `meta.status` field used in some early docs is superseded by the top-level `status` field on AdviceV1.

---

## 5. Logging & Exports (high-level)

Coaching integrates with logging and exports to make behavior testable and debuggable:

- When logging is enabled and `/api/coach/advice` is called for a given `(hand_id, idx)`:
  - The returned AdviceV1 object may be stored as `coach_advice` snapshot on that action.
- Existing snapshots:
  - `preflop_advice` – legacy preflop advisor payload (from `/api/coach/preflop`).
  - `equity_snapshot` – raw equity result from `/api/equity`.

Export endpoints (`/api/export/hand`, `/api/export/session`) include these snapshots per action when present. Over time, `coach_advice` becomes the primary all-streets view of what was shown to the user.

Details of the export format and logging flags live in:

- `docs/API-CONTRACT.md`
- `docs/CONFIGURATION.md`
- `docs/RUNBOOK.md`
- `docs/COACH-ADVICE-PAYLOAD.md` (for the AdviceV1 payload within `coach_advice`).

---
