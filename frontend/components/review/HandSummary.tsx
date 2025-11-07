// frontend/components/review/HandSummary.tsx
import React from "react";
import clsx from "clsx";
import type { HandSummary as HandSummaryType } from "@/lib/types/review";

export interface HandSummaryProps {
  summary: HandSummaryType;
  handId?: string;
  actionsCount?: number;
  hasAdvice?: boolean;
  className?: string;
}

function formatDateTime(iso?: string | null) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    const y = d.getFullYear();
    const m = `${d.getMonth() + 1}`.padStart(2, "0");
    const day = `${d.getDate()}`.padStart(2, "0");
    const hh = `${d.getHours()}`.padStart(2, "0");
    const mm = `${d.getMinutes()}`.padStart(2, "0");
    return `${y}-${m}-${day} ${hh}:${mm}`;
  } catch {
    return iso;
  }
}

function formatChips(n?: number | null) {
  if (n == null || !isFinite(n)) return "—";
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 2,
    minimumFractionDigits: n % 1 === 0 ? 0 : 2,
  }).format(n);
}

export default function HandSummary({
  summary,
  handId,
  actionsCount,
  hasAdvice,
  className,
}: HandSummaryProps) {
  const { finished_at, seats, final_pot, winners } = summary;

  return (
    <div
      className={clsx(
        "w-full rounded-2xl border border-gray-200 bg-white/60 backdrop-blur px-4 py-3 shadow-sm",
        className
      )}
    >
      <div className="flex flex-wrap items-center gap-3">
        {handId ? (
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-500">Hand</span>
            <code className="rounded bg-gray-100 px-2 py-0.5 text-sm text-gray-800">
              {handId}
            </code>
            <button
              type="button"
              onClick={() => {
                navigator.clipboard?.writeText(handId).catch(() => {});
              }}
              className="text-xs text-blue-600 hover:underline"
              aria-label="Copy hand id"
              title="Copy hand id"
            >
              Copy
            </button>
          </div>
        ) : (
          <div className="text-sm font-medium text-gray-700">Hand Summary</div>
        )}

        <div className="ml-auto flex items-center gap-2">
          {typeof actionsCount === "number" && (
            <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-0.5 text-xs text-gray-700">
              <span className="h-1.5 w-1.5 rounded-full bg-gray-400" />
              {actionsCount} actions
            </span>
          )}
          {typeof hasAdvice === "boolean" && (
            <span
              className={clsx(
                "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs",
                hasAdvice
                  ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                  : "bg-gray-50 text-gray-600 ring-1 ring-gray-200"
              )}
              title={
                hasAdvice
                  ? "At least one decision has coach advice"
                  : "No advice snapshots"
              }
            >
              <span
                className={clsx(
                  "h-1.5 w-1.5 rounded-full",
                  hasAdvice ? "bg-emerald-500" : "bg-gray-400"
                )}
              />
              {hasAdvice ? "Advice available" : "Advice n/a"}
            </span>
          )}
        </div>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-4">
        <div className="flex flex-col">
          <span className="text-xs uppercase tracking-wide text-gray-500">
            Finished
          </span>
          <span className="text-sm text-gray-900">
            {formatDateTime(finished_at)}
          </span>
        </div>

        <div className="flex flex-col">
          <span className="text-xs uppercase tracking-wide text-gray-500">
            Seats
          </span>
          <span className="text-sm text-gray-900">{seats ?? "—"}</span>
        </div>

        <div className="flex flex-col">
          <span className="text-xs uppercase tracking-wide text-gray-500">
            Final Pot
          </span>
          <span className="text-sm text-gray-900">{formatChips(final_pot)}</span>
        </div>

        <div className="flex flex-col sm:col-span-2 lg:col-span-1 sm:col-start-3 lg:col-start-auto">
          <span className="text-xs uppercase tracking-wide text-gray-500">
            Winners
          </span>
          {winners && winners.length > 0 ? (
            <div className="mt-1 flex flex-wrap gap-1">
              {winners.map((w) => (
                <span
                  key={w}
                  className="inline-flex items-center rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700"
                >
                  {w}
                </span>
              ))}
            </div>
          ) : (
            <span className="text-sm text-gray-900">—</span>
          )}
        </div>
      </div>
    </div>
  );
}
