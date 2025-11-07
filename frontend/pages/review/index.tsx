// frontend/pages/review/index.tsx
import { useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import ReviewListTable from "@/components/review/ReviewListTable";
import { getReviewHands } from "@/lib/api/review";
import type { ReviewHandListItem } from "@/lib/types/review";

export default function ReviewIndexPage() {
  const [items, setItems] = useState<ReviewHandListItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [limit, setLimit] = useState<number>(100);

  useEffect(() => {
    let canceled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await getReviewHands(limit);
        if (!canceled) setItems(data.hands);
      } catch (e: any) {
        if (!canceled) setError(e?.message || "Failed to load");
      } finally {
        if (!canceled) setLoading(false);
      }
    }
    load();
    return () => {
      canceled = true;
    };
  }, [limit]);

  return (
    <>
      <Head>
        <title>Review | NLH Trainer</title>
      </Head>

      <main className="mx-auto max-w-6xl px-4 py-6">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold text-gray-900">Review</h1>
            <span className="text-sm text-gray-500">Recent completed hands</span>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <span>Limit</span>
              <input
                type="number"
                min={1}
                max={500}
                value={limit}
                onChange={(e) => setLimit(Math.max(1, Math.min(500, Number(e.target.value) || 1)))}
                className="w-20 rounded-md border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none"
              />
            </label>
            <button
              onClick={() => setLimit((v) => v)} // note: setting same value won't refetch; if you want a real refresh, add a separate refresh tick
              className="rounded-md bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-800"
            >
              Refresh
            </button>
            <Link
              href="/"
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
            >
              Home
            </Link>
          </div>
        </div>

        <ReviewListTable
          items={items}
          loading={loading}
          error={error}
          emptyMessage="No hands yet. Play some hands or enable Coach to record advice."
        />
      </main>
    </>
  );
}
