// frontend/components/DecisionHelpOverlay.tsx
// Presentational overlay for hand guidance (phase 3, updated in phase 5).
//
// This component renders a fixed panel on the right side of the screen (or
// bottom on small screens) and displays coach advice and equity for the
// current decision.  It is purely presentational: all network logic is
// encapsulated in hooks invoked by the parent component.  Consumers
// supply normalised coach and equity state along with the meta snapshot.
//
// Future alignment (M3+):
// - The UI here is conceptually tied to the universal Advice payload described
//   in docs/COACH-ADVICE-PAYLOAD.md.
// - The "Recommended" section corresponds to advice.recommendation.bucket and
//   advice.recommendation.strategy_bar.
// - The equity block corresponds to advice.equity.hero / advice.equity.players
//   plus thresholds and rationale fields.
// When the backend / hook migrate to GET /api/coach/advice, this component
// should be able to render that AdviceV1 shape with minimal changes.

import React from 'react';
import type { DecisionContext } from '../types/decision';
import { StrategyBar } from './StrategyBar';
import { StatusChip } from './StatusChip';
import { HeroEquityBar } from './HeroEquityBar';
import type { CoachAdvice } from '../types/coach';
import type { EquityResponse } from '../types/equity';
import type { EquityStatus } from '../utils/overlayCache';
import type { Meta } from '../types/meta';

export interface DecisionHelpOverlayProps {
  /** Optional decision context (unused here but reserved for future extensions). */
  decision?: DecisionContext | null;
  /** Normalised coach state from useDecisionOverlay. */
  coach: {
    data: CoachAdvice | null;
    loading: boolean;
    status: 'ok' | 'loading' | 'disabled' | 'not_found' | 'unavailable';
    error?: string;
  };
  /** Normalised equity state from useDecisionOverlay. */
  equity: {
    data: EquityResponse | null;
    loading: boolean;
    status: EquityStatus;
    error?: string;
    origin?: string;
  };
  /** Meta snapshot from useDecisionOverlay (contains backend name). */
  meta: {
    meta: Meta | null;
    loading: boolean;
    error?: string;
  };
}

/**
 * Guidance overlay for preflop advice and (in later phases) equity.
 *
 * This component hooks into the decision context and overlay gate to
 * fetch coach advice, render recommended actions and display a status
 * indicator.  It does not itself perform any network calls; those are
 * encapsulated in the useDecisionOverlay hook.  When advice is not
 * available a friendly message is shown.  The overlay should mount
 * only when the overlayEnabled prop is true.
 */
export function DecisionHelpOverlay({ decision, coach, equity, meta }: DecisionHelpOverlayProps) {
  return (
    <div
      role="region"
      aria-label="Guidance"
      className="fixed z-40 right-4 top-4 md:right-4 md:top-4 max-w-[90vw] w-80 md:w-96"
    >
      <div className="bg-white shadow-lg rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Guidance</h2>
          {/* Status badge summarises the current coach state */}
          <StatusChip status={coach.status} />
        </div>
        {/* Coach section depends on coach status */}
        {coach.status === 'loading' && (
          <div className="space-y-2">
            <div className="h-4 w-32 bg-gray-100 animate-pulse rounded"></div>
            <div className="h-3 w-24 bg-gray-100 animate-pulse rounded"></div>
          </div>
        )}
        {coach.status === 'disabled' && (
          <div className="text-sm text-gray-600">Coach disabled or not configured.</div>
        )}
        {coach.status === 'not_found' && (
          <div className="text-sm text-gray-600">Coach route not available.</div>
        )}
        {coach.status === 'unavailable' && (
          <div className="text-sm text-gray-600">Coach unavailable.</div>
        )}
        {coach.status === 'ok' && coach.data && (
          <div className="space-y-3 text-sm">
            {/* Source badge and recommended line */}
            <div className="flex items-center gap-2">
              <span className="text-gray-500">Source:</span>
              <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-700">
                {coach.data.source}
              </span>
            </div>
            <div>
              <span className="text-gray-500 mr-1">Recommended:</span>
              <span className="font-medium capitalize">
                {coach.data.bucket.replace(/_/g, ' ')}
              </span>
            </div>
            {/* Strategy bar if provided */}
            {coach.data.strategy_bar && coach.data.strategy_bar.length > 0 && (
              <div className="space-y-1">
                <StrategyBar parts={coach.data.strategy_bar} />
                {/* Optional legend */}
                <div className="flex justify-between text-[11px] text-gray-500">
                  {coach.data.strategy_bar.map((p) => (
                    <div key={p.action} className="flex-1 text-center">
                      {p.action}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {coach.data.rationale && (
              <div className="text-xs text-gray-500">{coach.data.rationale}</div>
            )}
          </div>
        )}

        {/* Equity section (planned to map to advice.equity.* in the unified payload) */}
        {equity && (
          <div className="mt-3 border-t pt-3 space-y-2">
            {equity.loading && (
              <div className="space-y-2">
                <div className="h-4 w-32 bg-gray-100 animate-pulse rounded"></div>
                <div className="h-3 w-24 bg-gray-100 animate-pulse rounded"></div>
              </div>
            )}
            {!equity.loading && equity.status === 'ok' && equity.data && (
              <div className="space-y-2 text-sm">
                <div className="flex items-center gap-2">
                  <span className="text-gray-500">Equity:</span>
                  <span className="font-medium">
                    {(() => {
                      const hero = equity.data.players?.[0];
                      if (!hero) return '-';
                      const pct = hero.equity * 100;
                      return `${pct.toFixed(1)}%`;
                    })()}
                  </span>
                </div>
                {/* Hero equity bar */}
                {(() => {
                  const hero = equity.data.players?.[0];
                  if (!hero) return null;
                  return <HeroEquityBar equity={hero.equity} />;
                })()}
                <div className="flex items-center gap-2 text-xs">
                  <span className="inline-flex items-center rounded-full px-2 py-0.5 bg-gray-100 text-gray-700">
                    {meta?.meta?.equity.backend ?? equity.data.backend}
                  </span>
                  <span className="inline-flex items-center rounded-full px-2 py-0.5 bg-gray-100 text-gray-700">
                    {equity.data.mode}
                  </span>
                </div>
                {(() => {
                  if (equity.data.mode === 'ranges') {
                    return (
                      <div className="text-xs text-gray-500">
                        vs range ({equity.origin || 'default'})
                      </div>
                    );
                  }
                  // Postflop: indicate exact/MC and iteration count
                  if (equity.data.exact) {
                    return <div className="text-xs text-gray-500">exact</div>;
                  }
                  if (equity.data.iters) {
                    return (
                      <div className="text-xs text-gray-500">
                        MC {equity.data.iters.toLocaleString()} iters
                      </div>
                    );
                  }
                  return null;
                })()}
              </div>
            )}
            {!equity.loading && equity.status !== 'ok' && equity.status !== 'skipped' && (
              <div className="text-sm text-gray-600">
                {equity.status === 'disabled' && 'Equity disabled'}
                {equity.status === 'unsupported' && 'Equity not available here'}
                {equity.status === 'route-missing' && 'Equity route not available'}
                {equity.status === 'timeout' && 'Equity timed out (retry?)'}
                {equity.status === 'error' && 'Equity unavailable'}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default DecisionHelpOverlay;
