// frontend/dev/SnapshotInspector.tsx
import { useEffect, useState } from 'react';
import { getOverlayTrace, subscribeOverlayTrace } from '../store/overlayDebugStore';
import { getHandExport } from '../utils/export';
import type { ExportHand } from '../types/export';
import { globalOverlayGate } from '../utils/overlayFlags';
import { useHelpOverlayToggle } from '../hooks/useHelpOverlayToggle';

export default function SnapshotInspector() {
  const devEnabled = ['1', 'true', 'yes', 'on'].includes(
    String(process.env.NEXT_PUBLIC_DEV_TOOLS || '').toLowerCase()
  );

  const [trace, setTrace] = useState(getOverlayTrace());
  const [exportRes, setExportRes] = useState<ExportHand | null>(null);
  const [exportErr, setExportErr] = useState<string | null>(null);
  const [loadingExport, setLoadingExport] = useState(false);

  useEffect(() => {
    const unsub = subscribeOverlayTrace((t) => setTrace(t));
    return () => unsub();
  }, []);

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
      setExportRes(res);
    } catch (e: any) {
      setExportErr(e?.message || String(e));
    } finally {
      setLoadingExport(false);
    }
  }

  let decisionSnapshot: { hasAdvice: boolean; hasEquity: boolean } | null = null;
  if (exportRes && typeof trace.idx === 'number') {
    const d = exportRes.decisions.find((x) => x.idx === trace.idx);
    decisionSnapshot = d
      ? { hasAdvice: typeof d.preflop_advice !== 'undefined', hasEquity: typeof d.equity_snapshot !== 'undefined' }
      : { hasAdvice: false, hasEquity: false };
  }

  if (!devEnabled) return null; // ← after hooks

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
        <div>Coach called: {trace.calledCoach ? 'Yes' : 'No'}</div>
        <div>Equity called: {trace.calledEquity ? 'Yes' : 'No'}</div>
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
          <div>Advice snapshot: {decisionSnapshot.hasAdvice ? 'Yes' : 'No'}</div>
          <div>Equity snapshot: {decisionSnapshot.hasEquity ? 'Yes' : 'No'}</div>
        </div>
      )}
    </div>
  );
}
