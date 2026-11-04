"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { getRadar } from "@/lib/api";
import type { RadarCategory } from "@/lib/types";
import { formatDelta } from "@/lib/utils";
import { HypeTable } from "./HypeTable";

type Status = "rising" | "stable" | "declining";

/** List / Radar switch shared by /trends and /radar (one nav tab, two views). */
export function TrendsViewTabs({ active }: { active: "list" | "radar" }) {
  return (
    <div className="filters" style={{ marginTop: 18 }}>
      <Link className={`chip ${active === "list" ? "on" : ""}`} href="/trends">
        Rankings
      </Link>
      <Link className={`chip ${active === "radar" ? "on" : ""}`} href="/radar">
        Radar
      </Link>
    </div>
  );
}

export function TrendsClient() {
  const { data, isLoading } = useQuery({ queryKey: ["radar"], queryFn: getRadar, staleTime: 5 * 60_000 });

  // The backend already buckets each category; keep its status rather than re-deriving one.
  const all: (RadarCategory & { status: Status })[] = data
    ? [
        ...data.rising.map((c) => ({ ...c, status: "rising" as const })),
        ...data.stable.map((c) => ({ ...c, status: "stable" as const })),
        ...data.declining.map((c) => ({ ...c, status: "declining" as const })),
      ].sort((a, b) => b.momentum_score - a.momentum_score)
    : [];

  return (
    <div className="fade-up">
      <div className="kicker">Trend Discovery · 7-day window</div>
      <h1 className="big">
        Where the <span className="ember">gravity</span> is moving.
      </h1>
      <p className="standfirst">
        Every technology category, ranked by composite momentum — star, fork, contributor and commit
        velocity, log-normalized into a single 0–100 signal.
      </p>
      <TrendsViewTabs active="list" />

      <div className="rulehead">
        Category Rankings <span className="meta">momentum · Δ vs last week</span>
      </div>

      {isLoading && !data ? (
        <TrendsSkeleton />
      ) : all.length ? (
        <div>
          {all.map((c, i) => {
            const delta = c.change_vs_last_week;
            return (
              <Link key={c.category.id} className="trendrow" href={`/trends/${c.category.slug}`}>
                <div className="idx">{String(i + 1).padStart(2, "0")}</div>
                <div>
                  <div className="tn">{c.category.name}</div>
                  <div className="td">
                    {c.repo_count.toLocaleString()} repos · {formatDelta(c.stars_gained_week)} stars this week
                  </div>
                </div>
                <div className="tspark" style={{ display: "flex", alignItems: "center" }}>
                  <div className="mbar">
                    <i style={{ width: `${Math.min(100, c.momentum_score)}%` }} />
                  </div>
                </div>
                <div className="tsc">
                  <div className="v">{Math.round(c.momentum_score)}</div>
                  <div className={`d ${delta >= 0 ? "up" : "dn"}`}>
                    {delta > 0 ? "▲ +" : delta < 0 ? "▼ " : "— "}
                    {Math.abs(delta).toFixed(1)} wow · {c.status}
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      ) : (
        <div className="note">No trend data yet — categories appear once snapshots are computed.</div>
      )}

      <HypeTable />

      <div className="foot">
        <div className="fb">{all.length} categories</div>
        <div className="fm">Click a category for its history and top repositories</div>
      </div>
    </div>
  );
}

function TrendsSkeleton() {
  return (
    <div style={{ marginTop: 12 }}>
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="skel" style={{ height: 66, marginBottom: 8 }} />
      ))}
    </div>
  );
}
