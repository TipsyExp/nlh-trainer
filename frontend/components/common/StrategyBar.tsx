// frontend/components/common/StrategyBar.tsx
import React from "react";
import clsx from "clsx";

type Size = "xs" | "sm" | "md" | "lg";

export type StrategyMap = Record<string, number>;

export interface StrategyEntry {
  key: string;
  /** Probability in [0,1] or percentage in [0,100]; normalized if needed */
  p: number;
  /** Optional label override for legend */
  label?: string;
  /** Optional Tailwind color classes (e.g., "bg-blue-500") */
  color?: string;
  /** Optional tooltip/title per slice */
  title?: string;
}

export interface StrategyBarProps {
  /** Either a map {action: weight} or pre-shaped entries */
  data: StrategyMap | StrategyEntry[];
  /** Normalize values to sum=1 (default: true) */
  normalize?: boolean;
  /** Number of decimal places for percentages (default: 0) */
  precision?: number;
  /** Show legend under the bar (default: true) */
  showLegend?: boolean;
  /** Height preset for the bar */
  size?: Size;
  /** Additional classes for outer wrapper */
  className?: string;
  /** Accessible label for the whole bar */
  ariaLabel?: string;
  /** Sort order for legend and bar stacking (default: "desc" by p) */
  order?: "none" | "asc" | "desc";
}

/* ---------- helpers ---------- */

const sizeHeights: Record<Size, string> = {
  xs: "h-2",
  sm: "h-3",
  md: "h-4",
  lg: "h-5",
};

const defaultPalette = [
  "bg-blue-500",
  "bg-emerald-500",
  "bg-amber-500",
  "bg-rose-500",
  "bg-violet-500",
  "bg-sky-500",
  "bg-cyan-500",
  "bg-fuchsia-500",
];

function stableIndex(key: string, mod: number): number {
  // Simple deterministic hash for color picking
  let h = 2166136261 >>> 0;
  for (let i = 0; i < key.length; i++) {
    h ^= key.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h % mod;
}

function pickColor(key: string, i: number) {
  // Prefer classic poker action colors when we can recognize the key
  const k = key.toLowerCase();

  if (k.includes("fold")) return "bg-rose-500";
  if (k.includes("check")) return "bg-gray-400";
  if (k.includes("call")) return "bg-emerald-500";

  // Detect overbets: explicit "overbet" or % labels > 100%
  const pctMatch = k.match(/(\d+(?:\.\d+)?)%/);
  const pct = pctMatch ? parseFloat(pctMatch[1]) : null;
  if (k.includes("overbet") || (pct !== null && pct > 100)) {
    return "bg-amber-600";
  }

  if (k.includes("bet") || k.includes("%")) return "bg-blue-500";
  if (k.includes("raise")) return "bg-violet-500";

  return defaultPalette[i % defaultPalette.length];
}

function toEntries(data: StrategyMap | StrategyEntry[]): StrategyEntry[] {
  if (Array.isArray(data)) {
    return data.map((e, i) => ({
      key: e.key,
      p: e.p,
      label: e.label ?? e.key,
      color: e.color ?? pickColor(e.key, i),
      title: e.title,
    }));
  }
  const keys = Object.keys(data);
  return keys.map((k, i) => ({
    key: k,
    p: data[k]!,
    label: k,
    color: pickColor(k, stableIndex(k, defaultPalette.length)),
  }));
}

function normalizeWeights(entries: StrategyEntry[]): StrategyEntry[] {
  const sum = entries.reduce(
    (acc, e) => acc + (isFinite(e.p) ? Math.max(0, e.p) : 0),
    0
  );
  if (sum <= 0) {
    // Avoid division by zero; evenly distribute
    const even = entries.length > 0 ? 1 / entries.length : 0;
    return entries.map((e) => ({ ...e, p: even }));
  }
  // If any value looks like a percentage > 1, convert to fraction first
  const hasPct = entries.some((e) => e.p > 1.00001);
  const denom = hasPct ? 100 : sum;
  return entries.map((e) => ({
    ...e,
    p: Math.max(0, e.p) / denom,
  }));
}

function formatPct(p: number, precision: number) {
  return `${(p * 100).toFixed(precision)}%`;
}

/* ---------- component ---------- */

export function StrategyBar({
  data,
  normalize = true,
  precision = 0,
  showLegend = true,
  size = "md",
  className,
  ariaLabel = "Strategy distribution",
  order = "desc",
}: StrategyBarProps) {
  let entries = toEntries(data);

  entries = normalize ? normalizeWeights(entries) : entries;

  if (order !== "none") {
    entries = [...entries].sort((a, b) =>
      order === "asc" ? a.p - b.p : b.p - a.p
    );
  }

  // Guard tiny residuals to ensure 100% fill; last slice absorbs rounding
  const pct = entries.map((e) => Math.max(0, e.p));
  const sum = pct.reduce((a, b) => a + b, 0) || 1;
  const pct100 = pct.map((p) => (p / sum) * 100);
  const rounded = pct100.map((p) => Math.max(0, p));
  const deficit = 100 - rounded.reduce((a, b) => a + b, 0);
  if (rounded.length > 0) {
    rounded[rounded.length - 1] += deficit;
  }

  return (
    <div className={clsx("w-full", className)}>
      <div
        role="img"
        aria-label={ariaLabel}
        className={clsx(
          "w-full overflow-hidden rounded-lg ring-1 ring-gray-200 bg-gray-100",
          sizeHeights[size]
        )}
        title={entries
          .map((e) => `${e.label ?? e.key}: ${formatPct(e.p, precision)}`)
          .join(" • ")}
      >
        <div className="flex w-full h-full">
          {entries.map((e, i) => (
            <div
              key={e.key}
              className={clsx("h-full", e.color || pickColor(e.key, i))}
              style={{ width: `${Math.max(0, rounded[i] || 0)}%` }}
              title={
                e.title ??
                `${e.label ?? e.key} — ${formatPct(e.p, precision)}`
              }
            />
          ))}
        </div>
      </div>

      {showLegend && (
        <div className="mt-2 grid grid-cols-1 gap-1 sm:grid-cols-2">
          {entries.map((e, i) => (
            <div
              key={`legend-${e.key}`}
              className="flex items-center gap-2 text-sm text-gray-700"
            >
              <span
                className={clsx(
                  "inline-block h-3 w-3 rounded-sm ring-1 ring-gray-300",
                  e.color || pickColor(e.key, i)
                )}
                aria-hidden
              />
              <span className="truncate">{e.label ?? e.key}</span>
              <span className="ml-auto tabular-nums text-gray-600">
                {formatPct(e.p, precision)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
