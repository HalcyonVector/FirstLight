"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getStarChecks } from "@/lib/api";
import type { Lifecycle, StarCheck } from "@/lib/types";
import { readFollows, subscribeFollows, toggleFollow, type Follows } from "@/lib/follows";

const STAGE_HELP: Record<Lifecycle, string> = {
  breakout: "Stars this week are well above its recent weekly average",
  emerging: "Young or still small, without a clear spike",
  established: "Large and growing at its usual pace",
  fading: "Stars this week are less than half its recent weekly average",
};

/** Growth-curve stage pill. */
export function LifecycleChip({ stage }: { stage?: Lifecycle | null }) {
  if (!stage) return null;
  return (
    <span className={`stage ${stage}`} title={STAGE_HELP[stage]}>
      {stage}
    </span>
  );
}

/** Stargazer-sample verdicts for a set of repos (only the sampled ones come back). */
export function useStarChecks(ids: number[]): Record<string, StarCheck> {
  const key = [...ids].sort((a, b) => a - b).join(",");
  const { data } = useQuery({
    queryKey: ["star-checks", key],
    queryFn: () => getStarChecks(ids),
    enabled: ids.length > 0,
    staleTime: 10 * 60_000,
    retry: false,
  });
  return data?.checks ?? {};
}

/** Warning chip for repos gaining stars far faster than forks. Renders nothing otherwise. */
export function StarFlag({ check }: { check?: StarCheck }) {
  if (!check || check.verdict !== "suspicious") return null;
  const typical = check.typical_ratio > 0 ? Math.round(1 / check.typical_ratio) : null;
  return (
    <span
      className="starflag"
      title={`${check.stars_week.toLocaleString()} stars but ${check.forks_week.toLocaleString()} forks this week${
        typical ? `; fast-growing repos usually get 1 fork per ${typical} stars` : ""
      }`}
    >
      stars without forks
    </span>
  );
}

/** Odds a breakout call comes true, as a small pill. */
export function OddsChip({ prob }: { prob?: number | null }) {
  if (prob == null) return null;
  const pct = Math.round(prob * 100);
  return (
    <span className={`odds ${pct >= 50 ? "hi" : pct >= 25 ? "mid" : "lo"}`} title="Model's odds this call reaches the weekly top list within 30 days">
      {pct}% odds
    </span>
  );
}

const EXAMPLES = [
  "fastest-growing Rust databases",
  "new AI agents under 2k stars",
  "Python repos breaking out",
  "terminal tools trending today",
];

/** Plain-English question box; submits to /ask. */
export function AskBox({ initial = "", autoFocus = false }: { initial?: string; autoFocus?: boolean }) {
  const router = useRouter();
  const [q, setQ] = useState(initial);
  const [example, setExample] = useState(EXAMPLES[0]);

  useEffect(() => setQ(initial), [initial]);
  useEffect(() => {
    let i = 0;
    const t = setInterval(() => setExample(EXAMPLES[++i % EXAMPLES.length]), 3500);
    return () => clearInterval(t);
  }, []);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const text = q.trim();
    if (text.length >= 3) router.push(`/ask?q=${encodeURIComponent(text)}`);
  }

  return (
    <form className="askbox" onSubmit={submit} role="search">
      <span className="ico" aria-hidden>
        ?
      </span>
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={`Ask the data — e.g. “${example}”`}
        aria-label="Ask a question about trending repositories"
        maxLength={200}
        autoFocus={autoFocus}
      />
      <button type="submit" disabled={q.trim().length < 3}>
        Ask
      </button>
    </form>
  );
}

export function useFollows() {
  const [follows, setFollows] = useState<Follows>({ categories: [], languages: [] });
  useEffect(() => {
    setFollows(readFollows());
    return subscribeFollows(() => setFollows(readFollows()));
  }, []);
  return follows;
}

/** Chip that follows/unfollows a category or language for the For You feed. */
export function FollowChip({ kind, value, label }: { kind: keyof Follows; value: string; label?: string }) {
  const follows = useFollows();
  const on = follows[kind].includes(value);
  return (
    <button
      className={`chip ${on ? "on" : ""}`}
      aria-pressed={on}
      onClick={(e) => {
        e.preventDefault();
        toggleFollow(kind, value);
      }}
    >
      {on ? "✓ " : "+ "}
      {label ?? value}
    </button>
  );
}
