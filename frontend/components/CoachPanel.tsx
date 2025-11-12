// frontend/components/CoachPanel.tsx

import { useEffect, useMemo, useState } from "react";
import { Api } from "../lib/api";

type AdviceMeta = {
  status: "ok" | "unsupported" | "disabled" | "timeout" | "error";
  cached?: boolean;
  latency_ms?: number;
  node_key?: string | null;
};

type AdviceResponse = {
  recommended_bucket?: string;
  strategy?: Record<string, number>;
  ev_map?: Record<string, number>;
  meta: AdviceMeta;
};

type DebugEvent = {
  ts: string;
  url: string;
  status: number;
  ok: boolean;
  body: any;
};

/**
 * CoachPanel fetches and displays postflop advice for the current decision.
 *
 * When enabled, it calls the backend for advice at a given handId and
 * decision index. The panel gracefully handles scenarios where advice is
 * unavailable, unsupported, timed out, or explicitly disabled by the
 * backend (HTTP 501). In the disabled case the panel shows a
 * "Disabled" badge rather than treating the response as an error.
 */
export function CoachPanel({
  enabled,
  handId,
  idx,
  street, // optional; if present we only fetch on flop/turn/river
}: {
  enabled: boolean;
  handId?: string | null;
  idx?: number | null;
  street?: string | null;
}) {
  const [loading, setLoading] = useState(false);
  const [advice, setAdvice] = useState<AdviceResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Debug mode persisted in localStorage
  const [debugOn, setDebugOn] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem("coachDebug") === "1";
  });
  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem("coachDebug", debugOn ? "1" : "0");
    }
  }, [debugOn]);

  const [events, setEvents] = useState<DebugEvent[]>([]);

  // Track whether the coach endpoint is explicitly disabled (HTTP 501). When
  // this is true the UI shows a Disabled badge. The flag is reset when
  // subsequent requests succeed or when advice is fetched successfully.
  const [isDisabled, setIsDisabled] = useState<boolean>(false);

  const isPostflop = useMemo(() => {
    if (!street) return true; // backwards-compat: if parent doesn't pass street, don't gate
    const s = String(street).toLowerCase();
    return s === "flop" || s === "turn" || s === "river";
    // "showdown" also wouldn't fetch since idx wouldn't be meaningful
  }, [street]);

  const canFetch = enabled && !!handId && typeof idx === "number" && isPostflop;

  useEffect(() => {
    let abort = false;

    async function run() {
      if (!canFetch) {
        setAdvice(null);
        setError(null);
        setIsDisabled(false);
        return;
      }
      setLoading(true);
      setError(null);

      // Prefer raw variant so we can show status/body in debug
      const raw = await Api.getCoachAdviceRaw(String(handId), Number(idx));
      if (abort) return;

      if (debugOn) {
        setEvents((prev) =>
          [
            {
              ts: new Date().toISOString(),
              url: raw.url,
              status: raw.status,
              ok: raw.ok,
              body: raw.body,
            },
            ...prev,
          ].slice(0, 50)
        );
        // eslint-disable-next-line no-console
        console.debug("[CoachAdvice]", raw);
      }

      try {
        // If the backend reports the coach advice endpoint as disabled (HTTP 501),
        // treat this as a disabled state rather than an error. Do not set advice
        // or error; instead set the disabled flag so the UI shows the
        // appropriate badge.
        if (raw.disabled) {
          setAdvice(null);
          setError(null);
          setIsDisabled(true);
        } else if (raw.ok && raw.body?.meta?.status === "ok") {
          setAdvice(raw.body as AdviceResponse);
          setError(null);
          setIsDisabled(false);
        } else {
          const msg =
            raw.body?.meta?.status ||
            raw.body?.detail ||
            (typeof raw.body === "string" ? raw.body : "unavailable");
          setAdvice(null);
          setError(String(msg));
          setIsDisabled(false);
        }
      } finally {
        setLoading(false);
      }
    }

    run();
    return () => {
      abort = true;
    };
    // re-fetch when any of these change
  }, [canFetch, enabled, handId, idx, debugOn]);

  // Derive the current status for the coach. If the endpoint is disabled,
  // override whatever meta status might be present. Otherwise fall back
  // to the advice meta status, error state, or enabled flag.
  const status = isDisabled
    ? "disabled"
    : advice?.meta?.status ?? (error ? "error" : enabled ? "ok" : "disabled");

  // --- PRE-FLOP BADGE OVERRIDE (minor polish) ---
  // If we're preflop *and* the feature is enabled, show a neutral
  // "n/a preflop" badge instead of "On".
  type BadgeStatus =
    | "ok"
    | "disabled"
    | "unsupported"
    | "timeout"
    | "error"
    | "na_preflop";
  const badgeStatus: BadgeStatus =
    enabled && !isPostflop ? "na_preflop" : (status as BadgeStatus);
  // ----------------------------------------------

  const sortedStrategy = useMemo(() => {
    const s = advice?.strategy || {};
    return Object.entries(s).sort((a, b) => b[1] - a[1]);
  }, [advice]);

  const Badge = ({ text, color }: { text: string; color: string }) => (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${color}`}
    >
      {text}
    </span>
  );

  const badgeEl =
    badgeStatus === "ok" ? (
      <Badge text="On" color="bg-green-100 text-green-800" />
    ) : badgeStatus === "na_preflop" ? (
      <Badge text="n/a preflop" color="bg-gray-100 text-gray-700" />
    ) : badgeStatus === "disabled" ? (
      <Badge text="Disabled" color="bg-gray-100 text-gray-700" />
    ) : badgeStatus === "unsupported" ? (
      <Badge text="Unsupported" color="bg-yellow-100 text-yellow-800" />
    ) : badgeStatus === "timeout" ? (
      <Badge text="Timeout" color="bg-orange-100 text-orange-800" />
    ) : (
      <Badge text="Unavailable" color="bg-red-100 text-red-800" />
    );

  const lastEvent = events[0];

  return (
    <div className="rounded-2xl bg-white shadow p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Coach</h2>
        <div className="flex items-center gap-2">
          {/* Debug toggle */}
          <label className="flex items-center gap-1 text-xs text-gray-500 cursor-pointer select-none">
            <input
              type="checkbox"
              className="accent-black"
              checked={debugOn}
              onChange={(e) => setDebugOn(e.target.checked)}
            />
            Debug
          </label>
          {badgeEl}
        </div>
      </div>

      {!enabled && <div className="text-sm text-gray-600">Coach: off</div>}

      {enabled && !handId && (
        <div className="text-sm text-gray-600">No hand in progress.</div>
      )}

      {enabled && handId && typeof idx === "number" && !isPostflop && (
        <div className="text-sm text-gray-600">Advice n/a preflop.</div>
      )}

      {enabled && handId && typeof idx === "number" && isPostflop && (
        <>
          {loading && (
            <div className="text-sm text-gray-500">Fetching advice…</div>
          )}

          {!loading && error && (
            <div className="text-sm text-gray-600">No advice: {error}</div>
          )}

          {!loading && advice && status !== "ok" && (
            <div className="text-sm text-gray-600">No advice: {status}</div>
          )}

          {!loading && advice && status === "ok" && (
            <div className="space-y-3">
              <div className="text-sm">
                <span className="text-gray-500 mr-1">Recommended:</span>
                <span className="font-medium">
                  {advice.recommended_bucket}
                </span>
                {typeof advice.meta.latency_ms === "number" && (
                  <span className="text-xs text-gray-400 ml-2">
                    ({advice.meta.latency_ms} ms)
                  </span>
                )}
              </div>

              {/* Strategy list */}
              <div className="space-y-1">
                {sortedStrategy.map(([label, p]) => (
                  <div key={label} className="flex items-center gap-2">
                    <div className="w-24 text-xs text-gray-600">{label}</div>
                    <div className="flex-1 bg-gray-100 rounded-full h-2 overflow-hidden">
                      <div
                        className="bg-black h-2"
                        style={{
                          width: `${Math.min(100, Math.max(0, p * 100))}%`,
                        }}
                      />
                    </div>
                    <div className="w-12 text-right text-xs">
                      {(p * 100).toFixed(1)}%
                    </div>
                  </div>
                ))}
              </div>

              {/* Optional EV row */}
              {advice.ev_map && Object.keys(advice.ev_map).length > 0 && (
                <div className="pt-1 border-t">
                  <div className="text-xs text-gray-500 mb-1">EV</div>
                  <div className="grid grid-cols-2 gap-1 text-xs">
                    {Object.entries(advice.ev_map).map(([k, v]) => (
                      <div key={k} className="flex justify-between">
                        <span className="text-gray-600">{k}</span>
                        <span>{v.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="text-[11px] text-gray-400">
                Single thread, deterministic; may be slow on first solve.
              </div>
            </div>
          )}

          {/* Debug drawer */}
          {debugOn && (
            <div className="mt-2 rounded-xl border bg-gray-50">
              <div className="px-3 py-2 text-xs text-gray-600 flex items-center justify-between">
                <div className="font-medium">Debug</div>
                <div className="flex items-center gap-2">
                  <button
                    className="text-gray-700 underline"
                    onClick={() => setEvents([])}
                  >
                    Clear
                  </button>
                  {lastEvent && (
                    <button
                      className="text-gray-700 underline"
                      onClick={() => {
                        const payload = JSON.stringify(lastEvent, null, 2);
                        navigator.clipboard?.writeText(payload).catch(() => {});
                      }}
                    >
                      Copy last
                    </button>
                  )}
                </div>
              </div>
              <div className="max-h-48 overflow-auto p-3 text-[11px] font-mono text-gray-800">
                {events.length === 0 ? (
                  <div className="text-gray-500">No debug events yet.</div>
                ) : (
                  events.map((e, i) => (
                    <div key={i} className="mb-2">
                      <div className="text-gray-600">
                        [{e.ts}] {e.status} {e.ok ? "OK" : "ERR"} — {e.url}
                      </div>
                      <pre className="whitespace-pre-wrap break-words">
                        {typeof e.body === "string"
                          ? e.body
                          : JSON.stringify(e.body, null, 2)}
                      </pre>
                      <hr className="my-2 border-gray-200" />
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default CoachPanel;
