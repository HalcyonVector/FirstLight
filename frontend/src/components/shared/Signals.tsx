"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import type { Lifecycle } from "@/lib/types";
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
