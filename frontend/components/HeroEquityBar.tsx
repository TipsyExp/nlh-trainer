// frontend/components/HeroEquityBar.tsx
// Compact bar to visualise hero equity.
//
// Displays a horizontal bar where the blue portion corresponds to the
// hero's equity and the grey portion corresponds to the remainder.
// The component is intentionally minimal to avoid cluttering the
// guidance overlay. It can be driven either by the standalone equity
// endpoint (EquityResponse.players[hero].equity) or by the unified
// Advice payload (advice.equity.hero_vs_villain_equity).

import React from 'react';

export interface HeroEquityBarProps {
  /** Hero equity as a decimal between 0 and 1. */
  equity: number;
}

export function HeroEquityBar({ equity }: HeroEquityBarProps) {
  const pct = Math.max(0, Math.min(1, equity));
  return (
    <div className="w-full h-2 rounded overflow-hidden bg-gray-200">
      <div
        className="h-full bg-blue-400"
        style={{ width: `${(pct * 100).toFixed(1)}%` }}
      />
    </div>
  );
}

export default HeroEquityBar;
