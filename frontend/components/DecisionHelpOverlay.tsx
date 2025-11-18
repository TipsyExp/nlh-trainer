// frontend/components/DecisionHelpOverlay.tsx
// Presentational overlay for hand guidance (Phase 2).
//
// This component renders a fixed panel on the right side of the screen (or
// bottom on small screens). It is *purely presentational* and does not
// perform any network calls. The parent page is responsible for fetching
// coach data (via useDecisionOverlay) and passing it in.
//
// Props:
//  - decision: optional decision context (unused for now; kept for future phases)
//  - coach: normalized coach state { data, loading, status, error? }

import React from 'react';
import type { DecisionContext } from '../types/decision';
import type { CoachAdvice } from '../types/coach';
import { StrategyBar } from './StrategyBar';
import { StatusChip } from './StatusChip';

export interface DecisionHelpOverlayProps {
  decision?: DecisionContext | null;
  coach: {
    data: CoachAdvice | null;
    loading: boolean;
    status: 'ok' | 'loading' | 'disabled' | 'not_found' | 'unavailable';
    error?: string;
  };
}

export function DecisionHelpOverlay({ decision, coach }: DecisionHelpOverlayProps) {
  // Note: `decision` is currently unused in this presentational shell.
  // It remains as a prop to keep the interface stable for future phases.

  return (
    <div
      role="region"
      aria-label="Guidance"
      className="fixed z-40 right-4 top-4 md:right-4 md:top-4 max-w-[90vw] w-80 md:w-96"
    >
      <div className="bg-white shadow-lg rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Guidance</h2>
          <StatusChip status={coach.status} />
        </div>

        {/* Main content area depends on coach status */}
        {coach.status === 'loading' && (
          <div className="text-sm text-gray-600">Loading preflop advice…</div>
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
      </div>
    </div>
  );
}

export default DecisionHelpOverlay;
