// frontend/components/review/ActionPanel.tsx
import React from "react";
import clsx from "clsx";
import type { ReviewAction } from "@/lib/types/review";

export interface ActionPanelProps {
  action?: ReviewAction | null;
  className?: string;
}

function formatChips(n?: number | null) {
  if (n == null || !isFinite(n)) return "—";
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 2,
    minimumFractionDigits: n % 1 === 0 ? 0 : 2,
  }).format(n);
}

function StreetBadge({ street }: { street?: string }) {
  if (!street) return null;
  const color =
    street === "flop"
      ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
      : street === "turn"
      ? "bg-blue-50 text-blue-700 ring-blue-200"
      : street === "river"
      ? "bg-purple-50 text-purple-700 ring-purple-200"
      : street === "preflop"
      ? "bg-amber-50 text-amber-700 ring-amber-200"
      : "bg-gray-50 text-gray-700 ring-gray-200";
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs ring-1",
        color
      )}
      title={`Street: ${street}`}
    >
      {street.toUpperCase()}
    </span>
  );
}

export default function ActionPanel({ action, className }: ActionPanelProps) {
  if (!action) {
    return (
      <div
        className={clsx(
          "rounded-2xl border border-gray-200 bg-white/60 p-4 text-sm text-gray-600",
          className
        )}
      >
        No action selected.
      </div>
    );
  }

  const { idx, street, actor, action: verb, amount, pot_after, stacks_after } = action;

  const entries =
    stacks_after && typeof stacks_after === "object"
      ? Object.entries(stacks_after)
      : [];

  return (
    <div
      className={clsx(
        "rounded-2xl border border-gray-200 bg-white/60 backdrop-blur shadow-sm",
        className
      )}
    >
      <div className="flex items-center justify-between gap-3 border-b border-gray-100 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-900">
            Action #{idx}
          </span>
          <StreetBadge street={street} />
        </div>
        <div className="text-xs text-gray-500">Details</div>
      </div>

      <div className="grid grid-cols-1 gap-4 px-4 py-4 md:grid-cols-2">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs uppercase tracking-wide text-gray-500">
              Actor
            </span>
            <span className="text-sm text-gray-900">
              {actor ?? "—"}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs uppercase tracking-wide text-gray-500">
              Action
            </span>
            <span className="text-sm text-gray-900">
              {verb}
              {amount != null && (
                <>
                  {" "}
                  <span className="text-gray-500">·</span>{" "}
                  <span title="Amount">{formatChips(amount)}</span>
                </>
              )}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs uppercase tracking-wide text-gray-500">
              Pot After
            </span>
            <span className="text-sm text-gray-900">
              {formatChips(pot_after)}
            </span>
          </div>
        </div>

        <div className="space-y-2">
          <div className="text-xs uppercase tracking-wide text-gray-500">
            Stacks After
          </div>
          {entries.length === 0 ? (
            <div className="text-sm text-gray-600">—</div>
          ) : (
            <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
              {entries.map(([name, stack]) => (
                <div
                  key={name}
                  className="flex items-center justify-between rounded-lg border border-gray-100 bg-white px-3 py-1.5 text-sm"
                >
                  <span className="text-gray-700">{name}</span>
                  <span className="tabular-nums text-gray-900">
                    {formatChips(stack as number)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
