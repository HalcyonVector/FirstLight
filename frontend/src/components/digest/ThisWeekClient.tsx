"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { getDashboard, getRadar } from "@/lib/api";
import { formatStat, formatDelta } from "@/lib/utils";

export function ThisWeekClient() {
  const { data: dash } = useQuery({ queryKey: ["dashboard"], queryFn: getDashboard, staleTime: 5 * 60_000 });
  const { data: radar } = useQuery({ queryKey: ["radar"], queryFn: getRadar, staleTime: 5 * 60_000 });

  const movers = (dash?.top_gaining_week ?? []).slice(0, 6);
  const newcomers = dash?.new_entrants ?? [];
  const rising = [...(radar?.rising ?? [])]
    .sort((a, b) => b.change_vs_last_week - a.change_vs_last_week)
    .slice(0, 5);
  const cooling = [...(radar?.declining ?? [])]
    .sort((a, b) => a.change_vs_last_week - b.change_vs_last_week)
    .slice(0, 5);
  const totalWeek = (dash?.top_gaining_week ?? []).reduce((s, r) => s + r.stars_gained_week, 0);
  const topMover = movers[0];
  const topRising = rising[0];

  const dateLabel = new Date().toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  });

  return (
    <div className="fade-up">
      <div className="kicker" suppressHydrationWarning>
        The Weekly · {dateLabel}
      </div>
      <h1 className="big">
        This week in <span className="ember">open source.</span>
      </h1>
      {topMover ? (
        <p className="standfirst">
          The board added {formatStat(totalWeek)} stars over the last seven days. {topMover.name} led
          the climb
          {topRising ? `, and ${topRising.category.name} was the fastest-heating category` : ""}.
          Here is the recap.
        </p>
      ) : (
        <p className="standfirst">
          The weekly recap fills in once there is velocity data. Run an ingest cycle (or the seed) to
          populate it.
        </p>
      )}

      <div className="rulehead">
        The Big Movers <span className="meta">by weekly star velocity</span>
      </div>
      {movers.length ? (
        movers.map((r, i) => (
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
        ))
      ) : (
        <div className="note">No movers yet.</div>
      )}

      <div className="panelrow" style={{ marginTop: 12 }}>
        <div>
          <div className="rulehead">
            New Entrants <span className="meta">first seen this week</span>
          </div>
          {newcomers.length ? (
            newcomers.map((r) => (
              <Link key={r.id} className="mini" href={`/repos/${r.id}`}>
                <span className="mn">{r.full_name}</span>
                <span className="badge-new">new</span>
                <span className="mg">{formatDelta(r.stars_gained_week)}</span>
              </Link>
            ))
          ) : (
            <div className="note" style={{ margin: 0 }}>
              No new entrants recorded yet.
            </div>
          )}
        </div>
        <div>
          <div className="rulehead">
            Heating Up <span className="meta">momentum ▲ wow</span>
          </div>
          {rising.length ? (
            rising.map((c) => (
              <Link key={c.category.id} className="mini" href={`/trends/${c.category.slug}`}>
                <span className="mn">{c.category.name}</span>
                <span className="mg">{formatDelta(c.change_vs_last_week)}</span>
              </Link>
            ))
          ) : (
            <div className="note" style={{ margin: 0 }}>
              No categories heating up yet.
            </div>
          )}
        </div>
      </div>

      <div className="rulehead">
        Cooling Down <span className="meta">momentum ▼ wow</span>
      </div>
      {cooling.length ? (
        cooling.map((c) => (
          <Link key={c.category.id} className="mini" href={`/trends/${c.category.slug}`}>
            <span className="mn">{c.category.name}</span>
            <span className="mg" style={{ color: "var(--loss)" }}>
              {formatDelta(c.change_vs_last_week)}
            </span>
          </Link>
        ))
      ) : (
        <div className="note">Nothing notably cooling this week.</div>
      )}

      <div className="foot">
        <div className="fb">The Weekly</div>
        <div className="fm">Generated from live data · refreshes every 6h</div>
      </div>
    </div>
  );
}
