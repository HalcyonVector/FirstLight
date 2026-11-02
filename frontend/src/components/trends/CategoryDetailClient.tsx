"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { getCategoryTrend } from "@/lib/api";
import type { TrendSnapshot } from "@/lib/types";
import { formatStat, formatDelta } from "@/lib/utils";

export function CategoryDetailClient({ slug }: { slug: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["category-trend", slug],
    queryFn: () => getCategoryTrend(slug, "30d"),
    staleTime: 5 * 60_000,
    retry: false,
  });

  if (isLoading) {
    return (
      <div style={{ marginTop: 40 }}>
        <div className="skel" style={{ height: 52, width: "50%", marginBottom: 16 }} />
        <div className="skel" style={{ height: 220, marginBottom: 20 }} />
      </div>
    );
  }
  if (isError || !data) {
    return (
      <div className="fade-up">
        <Link className="crumb" href="/trends" style={{ display: "inline-block", marginTop: 34 }}>
          ← Trends
        </Link>
        <div className="note">Category not found, or the backend is unavailable.</div>
      </div>
    );
  }

  const status = (data.radar_status ?? "stable") as "rising" | "stable" | "declining";
  const snaps = data.snapshots ?? [];

  return (
    <div className="fade-up">
      <Link className="crumb" href="/trends" style={{ display: "inline-block", marginTop: 34 }}>
        ← Trends
      </Link>
      <div className="kicker">Category · 30-day window</div>
      <h1 className="big">
        {data.category.name}
        <span className="ember">.</span>
      </h1>

      <div className="metrics" style={{ marginTop: 24 }}>
        <div className="mc">
          <div className="mv e">{Math.round(data.current_momentum)}</div>
          <div className="md">Momentum</div>
        </div>
        <div className="mc">
          <div className="mv">
            <span className={`pill ${status}`}>{status}</span>
          </div>
          <div className="md">Radar status</div>
        </div>
        <div className="mc">
          <div className="mv">{(data.top_repos?.length ?? 0).toString()}</div>
          <div className="md">Top repos</div>
        </div>
        <div className="mc">
          <div className="mv">{snaps.length.toString()}</div>
          <div className="md">Snapshots</div>
        </div>
      </div>

      <div className="chartcard" style={{ marginTop: 26 }}>
        <h4>
          Momentum over time <span>{snaps.length ? `${snaps.length} snapshots` : "no history yet"}</span>
        </h4>
        {snaps.length > 1 ? (
          <SnapshotChart snapshots={snaps} />
        ) : (
          <div className="note" style={{ margin: 0 }}>
            Trend history appears once a few daily snapshots accumulate.
          </div>
        )}
      </div>

      <div className="rulehead">
        Top Repositories <span className="meta">by momentum</span>
      </div>
      <div>
        {(data.top_repos ?? []).map((r, i) => (
          <Link key={r.id} className="lentry" href={`/repos/${r.id}`}>
            <div className="rk">{i + 1}</div>
            <div>
              <div className="nm">
                {r.full_name}
                {r.language && <span className="lang">{r.language}</span>}
              </div>
              <div className="ds">{r.description ?? "No description provided."}</div>
            </div>
            <div className="rt">
              <div className="gv">{formatDelta(r.stars_gained_week)}</div>
              <div className="gl">stars/wk · {Math.round(r.momentum_score)}</div>
            </div>
          </Link>
        ))}
      </div>

      <div className="foot">
        <div className="fb">{data.category.name}</div>
        <div className="fm">
          {formatStat(data.top_repos?.length ?? 0)} repositories in category ·{" "}
          <a href={`/rss.xml?category=${data.category.slug}`}>RSS feed</a>
        </div>
      </div>
    </div>
  );
}

function SnapshotChart({ snapshots }: { snapshots: TrendSnapshot[] }) {
  const w = 640;
  const h = 220;
  const pad = 10;
  const vals = snapshots.map((s) => s.momentum_score);
  const mx = Math.max(...vals, 100);
  const mn = Math.min(...vals, 0);
  const range = mx - mn || 1;
  const X = (i: number) => pad + (i / (snapshots.length - 1)) * (w - pad * 2);
  const Y = (v: number) => h - pad - ((v - mn) / range) * (h - pad * 2);
  const line = vals.map((v, i) => `${i ? "L" : "M"}${X(i).toFixed(1)} ${Y(v).toFixed(1)}`).join(" ");
  const area = `${line} L${X(vals.length - 1).toFixed(1)} ${h} L${X(0).toFixed(1)} ${h} Z`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: "auto" }}>
      <defs>
        <linearGradient id="catGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="var(--ember)" stopOpacity="0.32" />
          <stop offset="1" stopColor="var(--ember)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#catGrad)" />
      <path
        d={line}
        fill="none"
        stroke="var(--ember)"
        strokeWidth="2"
        strokeLinejoin="round"
        style={{ strokeDasharray: 3000, strokeDashoffset: 3000, animation: "draw 1.6s var(--ease) forwards" }}
      />
      <circle cx={X(vals.length - 1).toFixed(1)} cy={Y(vals[vals.length - 1]).toFixed(1)} r="4" fill="var(--ember)" />
    </svg>
  );
}
