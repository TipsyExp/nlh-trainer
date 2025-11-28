// frontend/dev/SnapshotInspector.tsx
// Developer-only inspector for snapshot logging (Phase 4 / early M3).
//
// When the guidance overlay triggers advice requests and the backend is
// configured to log snapshots, these calls are persisted and surfaced
// in the export API. This component provides a simple UI to inspect
// whether the overlay made the expected calls for the current decision
// and to fetch the exported snapshots. It is gated by
// NEXT_PUBLIC_DEV_TOOLS and should not appear in production builds.
//
// Snapshot types note:
// --------------------
// Historically the backend attached three optional per-action snapshot
// fields in the JSON export:
//   - preflop_advice  (legacy preflop-only advice)
//   - coach_advice    (legacy unified AdviceV1)
//   - equity_snapshot (equity results from /api/equity)
// Newer backends may expose a single `advice_snapshot` field carrying
// the unified advice payload. This inspector tolerates both shapes and
// simply reports which fields are present for the current (hand_id, idx).

import { useEffect, useState } from 'react';
import { getOverlayTrace, subscribeOverlayTrace } from '../store/overlayDebugStore';
import { getHandExport } from '../utils/export';
import type { ExportHand } from '../types/export';
import { globalOverlayGate } from '../utils/overlayFlags';
import { useHelpOverlayToggle } from '../hooks/useHelpOverlayToggle';

/**
 * SnapshotInspector renders a small panel showing the last overlay call
 * trace and a button to fetch the export for the current hand. It
 * subscribes to overlayDebugStore updates so that changes propagate
 * automatically. Only visible when NEXT_PUBLIC_DEV_TOOLS is enabled.
 */
export default function SnapshotInspector() {
  // Gate by build-time flag; do not render if dev tools disabled.
  const devEnabled = ['1', 'true', 'yes', 'on'].includes(
    String(process.env.NEXT_PUBLIC_DEV_TOOLS || '').toLowerCase()
  );
  if (!devEnabled) return null;

  const [trace, setTrace] = useState(getOverlayTrace());
  const [exportRes, setExportRes] = useState<ExportHand | null>(null);
  const [exportErr, setExportErr] = useState<string | null>(null);
  const [loadingExport, setLoadingExport] = useState(false);

  // Subscribe to overlay trace updates.
  useEffect(() => {
    const unsub = subscribeOverlayTrace((t) => setTrace(t));
    return () => unsub();
  }, []);

  // Determine whether overlay is currently enabled.
  const { enabled: helpEnabled } = useHelpOverlayToggle(undefined);
  const overlayEnabled = globalOverlayGate && helpEnabled;

  async function onExport() {
    setExportErr(null);
    setExportRes(null);
    if (!trace.handId) {
      setExportErr('No hand ID available');
      return;
    }
    try {
      setLoadingExport(true);
      const res = await getHandExport(trace.handId);
      if (process.env.NEXT_PUBLIC_DEV_TOOLS) {
        try {
          // eslint-disable-next-line no-console
          console.debug('[SnapshotInspector] exportRes', res);
        } catch {
          /* noop */
        }
      }
      setExportRes(res);
    } catch (e: any) {
      setExportErr(e?.message || String(e));
    } finally {
      setLoadingExport(false);
    }
  }

  // Extract snapshots for current idx from export if available.
  let decisionSnapshot:
    | {
        hasUnifiedAdvice: boolean;
        hasPreflopAdvice: boolean;
        hasCoachAdvice: boolean;
        hasEquity: boolean;
      }
    | null = null;

  if (exportRes && typeof trace.idx === 'number') {
    // Prefer the canonical "actions" array, but tolerate older "decisions"
    // naming if present for transitional backends.
    const actions: any = (exportRes as any).actions ?? (exportRes as any).decisions;

    if (Array.isArray(actions)) {
      const d: any = actions.find((x: any) => x && x.idx === trace.idx);
      if (d) {
        decisionSnapshot = {
          hasUnifiedAdvice: typeof d.advice_snapshot !== 'undefined',
          hasPreflopAdvice: typeof d.preflop_advice !== 'undefined',
          hasCoachAdvice: typeof d.coach_advice !== 'undefined',
          hasEquity: typeof d.equity_snapshot !== 'undefined',
        };
      } else {
        decisionSnapshot = {
          hasUnifiedAdvice: false,
          hasPreflopAdvice: false,
          hasCoachAdvice: false,
          hasEquity: false,
        };
      }
    } else {
      // If the export structure differs from expectations, keep snapshot null.
      decisionSnapshot = null;
    }
  }

  return (
    <div
      className="fixed right-4 bottom-4 z-50 max-w-xs bg-white border border-gray-200 rounded-lg shadow p-3 text-xs space-y-2"
      style={{ fontFamily: 'monospace' }}
    >
      <div className="font-semibold">Snapshot Inspector</div>
      <div>
        <div>Overlay: {overlayEnabled ? 'ON' : 'OFF'}</div>
        <div>Hand: {trace.handId ?? 'N/A'}</div>
        <div>Idx: {trace.idx ?? 'N/A'}</div>
        <div>Street: {trace.street ?? 'N/A'}</div>
        <div>Advice called: {trace.calledAdvice ? 'Yes' : 'No'}</div>
      </div>
      <button
        onClick={onExport}
        className="w-full text-center rounded border px-2 py-1 bg-gray-100 hover:bg-gray-200 disabled:opacity-50"
        disabled={loadingExport}
      >
        {loadingExport ? 'Loading…' : 'Fetch export'}
      </button>
      {exportErr && <div className="text-red-600">{exportErr}</div>}
      {decisionSnapshot && (
        <div>
          <div>
            Unified advice snapshot (advice_snapshot):{' '}
            {decisionSnapshot.hasUnifiedAdvice ? 'Yes' : 'No'}
          </div>
          <div>
            Legacy preflop advice snapshot (preflop_advice):{' '}
            {decisionSnapshot.hasPreflopAdvice ? 'Yes' : 'No'}
          </div>
          <div>
            Legacy coach advice snapshot (coach_advice):{' '}
            {decisionSnapshot.hasCoachAdvice ? 'Yes' : 'No'}
          </div>
          <div>
            Legacy equity snapshot (equity_snapshot):{' '}
            {decisionSnapshot.hasEquity ? 'Yes' : 'No'}
          </div>
        </div>
      )}
    </div>
  );
}
