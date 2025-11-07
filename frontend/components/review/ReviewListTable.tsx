// frontend/components/review/ReviewListTable.tsx
import React from "react";
import clsx from "clsx";
import Link from "next/link";
import type { ReviewHandListItem } from "@/lib/types/review";

export interface ReviewListTableProps {
  items: ReviewHandListItem[];
  loading?: boolean;
  error?: string | null;
  className?: string;
  /** Message to display when items is empty (and not loading) */
  emptyMessage?: string;
  /** Optional row click override; defaults to linking to /review/[hand_id] */
  onRowClick?: (handId: string) => void;
}

export default function ReviewListTable({
  items,
  loading = false,
  error = null,
  className,
  emptyMessage = "No hands yet.",
  onRowClick,
}: ReviewListTableProps) {
  return (
    <div
      className={clsx(
        "w-full overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm",
        className
      )}
    >
      <div className="border-b border-gray-200 px-4 py-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-gray-800">Recent Hands</h2>
          {loading ? (
            <span className="text-xs text-gray-500">Loading…</span>
          ) : (
            <span className="text-xs text-gray-500">{items.length} listed</span>
          )}
        </div>
      </div>

      {error ? (
        <div className="p-4 text-sm text-red-600">Failed to load: {error}</div>
      ) : items.length === 0 && !loading ? (
        <div className="p-6 text-sm text-gray-600">{emptyMessage}</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full border-separate border-spacing-0">
            <thead>
              <tr className="bg-gray-50 text-left text-xs uppercase tracking-wider text-gray-600">
                <Th>Hand</Th>
                <Th>Finished</Th>
                <Th className="text-right">Seats</Th>
                <Th className="text-right">Final Pot</Th>
                <Th>Winners</Th>
                <Th className="text-right">Actions</Th>
                <Th className="text-center">Advice?</Th>
              </tr>
            </thead>
            <tbody>
              {loading
                ? Array.from({ length: 6 }).map((_, i) => <SkeletonRow key={`sk-${i}`} />)
                : items.map((it) => (
                    <Row
                      key={it.hand_id}
                      item={it}
                      onClick={() => {
                        if (onRowClick) onRowClick(it.hand_id);
                        else window.location.href = `/review/${encodeURIComponent(it.hand_id)}`;
                      }}
                    />
                  ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Th({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <th
      className={clsx(
        "sticky top-0 z-10 border-b border-gray-200 px-4 py-3 text-xs font-semibold",
        className
      )}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <td className={clsx("px-4 py-3 text-sm text-gray-800", className)}>{children}</td>
  );
}

function Row({ item, onClick }: { item: ReviewHandListItem; onClick?: () => void }) {
  const href = `/review/${encodeURIComponent(item.hand_id)}`;
  const winners = formatWinners(item.winners);
  const finished = item.finished_at ? formatWhen(item.finished_at) : "—";

  return (
    <tr
      className={clsx(
        "group cursor-pointer border-t border-gray-100 hover:bg-gray-50"
      )}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={(e) => {
        if (!onClick) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
    >
      <Td className="font-mono">
        {/* Keep an actual link in the first cell for middle-click/open-in-new-tab */}
        <Link
          href={href}
          className="rounded bg-gray-100 px-1.5 py-0.5 text-gray-700 underline-offset-2 hover:underline"
          onClick={(e) => e.stopPropagation()}
        >
          {item.hand_id}
        </Link>
      </Td>
      <Td className="text-gray-600">{finished}</Td>
      <Td className="text-right tabular-nums">{item.seats}</Td>
      <Td className="text-right tabular-nums">{formatChipsNullable(item.final_pot)}</Td>
      <Td className="max-w-[320px] truncate text-gray-700">{winners || "—"}</Td>
      <Td className="text-right tabular-nums">{item.action_count}</Td>
      <Td className="text-center">
        {item.has_advice ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700 ring-1 ring-inset ring-green-200">
            ✓ yes
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-full bg-gray-50 px-2 py-0.5 text-xs font-medium text-gray-600 ring-1 ring-inset ring-gray-200">
            — no
          </span>
        )}
      </Td>
    </tr>
  );
}

function SkeletonRow() {
  return (
    <tr className="border-t border-gray-100">
      {Array.from({ length: 7 }).map((_, i) => (
        <Td key={i}>
          <div className="h-4 w-full animate-pulse rounded bg-gray-200/70" />
        </Td>
      ))}
    </tr>
  );
}

function formatWhen(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "2-digit",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatChipsNullable(v?: number | null): string {
  if (v == null || !isFinite(v)) return "—";
  return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function formatWinners(ws: ReviewHandListItem["winners"]): string {
  if (!ws || ws.length === 0) return "";
  return ws.join(", ");
}
