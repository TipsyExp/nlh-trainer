// frontend/components/StrategyBar.tsx
// Simple stacked bar for visualising coach strategy distributions.
//
// Each segment corresponds to a recommended action and its share of the
// distribution. Colours are chosen heuristically to distinguish fold
// (red), call/check (blue), raises (green) and jams (dark red). Unknown
// actions default to grey. The component does not display labels; the
// surrounding UI should provide context or a legend if necessary.

import React from 'react';

/**
 * Lightweight, shape-compatible strategy part.
 *
 * This component is designed to work with:
 *  - legacy CoachAdvice.strategy_bar entries ({ action, pct })
 *  - unified AdviceV1.recommendation.strategy_bar entries ({ action, weight })
 */
type StrategyPartLike = {
  action: string;
  pct?: number;
  weight?: number;
};

function getColor(action: string): string {
  const a = action.toLowerCase();
  if (a === 'fold') return 'bg-red-400';
  if (a === 'call' || a === 'check') return 'bg-blue-400';
  if (a === 'jam' || a === 'all_in' || a === 'allin' || a === 'all-in') return 'bg-red-600';
  if (a.startsWith('raise')) return 'bg-green-400';
  return 'bg-gray-400';
}

export interface StrategyBarProps {
  parts: StrategyPartLike[];
}

export function StrategyBar({ parts }: StrategyBarProps) {
  // Normalise values to ensure the bar fills the full width even if the
  // total is slightly above or below 1. We accept either `pct` or `weight`
  // and treat them as fractions in [0,1].
  const values = parts.map((p) => {
    if (typeof p.pct === 'number') return Math.max(0, p.pct);
    if (typeof p.weight === 'number') return Math.max(0, p.weight);
    return 0;
  });
  const total = values.reduce((sum, v) => sum + v, 0) || 1;

  return (
    <div className="w-full h-2 flex rounded overflow-hidden bg-gray-100">
      {parts.map((p, idx) => {
        const raw = values[idx] / total;
        const width = Math.max(0, Math.min(100, raw * 100));
        return (
          <div
            key={`${p.action}-${idx}`}
            className={`${getColor(p.action)} h-full`}
            style={{ width: `${width}%` }}
          />
        );
      })}
    </div>
  );
}

export default StrategyBar;
