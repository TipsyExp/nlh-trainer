TASKS — M3
Milestone M3: All-Streets Advice & Unified Overlay

Change order:
• Complete TASK-31 → TASK-32 first (spec + unified API + context).
• Then TASK-33 → TASK-34 (postflop HU, then multiway).
• Finally TASK-35 → TASK-36 (frontend migration + logging/exports/dev tools).
________________________________________

Goals

• Ship a **single Advice payload** that can describe guidance on any street, HU or multiway.
• Make **/api/coach/advice** the primary coaching endpoint, with **/api/coach/preflop** as a legacy/specialized path.
• Add a **postflop equity-driven coach** (HU first, then multiway) built on the existing EquityService.
• Migrate the **table overlay** to consume the unified Advice object instead of separate coach + equity calls.
• Align **logging and exports** so every decision can carry a replayable coach_advice snapshot.
• Keep behaviour **backwards-compatible** and degrade gracefully when features or backends are disabled.
________________________________________

TASK-31 (M3): Advice Payload V1 Spec & Meta

Deliver

• Spec & docs
  • New: `docs/COACH-ADVICE-PAYLOAD.md`
    • Define `AdviceV1` as the universal payload for all coaching endpoints.
    • Describe fields by group:
      • Meta: street, n_players, hero_seat, source.
      • Recommendation: bucket, strategy_bar.
      • Equity: hero, players, vs_field, backend/mode flags, exact/iters.
      • Thresholds: pot_odds, spr (optional).
      • Rationale: human-readable explanation.
    • Define:
      • `version` (starting at `1`).
      • `status` enum (`ok`, `disabled`, `unsupported`, `not_found`, `timeout`, `error`).
    • Clarify how it relates to:
      • `/api/coach/preflop` (subset today).
      • `/api/equity` (source of equity fields).
      • Export snapshots (`preflop_advice`, `equity_snapshot`, future `coach_advice`).

  • Update: `docs/COACHING.md`, `docs/API-CONTRACT.md`
    • Introduce AdviceV1 as the conceptual response for all coach routes.
    • Note that `/api/coach/preflop` currently returns only the preflop-subset.
    • Mark `/api/coach/advice` as the universal endpoint and link to the payload doc.

  • Update: `docs/CONFIGURATION.md`, `docs/RUNBOOK.md`, `docs/STATE-SCHEMA.md`
    • Tie coach and equity configuration flags to fields in AdviceV1.
    • Cross-link which state fields feed AdviceV1 via the decision-context helper.

• Backend schema (internal)
  • New: `backend/schemas/advice.py` (or equivalent)
    • Define the backend representation of AdviceV1 (fields, version, status, groups).
    • Used by `/api/coach/advice`, logging, and exports.

• Meta capabilities
  • Update: `backend/api/meta.py`
    • Expose coach capabilities:
      • `coach.enabled`
      • `coach.advice_route` (true when `/api/coach/advice` is mounted).
      • `coach.advice_version` (1).
    • Keep or refine existing equity capability fields (backend, supports_ranges, max_players).

• Inline comments
  • Update docstrings/comments in:
    • `backend/coach/preflop/models.py`
    • `backend/api/coach.py`
    • `frontend/types/coach.ts`
    • `frontend/hooks/useDecisionOverlay.ts`
    • `frontend/components/DecisionHelpOverlay.tsx`
  • Explain how existing shapes map into AdviceV1 and point to the payload doc.

Accept

• AdviceV1 is documented once, referenced everywhere (backend, frontend, exports).
• `/api/coach/advice` and `/api/coach/preflop` docs both explicitly point at AdviceV1.
• `/api/meta` reports `coach.advice_route` and `coach.advice_version = 1`.
• No behavioural change yet, but all later tasks reference this spec instead of inventing ad-hoc shapes.
________________________________________

TASK-32 (M3): Unified Coach API & Decision Context

Deliver

• Unified decision context helper
  • New: `backend/coach/decision_context.py`
    • Provide a single helper that, given `(hand_id, idx)`, returns a normalized context including:
      • Hand identity: hand_id, idx.
      • Game framing: street, n_players, hero_seat, active seats, positional roles (where available).
      • Cards: hero hole cards (internally), board split by street.
      • Betting:
        • pot_total before hero acts.
        • to_call (full amount hero must put in to continue).
        • min_raise (final size, not increment).
        • allowed_buckets (labels aligned with UI).
      • Stack/commitment:
        • per-seat stacks behind.
        • per-seat committed amounts so far.
      • Status: is_terminal, any showdown information available.
    • Document semantics for each field (especially to_call, min_raise, pot_total).

  • Engine/state integration
    • Review/extend:
      • `backend/api/hand.py` (public state helpers).
      • Relevant engine/session modules.
    • Add minimal helpers if needed to:
      • Fetch engine state for `(hand_id, idx)`.
      • Surface stack/commitment and active seats cleanly.

• Make `/api/coach/advice` the unified route
  • Update: `backend/api/coach.py`
    • Handler for `GET /api/coach/advice`:
      • Uses decision_context helper as **sole source of state**.
      • Applies config gating (same `COACH_ENABLED` semantics as preflop).
      • Branches by street:
        • Preflop:
          • Delegates to existing preflop advisor service.
          • Wraps result into AdviceV1 (meta + recommendation + rationale; equity/thresholds may be absent).
        • Postflop:
          • For now returns a clear non-crashy “not implemented” status (or 501) with minimal AdviceV1 where appropriate.
      • Prefer 200 + `status` for runtime “unsupported” cases, reserve 501 for global disable/misconfig.

  • Keep `/api/coach/preflop` as legacy
    • Behaviour unchanged (same JSON as M2).
    • Allowed (but not required) to be implemented via the same internal service/decision_context for reduced duplication.

• Refactor coach consumers onto the new context
  • Update: `backend/coach/preflop/service.py`
    • Accept or request the decision context instead of reconstructing pot/to_call/hero seat independently.
  • Update: `backend/coach/node_builder.py`
    • Use the decision context helper for street, board, stacks, pot, etc., when building solver requests.

• Tests & docs
  • New/extend: `backend/tests/test_decision_context.py`
    • Validate context correctness for:
      • Preflop, flop, turn, river.
      • HU vs multiway.
      • Terminal spots.
  • Extend: `backend/tests/test_api_coach.py`
    • `/api/coach/advice` returns AdviceV1 (preflop) with `status='ok'` when enabled.
    • Expected behaviour when disabled or called postflop at this stage.
  • Update docs:
    • `docs/COACHING.md`, `docs/API-CONTRACT.md` to describe decision context as the canonical backing for coaching.

Accept

• `/api/coach/advice` is wired and returns AdviceV1 for preflop; postflop requests respond deterministically with either a 200 + non-ok status or a clear 501 when globally disabled.
• Preflop advisor and solver node builder both consume the shared decision context helper.
• Decision context semantics (to_call, min_raise, pot_total, n_players) are tested and locked in.
________________________________________

TASK-33 (M3): Postflop Coach V1 — HU, Hands-Only

Deliver

• Postflop coach module (HU)
  • New: `backend/coach/postflop/service.py`
    • Entry point: “given decision context for flop/turn/river, HU only, return AdviceV1”.
    • Responsibilities:
      • Require:
        • street ∈ {flop, turn, river}
        • n_players == 2
        • hero hand and board known
      • Use EquityService to compute hero vs villain equity:
        • Hero: exact hand.
        • Villain: range from a simple profile.
      • Compute pot odds and equity threshold:
        • pot_odds based on to_call and pot_total pre-action.
      • Decide recommendation:
        • Facing a bet:
          • Equity below threshold → fold.
          • Around threshold → call.
          • Well above threshold and raises allowed → call/raise mix or pure raise.
        • No bet to face:
          • Simple hand-strength heuristics (made hand vs draw vs air) → bet/check.
      • Build strategy_bar (initially mostly single-bucket).
      • Fill AdviceV1:
        • `meta`: street, n_players, hero_seat, source="equity".
        • `recommendation`: bucket, strategy_bar.
        • `equity`: hero, villain, backend/mode/exact/iters if available.
        • `thresholds`: pot_odds (spr optional).
        • `rationale`: explain equity vs threshold and recommendation.

• Villain profiles & config
  • New: `backend/coach/postflop/ranges.py`
    • Define simple HU villain profiles per street/role (e.g., generic “TAG”).
  • Update: `backend/config.py`
    • Add postflop coach knobs, for example:
      • `POSTFLOP_COACH_ENABLED`
      • `POSTFLOP_COACH_ITERS`
      • `POSTFLOP_COACH_PROFILE`
      • Optional timeout/seed controls for EquityService use inside coach.

• EquityService integration
  • Update: `backend/services/equity/service.py`
    • Add a small helper oriented to “hero hand vs villain range on given board” for HU coaching.
    • Honour the new postflop coach config knobs for iters/timeout.

• Hook into `/api/coach/advice`
  • Update: `backend/api/coach.py`
    • For flop/turn/river with `n_players == 2` and postflop coach enabled:
      • Delegate to `backend/coach/postflop/service.py`.
    • For other postflop spots:
      • Return a clear `status` such as `unsupported` (still 200) or explicit 501 if globally disabled.

• Tests & docs
  • New: `backend/tests/test_postflop_coach_hu.py`
    • HU flop/turn/river scenarios:
      • Very weak hand vs bet → fold.
      • Medium equity near pot odds → call.
      • Strong hand with raises allowed → raise or raise-heavy mix.
      • No bet spots (check vs bet decisions).
    • Validate AdviceV1 fields: version, status, meta, recommendation, equity, thresholds, rationale.
  • Update: `docs/COACHING.md`, `docs/API-CONTRACT.md`
    • Document “Postflop Coach V1 (HU, hands-only)”:
      • Scope, assumptions, and how `/api/coach/advice` uses it.

Accept

• For eligible HU postflop decisions, `/api/coach/advice` returns AdviceV1 with:
  • `status='ok'`, `meta.source='equity'`, sensible bucket/strategy_bar.
  • `equity.hero` and `thresholds.pot_odds` consistent with the spot.
• Ineligible spots (multiway, missing data, disabled) return non-ok status or 501 without crashing.
• Performance and determinism are acceptable with configured iters/timeout.
________________________________________

TASK-34 (M3): Multiway Coaching & Equity Integration

Deliver

• Multiway coach extension
  • Extend: `backend/coach/postflop/service.py`
    • Add multiway path for `n_players > 2` where multiway equity is available.
    • Responsibilities:
      • Use decision context to build players list:
        • Hero: exact hand.
        • Each villain: range/profile.
      • Call EquityService with a multiway-capable backend.
      • Derive:
        • hero_equity.
        • players_equity array `{ seat, equity }`.
        • vs_field_equity (hero vs all others combined) as needed for UI.
      • Apply multiway heuristics:
        • More conservative folds when closing action multiway.
        • Adjust raise tendencies based on stack-to-pot ratios and position.
      • Fill AdviceV1 identically to HU path, including n_players and players_equity.

• Villain profiles for multiway
  • New: `backend/coach/postflop/multiway_profiles.py`
    • Given street, seat count, roles (opener, caller, blinds, etc.), return per-seat range profiles.
  • Extend: `backend/coach/postflop/ranges.py`
    • Shared helpers for turning profiles/presets into explicit ranges usable by EquityService.

• Decision context multiway fields
  • Extend: `backend/coach/decision_context.py`
    • Ensure context exposes:
      • Active seats in pot.
      • Per-seat stack behind and committed amounts.
      • Clear multiway `n_players` for the current decision.
    • Keep semantics shared between HU and multiway paths.

• EquityService multiway helper
  • Extend: `backend/services/equity/service.py`
    • Add helper focused on “multiway coaching”:
      • Chooses appropriate backend for ranges + multiway.
      • Uses coaching-specific iters/time budget.
      • Returns structure easily mapped to players_equity and vs_field_equity.
    • Explicitly handle “no multiway backend” and signal this cleanly to the coach.

• Config & API branch
  • Update: `backend/config.py`
    • Multiway coach toggles:
      • `POSTFLOP_COACH_MULTIWAY_ENABLED`
      • Multiway-specific iters/timeout.
      • Optional policy for multiway backend selection.
  • Update: `backend/api/coach.py`
    • Branching for postflop:
      • `n_players == 2` → HU path.
      • `n_players > 2` and multiway enabled → multiway path.
      • Otherwise → AdviceV1 with `status='unsupported'` or similar, not a 500.

• Tests & docs
  • New: `backend/tests/test_postflop_coach_multiway.py`
    • 3–6-way scenarios:
      • Hero closing action vs bet with low equity → fold.
      • Hero strong vs field → at least call, sometimes raise if allowed.
    • Validate:
      • n_players.
      • players_equity length and hero slot.
      • vs_field_equity when present.
      • Behaviour when multiway backend is missing (status not ok, no crash).
  • Update: `docs/COACHING.md`, `docs/EQUITY.md`, `docs/API-CONTRACT.md`
    • Add “Multiway postflop coaching” section.
    • Clarify requirements and fallback behaviour when multiway equity is unavailable.

Accept

• For supported multiway spots, `/api/coach/advice` returns AdviceV1 with:
  • n_players > 2 and meaningful players_equity.
  • A bucket/strategy consistent with multiway heuristics.
• When multiway is disabled or not supported by backends, the endpoint still responds deterministically with non-ok status (or explicit “unsupported”), never a 500.
________________________________________

TASK-35 (M3): Frontend Overlay Migration to Unified Advice

Deliver

• Types & utilities
  • New: `frontend/types/advice.ts`
    • Define the frontend Advice type mirroring AdviceV1 (meta, recommendation, equity, thresholds, rationale, status, version).
  • Update: `frontend/types/coach.ts`
    • Re-export or adapt to use the unified Advice type instead of the old preflop-only type.
  • Update: `frontend/types/equity.ts`
    • Keep for non-overlay uses; annotate that the overlay now reads equity via Advice.
  • Update: `frontend/types/meta.ts`, `frontend/utils/meta.ts`, `frontend/hooks/useMeta.ts`
    • Surface `coach.advice_route`, `coach.advice_version`, existing equity capabilities.

  • Update: `frontend/utils/http.ts`
    • Ensure helpers comfortably handle `/api/coach/advice` responses and map HTTP errors to overlay status where needed.

• Overlay cache & mapping
  • Update: `frontend/utils/overlayCache.ts`
    • Change cache entries to store unified Advice (and status) keyed by `(sessionId, handId, idx, street)` or similar.
    • Remove separate coach + equity cache paths for the overlay.
  • Update: `frontend/utils/coachMapping.ts`
    • Ensure bucket→button mapping works for preflop and postflop and matches backend labels.

• Hooks
  • Major update: `frontend/hooks/useDecisionOverlay.ts`
    • Primary flow:
      • Call `/api/coach/advice?hand_id=...&idx=...`.
      • Use AdviceV1 as the main datum for the overlay.
    • Fallback logic:
      • If `/api/coach/advice` is missing/disabled and street is preflop:
        • Optionally call `/api/coach/preflop` and wrap its response into AdviceV1 client-side.
    • Status handling:
      • Trust the `status` field where returned; otherwise derive simple statuses from HTTP codes.
    • Remove overlay’s dependency on `/api/equity` for the main display.

  • Light update: `frontend/hooks/useDecisionContext.ts`
    • Continue to derive decision context from table page.
    • Provide whatever identifiers `/api/coach/advice` needs (handId, idx, street, hero seat, etc.).

• Overlay UI
  • Major update: `frontend/components/DecisionHelpOverlay.tsx`
    • Accept unified Advice + status + meta.
    • Render:
      • Recommended action from `advice.recommendation.bucket`.
      • Strategy bar from `advice.recommendation.strategy_bar`.
      • Equity view from `advice.equity.hero` and `advice.equity.players`.
      • Multiway list when `n_players > 2`.
      • Pot odds and any EV hint when present.
    • Use status chips or badges for `ok`, `disabled`, `unsupported`, `timeout`, etc.

  • Update: `frontend/components/StrategyBar.tsx`
    • Generic bucket/weight display, not tied to preflop only.
  • Update: `frontend/components/HeroEquityBar.tsx`
    • Read from Advice equity (hero or vs_field) and show backend/mode labels when available.
  • New (optional): `frontend/components/PlayersEquityList.tsx`
    • Compact list of per-seat equities for multiway spots.

  • Update: table page/container
    • Stop passing separate coach and equity objects.
    • Pass unified advice state from `useDecisionOverlay` into `DecisionHelpOverlay`.

• Dev tools
  • Update: `frontend/store/overlayDebugStore.ts`
    • Track last Advice call/result for debugging (status, bucket, hero_equity).
  • Update: `frontend/dev/SnapshotInspector.tsx`
    • Show whether `/api/coach/advice` was used for the last decision.
    • Prepare UI to display exported `coach_advice` snapshots (see TASK-36).

• Tests
  • New/update: `frontend/__tests__/useDecisionOverlay.test.tsx`
    • Cover:
      • Normal AdviceV1 path.
      • Preflop fallback to legacy /coach/preflop.
      • Disabled/unsupported/timeouts.
  • Update: `frontend/__tests__/DecisionHelpOverlay.test.tsx`
    • Ensure HU and multiway advice render correctly across status variants.

Accept

• With backend M2 + M3 changes:
  • Overlay primarily uses `/api/coach/advice`, with preflop fallback when needed.
  • Overlay displays a single unified Advice block (action, strategy bar, equity) instead of separate coach/equity sections.
• When postflop coach is disabled or unsupported, overlay surfaces that cleanly and does not crash.
• No regressions in Phase 4 behaviour (preflop overlay still works even in environments that only have preflop coach).
________________________________________

TASK-36 (M3): Logging, Exports & Dev Tools Alignment

Deliver

• Logging & DB schema
  • Update: log schema module(s) (e.g., `backend/logging/schema.py`)
    • Add a `coach_advice` JSON field on per-action rows (nullable).
    • Keep `preflop_advice` and `equity_snapshot` fields intact for compatibility.
    • Provide a migration path for existing dev/QA databases.

  • Update: logging helpers (e.g., `backend/logging/helpers.py`)
    • New helper: `log_coach_advice(hand_id, idx, advice_blob)`.
    • Keep existing `log_preflop_advice`, `log_equity_snapshot`.
    • Define how preflop calls via `/api/coach/advice` interact with `preflop_advice`:
      • For example: log unified `coach_advice` always, and optionally mirror preflop fields into `preflop_advice`.

• Coach & equity endpoints
  • Update: `backend/api/coach.py`
    • After building AdviceV1 for `/api/coach/advice`, conditionally call `log_coach_advice` when logging is enabled.
    • When the spot is preflop and legacy logging is enabled, optionally keep logging `preflop_advice` as before.

  • Confirm: `backend/api/routes/equity.py`
    • Equity snapshots continue to be logged unchanged.
    • Document clearly that:
      • `coach_advice` describes “what the coach showed”.
      • `equity_snapshot` is raw equity calculation (can differ if coach uses heuristics).

• Export endpoints
  • Update: `backend/api/export.py`
    • JSON exports (`/api/export/hand`, `/api/export/session`):
      • Extend action entries to include `coach_advice` (AdviceV1 blob) when available.
      • Keep `preflop_advice` and `equity_snapshot` behaviour unchanged.
    • CSV exports:
      • Confirm they remain minimal and do not add `coach_advice` columns.

• Config & docs
  • Update: `backend/config.py`
    • Add logging flag(s), for example:
      • `LOG_COACH_ADVICE`
      • Keep `LOG_PREFLOP_ADVICE`, `LOG_EQUITY_SNAPSHOT` semantics clear.
  • Update docs:
    • `docs/API-CONTRACT.md`
      • Document `actions[*].coach_advice` in export JSON.
    • `docs/CONFIGURATION.md`
      • Describe new logging flags and interactions.
    • `docs/COACHING.md`, `docs/RUNBOOK.md`, `docs/QA-CHECKLIST.md`
      • Explain how to enable advice logging and verify via exports.
      • Add QA steps to confirm `coach_advice` presence when `/api/coach/advice` is called.

• Frontend export consumers & tools
  • Update: `frontend/types/export.ts`
    • Add optional `coach_advice` field on export action type (matching AdviceV1 or its subset).
  • Update: `frontend/utils/export.ts`
    • Preserve `coach_advice` when parsing exports.
  • Update: `frontend/dev/SnapshotInspector.tsx`
    • When `coach_advice` is present:
      • Display at least source, bucket, and optionally hero_equity.
    • Maintain existing handling of `preflop_advice` and `equity_snapshot`.

• Tests
  • Backend:
    • `backend/tests/test_export_hand.py`, `test_export_session.py`
      • Verify that:
        • With logging enabled and `/api/coach/advice` called, exports include `actions[idx].coach_advice`.
        • Preflop behaviour (presence/absence of `preflop_advice`) matches documented policy.
    • `backend/tests/test_logging_snapshots.py`
      • Exercise `log_coach_advice` in isolation.
  • Frontend:
    • `frontend/__tests__/SnapshotInspector.test.tsx`
      • Assert SnapshotInspector renders coach_advice when present and remains robust when only preflop/equity snapshots are available.

Accept

• Playing a hand with the overlay enabled and logging flags on yields exports where:
  • Each advised decision has `coach_advice` populated with AdviceV1.
  • Preflop decisions optionally still have `preflop_advice`.
  • Equity snapshots remain available where `/api/equity` is used.
• SnapshotInspector can show “what advice was logged” for any decision without breaking when fields are absent.
• Schema changes are backwards-compatible; old exports and replays still work.
________________________________________

M3 Acceptance (Overall)

• `/api/coach/advice` returns AdviceV1 with `status='ok'` for preflop, and appropriate non-ok `status` (or documented 501) for disabled/unsupported spots; no unexplained 500s in normal flows.
• HU postflop coaching is live: eligible flop/turn/river spots get equity-driven AdviceV1; multiway spots return either multiway advice or clearly marked “unsupported” depending on configuration/backends.
• Frontend overlay prefers `/api/coach/advice` and falls back to `/api/coach/preflop` only when necessary; separate `/api/equity` calls are no longer required for the overlay.
• Exports can include `coach_advice` snapshots for any street, with `preflop_advice` and `equity_snapshot` preserved for backwards compatibility.
• Dev tools (SnapshotInspector + overlay debug store) can inspect unified advice and correlate it with what was shown at the table.
