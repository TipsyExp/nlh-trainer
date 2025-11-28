// frontend/components/CoachPanel.tsx

import { useEffect, useMemo, useState } from "react";
import { Api } from "../lib/api";

type AdviceStatus =
  | "ok"
  | "unsupported"
  | "disabled"
  | "timeout"
  | "error"
  | "not_found";

type AdviceMetaLegacy = {
  // Legacy solver-centric status
  status?: AdviceStatus;
  cached?: boolean;
  latency_ms?: number;
  node_key?: string | null;
};

type AdviceMetaV1 = {
  // AdviceV1 meta fields
  street?: string;
  n_players?: number;
  hero_seat?: number;
  source?: string;
  // Optional passthroughs if backend adds them here
  cached?: boolean;
  latency_ms?: number;
};

type AdviceMeta = AdviceMetaLegacy & AdviceMetaV1;

type StrategyBarEntry = {
  action: string;
  weight: number;
};

type AdviceResponse = {
  // Unified: may be legacy solver payload or AdviceV1
  version?: number;
  status?: AdviceStatus;
  meta: AdviceMeta;

  // Legacy solver-centric fields
  recommended_bucket?: string;
  strategy?: Record<string, number>;
  ev_map?: Record<string, number>;

  // AdviceV1 fields
  recommendation?: {
    bucket?: string;
    strategy_bar?: StrategyBarEntry[];
  };
  equity?: any;
  thresholds?: any;
  rationale?: string;
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

  // Track whether the coach endpoint is explicitly disabled (HTTP 501).
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
        // treat this as a disabled state rather than an error.
        if (raw.disabled) {
          setAdvice(null);
          setError(null);
          setIsDisabled(true);
        } else if (raw.ok && raw.body) {
          const body = raw.body as AdviceResponse;
          // AdviceV1: status is top-level; legacy: status is under meta.status.
          const bodyStatus: AdviceStatus | undefined =
            body.status ?? body.meta?.status;

          if (bodyStatus === "ok") {
            setAdvice(body);
            setError(null);
            setIsDisabled(false);
          } else {
            const msg =
              bodyStatus ||
              (body as any).detail ||
              (typeof body === "string" ? body : "unavailable");
            setAdvice(null);
            setError(String(msg));
            setIsDisabled(false);
          }
        } else {
          const msg =
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

  // Derive the current status for the coach.
  const status: AdviceStatus | "unavailable" = isDisabled
    ? "disabled"
    : advice?.status ??
      advice?.meta?.status ??
      (error ? "error" : enabled ? "ok" : "disabled");

  // --- PRE-FLOP BADGE OVERRIDE (minor polish) ---
  type BadgeStatus =
    | "ok"
    | "disabled"
    | "unsupported"
    | "timeout"
    | "error"
    | "not_found"
    | "na_preflop"
    | "unavailable";
  const badgeStatus: BadgeStatus =
    enabled && !isPostflop ? "na_preflop" : (status as BadgeStatus);
  // ----------------------------------------------

  const sortedStrategy = useMemo(() => {
    if (!advice) return [];

    // Legacy solver payload: strategy is a map action -> weight.
    if (advice.strategy && typeof advice.strategy === "object") {
      return Object.entries(advice.strategy).sort((a, b) => b[1] - a[1]);
    }

    // AdviceV1: recommendation.strategy_bar is an array of { action, weight }.
    const bar = advice.recommendation?.strategy_bar;
    if (Array.isArray(bar)) {
      const strat: Record<string, number> = {};
      for (const part of bar) {
        if (!part) continue;
        const action = String(part.action);
        const weight = Number(part.weight ?? 0);
        strat[action] = weight;
      }
      return Object.entries(strat).sort((a, b) => b[1] - a[1]);
    }

    return [];
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
    ) : badgeStatus === "error" ? (
      <Badge text="Unavailable" color="bg-red-100 text-red-800" />
    ) : badgeStatus === "not_found" ? (
      <Badge text="Not found" color="bg-yellow-100 text-yellow-800" />
    ) : (
      <Badge text="Unavailable" color="bg-red-100 text-red-800" />
    );

  const lastEvent = events[0];

  // Normalised source badge (solver vs equity vs chart vs coach)
  let sourceBadge: JSX.Element | null = null;
  if (advice && advice.meta) {
    const raw = (advice.meta.source || "").toString().toLowerCase();
    if (raw) {
      let label = advice.meta.source as string;
      let color = "bg-gray-100 text-gray-700";
      if (raw.includes("solver") || raw.includes("texas")) {
        label = "Solver";
        color = "bg-indigo-100 text-indigo-800";
      } else if (raw.includes("equity")) {
        label = "Equity";
        color = "bg-emerald-100 text-emerald-800";
      } else if (raw.includes("chart") || raw.includes("preflop")) {
        label = "Chart";
        color = "bg-blue-100 text-blue-800";
      } else {
        // leave backend-provided label but with neutral styling
        label = advice.meta.source as string;
      }
      sourceBadge = <Badge text={label} color={color} />;
    } else if (status === "ok") {
      // Generic coach when we don't know the exact engine
      sourceBadge = <Badge text="Coach" color="bg-gray-100 text-gray-700" />;
    }
  }

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

          {!loading && advice && status !== "ok" && !error && (
            <div className="text-sm text-gray-600">No advice: {status}</div>
          )}

          {!loading && advice && status === "ok" && (
            <div className="space-y-3">
              {/* Source badge row */}
              {sourceBadge && (
                <div className="text-xs text-gray-500 flex items-center gap-2">
                  <span>Source:</span>
                  {sourceBadge}
                </div>
              )}

              <div className="text-sm">
                <span className="text-gray-500 mr-1">Recommended:</span>
                <span className="font-medium">
                  {advice.recommended_bucket ??
                    advice.recommendation?.bucket ??
                    "—"}
                </span>
                {typeof advice.meta.latency_ms === "number" && (
                  <span className="text-xs text-gray-400 ml-2">
                    ({advice.meta.latency_ms} ms)
                  </span>
                )}
              </div>

              {/* Strategy list */}
              <div className="space-y-1">
                {sortedStrategy.map(([label, p]) => {
                  const weight = Number(p);
                  const frac = Number.isFinite(weight) ? weight : 0;
                  const pct = Math.min(100, Math.max(0, frac * 100));
                  return (
                    <div key={label} className="flex items-center gap-2">
                      <div className="w-24 text-xs text-gray-600 truncate">
                        {label}
                      </div>
                      <div className="flex-1 bg-gray-100 rounded-full h-2 overflow-hidden">
                        <div
                          className="bg-black h-2"
                          style={{
                            width: `${pct}%`,
                          }}
                        />
                      </div>
                      <div className="w-12 text-right text-xs">
                        {pct.toFixed(1)}%
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Optional EV row */}
              {advice.ev_map && Object.keys(advice.ev_map).length > 0 && (
                <div className="pt-1 border-t">
                  <div className="text-xs text-gray-500 mb-1">EV</div>
                  <div className="grid grid-cols-2 gap-1 text-xs">
                    {Object.entries(advice.ev_map).map(([k, v]) => (
                      <div key={k} className="flex justify-between">
                        <span className="text-gray-600">{k}</span>
                        <span>{Number(v).toFixed(2)}</span>
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
                        navigator.clipboard
                          ?.writeText(payload)
                          .catch(() => {});
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
