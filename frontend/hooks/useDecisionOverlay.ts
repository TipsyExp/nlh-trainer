// frontend/hooks/useDecisionOverlay.ts
// Hook to fetch and cache unified coach advice for the guidance overlay.
//
// New behaviour:
// - Uses GET /api/coach/advice for ALL streets (preflop + postflop).
// - The backend returns a unified Advice payload (see ../types/advice).
// - Equity, if any, is included directly inside that Advice payload.
//
// This hook now orchestrates a *single* request per decision and exposes
// a unified `Advice` object instead of separate coach + equity calls.

import { useEffect, useState, useMemo } from 'react';
import { getJson } from '../utils/http';
import {
  getCoach,
  setCoach,
  getCoachInFlight,
  setCoachInFlight,
  deleteCoachInFlight,
  type CoachResponse,
} from '../utils/overlayCache';
import { mapCoachToAction } from '../utils/coachMapping';
import { useMeta } from './useMeta';
import type { DecisionContext } from '../types/decision';
import type { Advice } from '../types/advice';
import type { Meta } from '../types/meta';
import { setOverlayTrace } from '../store/overlayDebugStore';

// Default client timeout for the coach endpoint (in ms).
// TexasSolver can take a few seconds on first solve, so keep this reasonably high.
const DEFAULT_TIMEOUT_MS = 20000;
const COACH_TIMEOUT_MS = (() => {
  const raw = process.env.NEXT_PUBLIC_COACH_CLIENT_TIMEOUT_MS;
  const n = raw ? parseInt(String(raw), 10) : NaN;
  return !Number.isNaN(n) && n > 0 ? n : DEFAULT_TIMEOUT_MS;
})();

// Convert HTTP status codes into normalised coach statuses.
function statusFromResult(res: {
  ok: boolean;
  status: number | 'timeout';
}): 'ok' | 'disabled' | 'not_found' | 'unavailable' {
  if (res.status === 'timeout') return 'unavailable';
  if (res.ok) return 'ok';
  if (res.status === 501) return 'disabled';
  if (res.status === 404) return 'not_found';
  return 'unavailable';
}

export interface UseDecisionOverlayResult {
  advice: {
    data: Advice | null;
    loading: boolean;
    status: 'ok' | 'loading' | 'disabled' | 'not_found' | 'unavailable';
    error?: string;
  };
  /** Convenience mapping of the coach’s recommended bucket -> action key for the UI. */
  recommendedAction: string | null;
  meta: {
    meta: Meta | null;
    loading: boolean;
    error?: string;
  };
}

export function useDecisionOverlay(
  context: DecisionContext | null,
  overlayEnabled: boolean
): UseDecisionOverlayResult {
  // Fetch meta capabilities once per session (still useful for other UI bits).
  const metaState = useMeta();

  // Store the current coach/advice response record.
  const [coachResponse, setCoachResponse] = useState<CoachResponse | null>(null);

  // ------------------- Unified advice fetching -------------------
  useEffect(() => {
    // Always update overlay trace for current decision; reset calledAdvice flag.
    setOverlayTrace({
      handId: context?.handId ?? null,
      idx: typeof context?.idx === 'number' ? (context?.idx as number) : null,
      street: context?.street ?? null,
      // This now represents the single unified advice call.
      calledAdvice: false,
    });

    const shouldFetch =
      overlayEnabled &&
      context !== null &&
      !!context.handId &&
      typeof context.idx === 'number';

    if (!shouldFetch) {
      setCoachResponse(null);
      return;
    }

    // Keyed by hand_id + idx + street so that preflop / flop / turn / river
    // decisions don't accidentally share the same cached advice.
    const key = `${context.handId}:${context.idx}:${context.street ?? 'unknown'}`;

    const cached = getCoach(key);
    if (cached) {
      if (process.env.NEXT_PUBLIC_DEV_TOOLS) {
        // eslint-disable-next-line no-console
        console.debug('[advice] cached', key);
      }
      setCoachResponse(cached);
      return;
    }

    const existing = getCoachInFlight(key);
    if (existing) {
      existing.then((res) => {
        setCoachResponse(res);
      });
      return;
    }

    const abortController = new AbortController();
    const prom: Promise<CoachResponse> = (async () => {
      if (process.env.NEXT_PUBLIC_DEV_TOOLS) {
        // eslint-disable-next-line no-console
        console.debug('[advice] fetch', {
          hand_id: context.handId,
          idx: context.idx,
        });
      }
      // Mark that we made an advice call for this decision.
      setOverlayTrace({ calledAdvice: true });

      const qs = `hand_id=${encodeURIComponent(String(context.handId))}&idx=${
        context.idx
      }`;

      try {
        const res = await getJson(`/api/coach/advice?${qs}`, {
          timeoutMs: COACH_TIMEOUT_MS,
          signal: abortController.signal,
        });
        const status = statusFromResult(res);
        if (status === 'ok') {
          const data = res.body as Advice;
          const resp: CoachResponse = { data, status: 'ok' };
          setCoach(key, resp);
          return resp;
        } else {
          const resp: CoachResponse = {
            data: null,
            status,
            error:
              status === 'disabled'
                ? 'Coach disabled'
                : status === 'not_found'
                ? 'Advice route not available'
                : res.status === 'timeout'
                ? 'Coach timed out'
                : 'Coach unavailable',
          };
          setCoach(key, resp);
          return resp;
        }
      } catch (e: any) {
        const resp: CoachResponse = {
          data: null,
          status: 'unavailable',
          error: e?.message || 'Coach unavailable',
        };
        setCoach(key, resp);
        return resp;
      } finally {
        deleteCoachInFlight(key);
      }
    })();

    setCoachInFlight(key, prom);
    prom.then((res) => {
      setCoachResponse(res);
    });

    return () => {
      abortController.abort();
    };
  }, [context?.handId, context?.idx, overlayEnabled, context?.street]);

  // ------------------- Derived advice state -------------------
  const adviceState = useMemo(() => {
    if (!overlayEnabled) {
      return {
        data: null,
        loading: false,
        status: 'disabled' as const,
        error: undefined,
      };
    }

    if (!context || !context.handId || typeof context.idx !== 'number') {
      return {
        data: null,
        loading: false,
        status: 'not_found' as const,
        error: 'No decision context',
      };
    }

    if (coachResponse === null) {
      return {
        data: null,
        loading: true,
        status: 'loading' as const,
        error: undefined,
      };
    }

    if (coachResponse.status === 'ok') {
      return {
        data: coachResponse.data,
        loading: false,
        status: 'ok' as const,
        error: undefined,
      };
    }

    return {
      data: null,
      loading: false,
      status: coachResponse.status as any,
      error: coachResponse.error,
    };
  }, [coachResponse, overlayEnabled, context]);

  // Recommended action key derived from the coach's chosen bucket
  // (solver: recommendation.bucket, older paths: recommendation.primary_action).
  const recommendedAction = useMemo(() => {
    if (!context) return null;
    if (adviceState.status !== 'ok' || !adviceState.data) return null;

    const rec = adviceState.data.recommendation;
    const bucket = rec?.bucket || rec?.primary_action;
    if (!bucket) return null;

    const toCall = context.toCall ?? 0;
    // We don't know presets here; let caller reconcile if needed.
    return mapCoachToAction(bucket, toCall, []);
  }, [adviceState, context]);

  return {
    advice: adviceState,
    recommendedAction,
    meta: { meta: metaState.meta, loading: metaState.loading, error: metaState.error },
  };
}
