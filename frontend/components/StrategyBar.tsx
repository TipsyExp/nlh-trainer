// frontend/components/StrategyBar.tsx
// Simple stacked bar for visualising coach strategy distributions.
//
// Each segment corresponds to a recommended action and its share of the
// distribution.  Colours are chosen heuristically to distinguish fold
// (red), call/check (blue), raises (green) and jams (dark red).  Unknown
// actions default to grey.  The component does not display labels; the
// surrounding UI should provide context or a legend if necessary.

import React from 'react';
import type { StrategyPart } from '../types/coach';

function getColor(action: string): string {
  const a = action.toLowerCase();
  if (a === 'fold') return 'bg-red-400';
  if (a === 'call' || a === 'check') return 'bg-blue-400';
  if (a === 'jam' || a === 'all_in' || a === 'allin' || a === 'all-in') return 'bg-red-600';
  if (a.startsWith('raise')) return 'bg-green-400';
  return 'bg-gray-400';
}

export interface StrategyBarProps {
  parts: StrategyPart[];
}

export function StrategyBar({ parts }: StrategyBarProps) {
  // Normalise percentages to ensure the bar fills the full width even if the
  // total is slightly above or below 1.  Clamp each segment between 0 and 1.
  const total = parts.reduce((sum, p) => sum + (p.pct || 0), 0);
  return (
    <div className="w-full h-2 flex rounded overflow-hidden bg-gray-100">
      {parts.map((p) => {
        const w = total > 0 ? (p.pct / total) * 100 : 0;
        const width = Math.max(0, Math.min(100, w));
        return (
          <div
            key={p.action}
            className={`${getColor(p.action)} h-full`}
            style={{ width: `${width}%` }}
          />
        );
      })}
    </div>
  );
}

export default StrategyBar;