"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { getCalls, getDigest, getRadar } from "@/lib/api";
import type { DigestRepo } from "@/lib/types";
import { formatStat, formatDelta, relativeTime } from "@/lib/utils";

/** The weekly email, as a page: same sections, same data (/api/v1/digest). */
export function ThisWeekClient() {
  const { data: digest, isLoading } = useQuery({ queryKey: ["digest"], queryFn: getDigest, staleTime: 5 * 60_000 });
  const { data: radar } = useQuery({ queryKey: ["radar"], queryFn: getRadar, staleTime: 5 * 60_000 });
  const { data: calls } = useQuery({ queryKey: ["calls"], queryFn: getCalls, staleTime: 5 * 60_000, retry: false });

  const breakouts = digest?.breakouts ?? [];
  const movers = digest?.movers ?? [];
  const shipped = digest?.shipped ?? [];
  const story = breakouts[0] ?? movers[0];
  const weekAgo = Date.now() - 7 * 86_400_000;
  const newCalls = (calls?.calls ?? []).filter((c) => new Date(c.called_on).getTime() >= weekAgo);
  const rising = [...(radar?.rising ?? [])].sort((a, b) => b.change_vs_last_week - a.change_vs_last_week).slice(0, 5);
  const cooling = [...(radar?.declining ?? [])].sort((a, b) => a.change_vs_last_week - b.change_vs_last_week).slice(0, 5);

  const now = new Date();
  const range = `${new Date(weekAgo).toLocaleDateString("en-US", { month: "short", day: "numeric" })} – ${now.toLocaleDateString(
    "en-US",
    { month: "short", day: "numeric", year: "numeric" }
  )}`;

  return (
    <div className="fade-up">
      <div className="kicker" suppressHydrationWarning>
        The Weekly · {range}
      </div>
      <h1 className="big">
        This week in <span className="ember">open source.</span>
      </h1>
      <p className="standfirst">
        The same digest that goes out by email every Monday, updated live.
      </p>

      {story && (
        <Link className="bigstory" href={`/repos/${story.id}`}>
          <span className="bslabel">Big story</span>
          This week&apos;s {breakouts.length ? "breakout" : "top mover"}: <b>{story.full_name}</b>, momentum{" "}
          {Math.round(story.momentum_score)}, {formatDelta(story.stars_gained_week)} stars in 7 days.
        </Link>
      )}

      <div className="rulehead">
        Breakouts <span className="meta">new repos accelerating fast</span>
      </div>
      {isLoading ? <Skel /> : breakouts.length ? breakouts.map((r, i) => <DigestRow key={r.id} r={r} rank={i + 1} young />) : (
        <div className="note">No young repo is accelerating hard enough this week.</div>
      )}

      <div className="rulehead">
        Top movers <span className="meta">ranked by momentum</span>
      </div>
      {isLoading ? <Skel /> : movers.length ? movers.map((r, i) => <DigestRow key={r.id} r={r} rank={i + 1} />) : (
        <div className="note">No movers yet.</div>
      )}

      <div className="panelrow" style={{ marginTop: 12 }}>
        <div>
          <div className="rulehead">
            What shipped <span className="meta">releases this week</span>
          </div>
          {shipped.length ? (
            shipped.map((r) => (
              <a
                key={`${r.id}-${r.tag}`}
                className="mini"
                href={r.url ?? `https://github.com/${r.full_name}/releases`}
                target="_blank"
                rel="noopener noreferrer"
                title={r.snippet ?? undefined}
              >
                <span className="mn">{r.full_name}</span>
                <span className="reltag">{r.tag}</span>
                <span className="mg" style={{ color: "var(--dim2)", fontWeight: 400 }}>
                  {relativeTime(r.published_at)}
                </span>
              </a>
            ))
          ) : (
            <p className="emptyline">No stable releases from the top repos this week.</p>
          )}
        </div>
        <div>
          <div className="rulehead">
            New breakout calls <Link className="meta" href="/breakouts">track record →</Link>
          </div>
          {newCalls.length ? (
            newCalls.map((c) => (
              <Link key={c.id} className="mini" href={`/repos/${c.id}`}>
                <span className="mn">{c.full_name}</span>
                <span className="mg">{c.accel.toFixed(1)}× pace</span>
              </Link>
            ))
          ) : (
            <p className="emptyline">No new calls in the last 7 days.</p>
          )}
        </div>
      </div>

      <div className="panelrow" style={{ marginTop: 12 }}>
        <div>
          <div className="rulehead">
            Heating up <span className="meta">momentum ▲ week over week</span>
          </div>
          {rising.length ? (
            rising.map((c) => (
              <Link key={c.category.id} className="mini" href={`/trends/${c.category.slug}`}>
                <span className="mn">{c.category.name}</span>
                <span className="mg">{formatDelta(c.change_vs_last_week)}</span>
              </Link>
            ))
          ) : (
            <p className="emptyline">No categories heating up yet.</p>
          )}
        </div>
        <div>
          <div className="rulehead">
            Cooling down <span className="meta">momentum ▼ week over week</span>
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
            <p className="emptyline">Nothing notably cooling this week.</p>
          )}
        </div>
      </div>

      <div className="foot">
        <div className="fb">The Weekly</div>
        <div className="fm">
          &ldquo;Backed by activity&rdquo; = growth matched by commits or contributors · refreshes every 6h
        </div>
      </div>
    </div>
  );
}

function DigestRow({ r, rank, young }: { r: DigestRepo; rank: number; young?: boolean }) {
  const age = r.github_created_at ? Math.max(0, Math.floor((Date.now() - new Date(r.github_created_at).getTime()) / 86_400_000)) : null;
  return (
    <Link className="lentry" href={`/repos/${r.id}`}>
      <div className="rk">{rank}</div>
      <div>
        <div className="nm">
          {r.full_name}
          {r.language && <span className="lang">{r.language}</span>}
        </div>
        <div className="ds">{r.description ?? "No description provided."}</div>
        <div className="dtags">
          <span className={`signal ${r.backed_by_activity ? "good" : ""}`}>
            {r.backed_by_activity ? "Backed by activity" : "Star-driven"}
          </span>
          {r.category && <span className="tag">{r.category}</span>}
          {young && age != null && <span className="badge-new">{age}d old</span>}
        </div>
      </div>
      <div className="rt">
        <div className="gv">{formatDelta(r.stars_gained_week)}</div>
        <div className="gl">
          wk · {formatStat(r.latest_stars)} ★ · {Math.round(r.momentum_score)}
        </div>
      </div>
    </Link>
  );
}

function Skel() {
  return (
    <>
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="skel" style={{ height: 58, marginBottom: 10 }} />
      ))}
    </>
  );
}
