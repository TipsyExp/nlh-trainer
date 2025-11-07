// frontend/pages/review/[hand_id].tsx
import { useEffect, useMemo, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";

import { getReviewHand } from "@/lib/api/review";
import type {
  GetReviewHandResponse,
  ReviewAction,
  AdviceSnapshot,
  BoardState,
} from "@/lib/types/review";

import HandSummary from "@/components/review/HandSummary";
import ActionStepper from "@/components/review/ActionStepper";
import ActionPanel from "@/components/review/ActionPanel";
import BoardPanel from "@/components/review/BoardPanel";
import CoachPanel from "@/components/review/CoachPanel";

function flattenBoard(board?: BoardState): string[] | null {
  if (!board) return null;
  const out: string[] = [];

  // Flop may be an array of 3 cards or a single string (normalize both)
  if (Array.isArray(board.flop)) {
    out.push(...board.flop);
  } else if (board.flop) {
    out.push(board.flop as unknown as string);
  }

  // Turn may be a single string or an array (normalize)
  if (Array.isArray(board.turn)) {
    out.push(...board.turn);
  } else if (board.turn) {
    out.push(board.turn as unknown as string);
  }

  // River may be a single string or an array (normalize)
  if (Array.isArray(board.river)) {
    out.push(...board.river);
  } else if (board.river) {
    out.push(board.river as unknown as string);
  }

  return out.length ? out : null;
}

export default function ReviewHandDetailPage() {
  const router = useRouter();
  const q = router.query.hand_id;
  const handId = typeof q === "string" ? q : Array.isArray(q) ? q[0] : undefined;

  const [detail, setDetail] = useState<GetReviewHandResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [idx, setIdx] = useState<number>(0);

  // Fetch detail (only when we definitely have a string handId)
  useEffect(() => {
    if (typeof handId !== "string") return;

    let canceled = false;
    async function load(h: string) {
      setLoading(true);
      setError(null);
      try {
        const data = await getReviewHand(h);
        if (!canceled) {
          setDetail(data);
          setIdx(0);
        }
      } catch (e: any) {
        if (!canceled) setError(e?.message || "Failed to load hand");
      } finally {
        if (!canceled) setLoading(false);
      }
    }
    load(handId);
    return () => {
      canceled = true;
    };
  }, [handId]);

  const actions: ReviewAction[] = useMemo(
    () => detail?.actions ?? [],
    [detail]
  );
  const currentAction: ReviewAction | null =
    actions.length > 0 ? actions[idx] : null;

  const adviceForIdx: AdviceSnapshot | null = useMemo(() => {
    const m = detail?.advice_by_idx || {};
    if (!m) return null;
    return (m as any)[idx] ?? (m as any)[String(idx)] ?? null;
  }, [detail, idx]);

  const hasAdvice =
    !!detail?.advice_by_idx && Object.keys(detail.advice_by_idx).length > 0;

  const flatBoard = flattenBoard(detail?.board);

  return (
    <>
      <Head>
        <title>Hand {handId || ""} | Review | NLH Trainer</title>
      </Head>

      <main className="mx-auto max-w-6xl px-4 py-6">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold text-gray-900">Hand Review</h1>
            {handId ? <span className="text-sm text-gray-500">ID: {handId}</span> : null}
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/review"
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
            >
              ← Back to list
            </Link>
          </div>
        </div>

        {loading ? (
          <div className="rounded-lg border border-gray-200 bg-white p-6 text-sm text-gray-600">
            Loading…
          </div>
        ) : error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        ) : !detail ? (
          <div className="rounded-lg border border-gray-200 bg-white p-6 text-sm text-gray-600">
            Not found.
          </div>
        ) : (
          <>
            {/* Summary */}
            <div className="mb-4">
              <HandSummary
                summary={detail.summary}
                handId={detail.hand_id}
                actionsCount={actions.length}
                hasAdvice={hasAdvice}
              />
            </div>

            {/* Stepper */}
            <div className="mb-4">
              <ActionStepper
                index={idx}
                total={actions.length}
                onStep={(nextIndex: number) =>
                  setIdx(
                    Math.max(0, Math.min(Math.max(0, actions.length - 1), nextIndex))
                  )
                }
              />
            </div>

            {/* Panels */}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <ActionPanel action={currentAction} />
              <BoardPanel board={flatBoard ?? undefined} />
              <CoachPanel advice={adviceForIdx ?? undefined} />
            </div>
          </>
        )}
      </main>
    </>
  );
}
