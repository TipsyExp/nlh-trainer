// frontend/components/DecisionHelpOverlay.tsx
// Presentational overlay for hand guidance (unified advice payload).
//
// This component renders a fixed panel on the right side of the screen (or
// bottom on small screens) and displays coach advice (charts / solver) plus
// optional equity annotations for the current decision. All network logic is
// handled by hooks; this component only consumes the normalised state
// returned by `useDecisionOverlay` and renders it.

import React from 'react';
import type { DecisionContext } from '../types/decision';
import type { AdvicePayloadV1 } from '../types/advice';
import { StrategyBar } from './StrategyBar';
import { StatusChip } from './StatusChip';
import { HeroEquityBar } from './HeroEquityBar';

export interface DecisionHelpOverlayProps {
  /** Optional decision context (not used yet, reserved for future extensions). */
  decision?: DecisionContext | null;
  /** Normalised advice state from useDecisionOverlay. */
  advice: {
    data: AdvicePayloadV1 | null;
    loading: boolean;
    status: 'ok' | 'loading' | 'disabled' | 'not_found' | 'unavailable';
    error?: string;
  };
}

export function DecisionHelpOverlay({ decision, advice }: DecisionHelpOverlayProps) {
  const payload = advice.data ?? null;

  const recommendation = payload?.recommendation ?? null;
  const equity = payload?.equity ?? null;
  const thresholds = payload?.thresholds ?? null;
  const ctx = payload?.context ?? null;
  const meta = payload?.meta ?? null;

  // Compute a simple label for the source badge.
  // For now we just surface meta.source (e.g. "equity", "solver", "chart").
  const sourceLabel = meta?.source || (payload ? 'coach' : '—');

  // Strategy parts: prefer backend strategy_bar; fall back to action_mix
  const strategyParts =
    recommendation && recommendation.strategy_bar && recommendation.strategy_bar.length > 0
      ? recommendation.strategy_bar
          .map((p) => ({
            action: p.action,
            weight: typeof p.weight === 'number' ? p.weight : Number(p.weight),
          }))
          .filter((p) => p.weight > 0)
      : recommendation && recommendation.action_mix
      ? Object.entries(recommendation.action_mix)
          .map(([action, weight]) => ({
            action,
            weight: typeof weight === 'number' ? weight : Number(weight),
          }))
          .filter((p) => p.weight > 0)
      : [];

  // Primary action: prefer bucket; fall back to primary_action if present.
  const primaryAction =
    recommendation?.bucket ?? recommendation?.primary_action ?? null;

  // Equity + thresholds
  const heroEquity =
    typeof equity?.hero === 'number' ? equity.hero : null;

  const potOdds =
    typeof thresholds?.pot_odds === 'number' ? thresholds.pot_odds : null;

  const minEqToCall =
    typeof thresholds?.min_equity_to_call === 'number'
      ? thresholds.min_equity_to_call
      : null;

  const equityComment =
    (equity?.comment ?? thresholds?.ev_hint ?? payload?.rationale) || null;

  return (
    <div
      role="region"
      aria-label="Guidance"
      className="fixed z-40 right-4 top-4 md:right-4 md:top-4 max-w-[90vw] w-80 md:w-96"
    >
      <div className="bg-white shadow-lg rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Guidance</h2>
          {/* Status badge summarises the current advice state */}
          <StatusChip status={advice.status} />
        </div>

        {/* Advice section */}
        {advice.status === 'loading' && (
          <div className="space-y-2">
            <div className="h-4 w-32 bg-gray-100 animate-pulse rounded" />
            <div className="h-3 w-24 bg-gray-100 animate-pulse rounded" />
          </div>
        )}

        {advice.status === 'disabled' && (
          <div className="text-sm text-gray-600">
            Advice disabled or not configured.
          </div>
        )}

        {advice.status === 'not_found' && (
          <div className="text-sm text-gray-600">
            Advice route not available.
          </div>
        )}

        {advice.status === 'unavailable' && (
          <div className="text-sm text-gray-600">
            Advice unavailable.
          </div>
        )}

        {advice.status === 'ok' && payload && (
          <div className="space-y-3 text-sm">
            {/* Source badge and recommended line */}
            <div className="flex items-center gap-2">
              <span className="text-gray-500">Source:</span>
              <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-700">
                {sourceLabel}
              </span>
            </div>

            {ctx && (
              <div className="text-xs text-gray-500 flex flex-wrap gap-x-2 gap-y-1">
                <span className="uppercase">
                  {(ctx.street ?? meta?.street ?? 'unknown')}{' '}
                  · {(ctx.hero_position ?? 'unknown')}
                </span>
                {typeof ctx.to_call === 'number' && (
                  <span>To call: {ctx.to_call}</span>
                )}
                {typeof ctx.pot_size === 'number' && (
                  <span>Pot: {ctx.pot_size}</span>
                )}
              </div>
            )}

            <div>
              <span className="text-gray-500 mr-1">Recommended:</span>
              <span className="font-medium capitalize">
                {primaryAction
                  ? primaryAction.replace(/_/g, ' ')
                  : '—'}
              </span>
            </div>

            {/* Strategy bar if we have a mix */}
            {strategyParts.length > 0 && (
              <div className="space-y-1">
                <StrategyBar parts={strategyParts} />
                <div className="flex justify-between text-[11px] text-gray-500">
                  {strategyParts.map((p) => (
                    <div key={p.action} className="flex-1 text-center">
                      {p.action}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Optional comment / rationale */}
            {equityComment && (
              <div className="text-xs text-gray-500">{equityComment}</div>
            )}
          </div>
        )}

        {/* Equity / thresholds block */}
        {payload && (
          <div className="mt-3 border-t pt-3 space-y-2">
            {advice.status === 'loading' && (
              <div className="space-y-2">
                <div className="h-4 w-32 bg-gray-100 animate-pulse rounded" />
                <div className="h-3 w-24 bg-gray-100 animate-pulse rounded" />
              </div>
            )}

            {advice.status === 'ok' && (
              <div className="space-y-2 text-sm">
                {/* Hero equity */}
                {heroEquity !== null && (
                  <>
                    <div className="flex items-center gap-2">
                      <span className="text-gray-500">
                        Equity vs villain:
                      </span>
                      <span className="font-medium">
                        {(heroEquity * 100).toFixed(1)}%
                      </span>
                    </div>
                    <HeroEquityBar equity={heroEquity} />
                  </>
                )}

                {/* Pot odds / min equity to call */}
                {(potOdds !== null || minEqToCall !== null) && (
                  <div className="flex flex-col gap-1 text-xs text-gray-500">
                    {potOdds !== null && (
                      <span>
                        Pot odds:{' '}
                        {(potOdds * 100).toFixed(1)}%
                      </span>
                    )}
                    {minEqToCall !== null && (
                      <span>
                        Min equity to call:{' '}
                        {(minEqToCall * 100).toFixed(1)}%
                      </span>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default DecisionHelpOverlay;
