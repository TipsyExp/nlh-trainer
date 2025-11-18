// frontend/components/StatusChip.tsx
// Small badge component to indicate overlay status.
//
// Used by the guidance overlay to summarise the current state of the
// preflop coach integration.  Each status maps to a colour and a short
// label.  Unknown statuses fall back to a neutral grey.

import React from 'react';

export type OverlayStatus =
  | 'loading'
  | 'ok'
  | 'disabled'
  | 'not_found'
  | 'unavailable';

const STATUS_MAP: Record<OverlayStatus, { text: string; cls: string }> = {
  loading: { text: 'Loading', cls: 'bg-gray-100 text-gray-600' },
  ok: { text: 'Ready', cls: 'bg-green-100 text-green-800' },
  disabled: { text: 'Disabled', cls: 'bg-gray-100 text-gray-600' },
  not_found: { text: 'Unavailable', cls: 'bg-yellow-100 text-yellow-800' },
  unavailable: { text: 'Unavailable', cls: 'bg-red-100 text-red-800' },
};

export interface StatusChipProps {
  status: OverlayStatus;
}

export function StatusChip({ status }: StatusChipProps) {
  const def = STATUS_MAP[status] || STATUS_MAP.unavailable;
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${def.cls}`}
    >
      {def.text}
    </span>
  );
}

export default StatusChip;