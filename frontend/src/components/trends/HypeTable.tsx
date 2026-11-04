"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { getHype } from "@/lib/api";

/** How fast each category's hyped repos fade, from every repo that had a 700+ star week. */
export function HypeTable() {
  const { data } = useQuery({ queryKey: ["hype"], queryFn: getHype, staleTime: 30 * 60_000, retry: false });
  const o = data?.overall;
  if (!o || !data?.categories.length) return null;

  return (
    <>
      <div className="rulehead">
        After the hype <span className="meta">what happens once a repo has a big week</span>
      </div>
      <p className="hypelead">
        Across {o.n} repos that had a week of 700+ stars,{" "}
        {o.fade_days != null ? (
          <>
            weekly stars typically <b>halve within {o.fade_days} days</b> of the peak
          </>
        ) : (
          "weekly stars haven't halved yet for most"
        )}
        . <b>{o.holding_pct}%</b> are still at half their best week or better
        {o.building_pct != null && (
          <>
            , and <b>{o.building_pct}%</b> kept up their commit activity
          </>
        )}
        .
      </p>
      <div className="hypetable" role="table" aria-label="Hype half-life by category">
        <div className="hyperow head" role="row">
          <span role="columnheader">Category</span>
          <span role="columnheader">Halves in</span>
          <span role="columnheader">Still holding</span>
          <span role="columnheader">Still building</span>
        </div>
        {data.categories.map((c) => (
          <Link key={c.slug} className="hyperow" role="row" href={`/trends/${c.slug}`}>
            <span role="cell">
              {c.name} <em>{c.n} repos</em>
            </span>
            <span role="cell">{c.fade_days != null ? `${c.fade_days} days` : "—"}</span>
            <span role="cell">
              <span className="mbar">
                <i style={{ width: `${c.holding_pct}%` }} />
              </span>
              {c.holding_pct}%
            </span>
            <span role="cell">{c.building_pct != null ? `${c.building_pct}%` : "—"}</span>
          </Link>
        ))}
      </div>
      <p className="sigwhy">
        Halves in: median days from a repo&apos;s best week until its weekly stars fell below half of it.
        Still holding: share at half their best week or better today. Still building: share whose weekly
        commits stayed at half their peak-week level or more (where commit data exists). Updated daily.
      </p>
    </>
  );
}
