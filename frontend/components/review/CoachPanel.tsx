// frontend/components/review/CoachPanel.tsx
import React from "react";
import type { AdviceSnapshot } from "@/lib/types/review";
import { StrategyBar } from "../common/StrategyBar";

type Props = {
  advice?: AdviceSnapshot;
  cached?: boolean;
  latencyMs?: number;
  nodeKey?: string;
  className?: string;
};

export default function CoachPanel({
  advice,
  cached,
  latencyMs,
  nodeKey,
  className,
}: Props) {
  if (!advice) {
    return (
      <div
        className={[
          "rounded-2xl border border-gray-200 p-4 text-sm text-gray-500 shadow-sm",
          className || "",
        ].join(" ")}
      >
        <div className="font-medium text-gray-700">Coach</div>
        <div className="mt-1 text-gray-500">n/a</div>
      </div>
    );
  }

  const top = advice.recommended_bucket ?? "";
  const strategy = advice.strategy ?? {};
  const evMap = advice.ev_map ?? {};
  const meta = advice.meta ?? {};

  // Prefer payload meta, fall back to props
  const nk: string | undefined = (meta.node_key ?? nodeKey) ?? undefined; // coerce null → undefined
  const cachedFlag = meta.cached ?? cached;
  const latency = meta.latency_ms ?? latencyMs;

  return (
    <div
      className={[
        "rounded-2xl border border-gray-200 p-4 shadow-sm",
        className || "",
      ].join(" ")}
    >
      <div className="flex items-center justify-between">
        <div className="font-semibold text-gray-800">Coach</div>
        <div className="text-xs text-gray-500">
          {nk ? `node: ${nk.slice(0, 12)}` : "node: -"}
          {cachedFlag !== undefined && (
            <>
              {" "}
              • cached: {String(Boolean(cachedFlag))}
            </>
          )}
          {latency !== undefined && (
            <>
              {" "}
              • {typeof latency === "number" ? latency.toFixed(1) : latency} ms
            </>
          )}
        </div>
      </div>

      <div className="mt-2 text-sm">
        <div className="text-gray-600">
          Top bucket:{" "}
          <span className="rounded-full bg-blue-50 px-2 py-0.5 text-blue-700">
            {top || "-"}
          </span>
        </div>
      </div>

      <div className="mt-3">
        <StrategyBar data={strategy} />
      </div>

      <div className="mt-3">
        <div className="text-xs font-medium text-gray-600">EV Δ (by action)</div>
        {Object.keys(evMap).length === 0 ? (
          <div className="mt-1 text-xs text-gray-500">No EV map.</div>
        ) : (
          <div className="mt-1 grid grid-cols-2 gap-2">
            {Object.entries(evMap).map(([k, v]) => (
              <div
                key={k}
                className="flex items-center justify-between rounded-lg bg-gray-50 px-2 py-1 text-xs"
              >
                <span className="text-gray-600">{k}</span>
                <span className={v >= 0 ? "text-green-600" : "text-red-600"}>
                  {v >= 0 ? "+" : ""}
                  {v.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
