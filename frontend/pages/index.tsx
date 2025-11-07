// frontend/pages/index.tsx
import { useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import { Api } from "../lib/api";

export default function SettingsPage() {
  const router = useRouter();
  const [seats, setSeats] = useState(2);
  const [sb, setSb] = useState(50);
  const [bb, setBb] = useState(100);
  const [ante, setAnte] = useState(0);
  const [stacks, setStacks] = useState("10000,10000");
  const [seed, setSeed] = useState("T08");
  const [humanSeat, setHumanSeat] = useState(0);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const stacksArr = stacks
        .split(",")
        .map((s) => parseInt(s.trim(), 10))
        .filter((n) => !Number.isNaN(n));

      await Api.startSession({
        seats,
        sb,
        bb,
        ante,
        stacks: stacksArr,
        base_seed: seed,
        human_seat: humanSeat,
      });

      // Persist human seat for UI convenience
      if (typeof window !== "undefined") {
        localStorage.setItem("humanSeat", String(humanSeat));
      }

      setMsg("Session created! Redirecting to Table…");
      router.push("/table");
    } catch (err: any) {
      setMsg(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-6 bg-gray-50">
      <div className="w-full max-w-2xl rounded-2xl bg-white shadow p-6 space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">NLH Trainer — Settings</h1>
          <Link
            href="/review"
            className="rounded-xl border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
          >
            Review Hands
          </Link>
        </div>

        <form onSubmit={onSubmit} className="grid grid-cols-2 gap-4">
          <label className="col-span-1">
            <span className="block text-sm font-medium text-gray-700">Seats</span>
            <input
              type="number"
              min={2}
              max={9}
              className="mt-1 w-full rounded-lg border p-2"
              value={seats}
              onChange={(e) => setSeats(parseInt(e.target.value, 10))}
            />
          </label>

          <label className="col-span-1">
            <span className="block text-sm font-medium text-gray-700">Human Seat</span>
            <input
              type="number"
              min={0}
              className="mt-1 w-full rounded-lg border p-2"
              value={humanSeat}
              onChange={(e) => setHumanSeat(parseInt(e.target.value, 10))}
            />
          </label>

          <label>
            <span className="block text-sm font-medium text-gray-700">SB</span>
            <input
              type="number"
              className="mt-1 w-full rounded-lg border p-2"
              value={sb}
              onChange={(e) => setSb(parseInt(e.target.value, 10))}
            />
          </label>

          <label>
            <span className="block text-sm font-medium text-gray-700">BB</span>
            <input
              type="number"
              className="mt-1 w-full rounded-lg border p-2"
              value={bb}
              onChange={(e) => setBb(parseInt(e.target.value, 10))}
            />
          </label>

          <label>
            <span className="block text-sm font-medium text-gray-700">Ante</span>
            <input
              type="number"
              className="mt-1 w-full rounded-lg border p-2"
              value={ante}
              onChange={(e) => setAnte(parseInt(e.target.value, 10))}
            />
          </label>

          <label className="col-span-2">
            <span className="block text-sm font-medium text-gray-700">Stacks (comma-sep)</span>
            <input
              type="text"
              className="mt-1 w-full rounded-lg border p-2"
              value={stacks}
              onChange={(e) => setStacks(e.target.value)}
            />
          </label>

          <label className="col-span-2">
            <span className="block text-sm font-medium text-gray-700">Base Seed</span>
            <input
              type="text"
              className="mt-1 w-full rounded-lg border p-2"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
            />
          </label>

          <div className="col-span-2 flex gap-3 items-center">
            <button
              type="submit"
              disabled={busy}
              className="rounded-xl bg-black text-white px-4 py-2 disabled:opacity-50"
            >
              {busy ? "Creating…" : "Create Session"}
            </button>
            {msg && <div className="text-sm text-gray-600">{msg}</div>}
          </div>
        </form>
      </div>
    </main>
  );
}
