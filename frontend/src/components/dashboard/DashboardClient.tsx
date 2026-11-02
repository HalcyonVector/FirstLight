"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getDashboard, getBreakouts, type Breakout } from "@/lib/api";
import type { CategoryMomentum, DashboardData, RepoCard } from "@/lib/types";
import { formatStat, formatDelta } from "@/lib/utils";
import { Sparkline } from "@/components/shared/Sparkline";
import { WatchButton } from "@/components/shared/WatchButton";
import { useSparklines } from "@/hooks/useSparklines";

interface Props {
  initialData: DashboardData | null;
}

export function DashboardClient({ initialData }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["dashboard"],
    queryFn: getDashboard,
    initialData: initialData ?? undefined,
    staleTime: 5 * 60_000,
  });

  const { data: breakoutData } = useQuery({
    queryKey: ["breakouts"],
    queryFn: getBreakouts,
    staleTime: 5 * 60_000,
  });
  const breakouts = breakoutData?.breakouts ?? [];

  const lead = data?.top_gaining_week?.[0];
  const second = data?.top_gaining_week?.[1];
  const trendingNow = (data?.top_gaining_today ?? []).slice(0, 15);
  const hotToday = (data?.top_gaining_today ?? []).slice(0, 6);
  const riseWeek = (data?.top_gaining_week ?? []).slice(0, 6);
  const cats = data?.trending_categories ?? [];
  const newEntrants = data?.new_entrants ?? [];
  const aiEco = data?.ai_ecosystem ?? [];

  const totalToday = (data?.top_gaining_today ?? []).reduce((s, r) => s + r.stars_gained_today, 0);
  const totalWeek = (data?.top_gaining_week ?? []).reduce((s, r) => s + r.stars_gained_week, 0);
  const topScore = cats[0] ? Math.round(cats[0].momentum_score) : 0;

  // On a fresh DB there's no velocity yet (needs a 2nd snapshot), so gains/momentum
  // are all 0. Detect that and fall back to ranking by total stars (footprint).
  const hasVelocity = totalWeek > 0;
  const featured = Array.from(
    new Map(
      [...(data?.top_gaining_week ?? []), ...(data?.top_gaining_today ?? [])].map((r) => [r.id, r])
    ).values()
  );
  const byStars = [...featured].sort((a, b) => b.latest_stars - a.latest_stars);
  const leader = hasVelocity ? lead : byStars[0];
  const runnerUp = hasVelocity ? second : byStars[1];
  const totalStars = featured.reduce((s, r) => s + r.latest_stars, 0);

  const sparkIds = Array.from(
    new Set([...hotToday, ...riseWeek, ...trendingNow, ...byStars.slice(0, 15)].map((r) => r.id))
  );
  const sparks = useSparklines(sparkIds);

  if (isLoading && !data) return <DashboardSkeleton />;

  return (
    <div className="fade-up">
      <div className="kicker">The Big Story · This week</div>
      {leader ? (
        <>
          <h1 className="big">
            {leader.name}{" "}
            <span className="ember">
              {hasVelocity ? "is pulling the ecosystem forward." : "leads the board."}
            </span>
          </h1>
          <p className="standfirst">
            {leader.description ??
              "One of the most-watched repositories on the open-source frontier."}
          </p>

          <div className="lead">
            <div>
              {hasVelocity ? (
                <p className="drop">
                  <Link className="inl" href={`/repos/${leader.id}`}>
                    {leader.full_name}
                  </Link>{" "}
                  added {formatStat(leader.stars_gained_week)} stars in the last seven days, more
                  than any other tracked repository, for a momentum score of{" "}
                  {Math.round(leader.momentum_score)}.
                  {runnerUp && (
                    <>
                      {" "}
                      Next is{" "}
                      <Link className="inl" href={`/repos/${runnerUp.id}`}>
                        {runnerUp.full_name}
                      </Link>{" "}
                      with {formatDelta(runnerUp.stars_gained_week)}.
                    </>
                  )}
                </p>
              ) : (
                <p className="drop">
                  Velocity needs two daily snapshots, so until the next refresh the board ranks by
                  total stars, led by{" "}
                  <Link className="inl" href={`/repos/${leader.id}`}>
                    {leader.full_name}
                  </Link>{" "}
                  at {formatStat(leader.latest_stars)}.
                </p>
              )}
              <p>
                Momentum is a 0 to 100 score that blends star, fork, contributor and commit growth.
                Open any repository to see how its score is built, its star curve, and an AI-written
                analysis.
              </p>
            </div>
            <aside className="side">
              <SideList
                items={hasVelocity ? trendingNow : byStars.slice(0, 15)}
                hasVelocity={hasVelocity}
                sparks={sparks}
              />
            </aside>
          </div>

          <div className="bigstats">
            {hasVelocity ? (
              <>
                <Stat n={`+${formatStat(totalToday)}`} l="Stars today" />
                <Stat n={`+${formatStat(totalWeek)}`} l="Stars this week" ember />
                <Stat n={String(cats.length)} l="Categories" />
                <Stat n={String(newEntrants.length)} l="New entrants" />
                <Stat n={String(topScore)} l="Top momentum" ember />
                <Stat n="6h" l="Refresh" />
              </>
            ) : (
              <>
                <Stat n={formatStat(totalStars)} l="Stars tracked" ember />
                <Stat n={String(featured.length)} l="Repos indexed" />
                <Stat n={String(cats.length)} l="Categories" />
                <Stat n={String(newEntrants.length)} l="New entrants" />
                <Stat n="6h" l="Refresh" />
              </>
            )}
          </div>
        </>
      ) : (
        <EmptyState />
      )}

      <div className="rulehead">
        The Leaderboards <span className="meta">by star velocity · ▲▼ vs yesterday</span>
      </div>
      <div className="cols">
        <div>
          <div className="kicker" style={{ marginTop: 20 }}>
            Hottest Today
          </div>
          {hotToday.map((r, i) => (
            <LeaderEntry
              key={r.id}
              rank={i + 1}
              repo={r}
              metric={r.stars_gained_today}
              label="today"
              spark={sparks[String(r.id)]}
              showMove
            />
          ))}
        </div>
        <div>
          <div className="kicker" style={{ marginTop: 20 }}>
            Rising This Week
          </div>
          {riseWeek.map((r, i) => (
            <LeaderEntry
              key={r.id}
              rank={i + 1}
              repo={r}
              metric={r.stars_gained_week}
              label="week"
              spark={sparks[String(r.id)]}
            />
          ))}
        </div>
      </div>

      <div className="rulehead">
        Category Momentum <span className="meta">composite velocity · 0–100</span>
      </div>
      <div className="catgrid">
        {cats.map((c) => (
          <CategoryCard key={c.category.id} c={c} />
        ))}
      </div>

      {breakouts.length > 0 && (
        <>
          <div className="rulehead">
            Breakouts <span className="meta">new &amp; accelerating · &lt; 30d old</span>
          </div>
          <div className="cols">
            <div>
              {breakouts.slice(0, Math.ceil(breakouts.length / 2)).map((b, i) => (
                <BreakoutEntry key={b.id} rank={i + 1} b={b} />
              ))}
            </div>
            <div>
              {breakouts.slice(Math.ceil(breakouts.length / 2)).map((b, i) => (
                <BreakoutEntry
                  key={b.id}
                  rank={i + 1 + Math.ceil(breakouts.length / 2)}
                  b={b}
                />
              ))}
            </div>
          </div>
        </>
      )}

      {aiEco.length > 0 && (
        <>
          <div className="rulehead">
            AI Ecosystem <span className="meta">agents · llm · inference</span>
          </div>
          {aiEco.map((r) => (
            <Link key={r.id} className="mini" href={`/repos/${r.id}`}>
              <span className="mn">{r.full_name}</span>
              <span className="mg">{formatDelta(r.stars_gained_week)}</span>
            </Link>
          ))}
        </>
      )}

      <div className="foot">
        <div className="fb">
          GitHub Trending <span style={{ color: "var(--ember)" }}>Intelligence</span>
        </div>
        <div className="fm" suppressHydrationWarning>
          {data?.snapshot_days
            ? `${data.snapshot_days} daily snapshot${data.snapshot_days === 1 ? "" : "s"}${
                data.data_since
                  ? ` since ${new Date(data.data_since).toLocaleDateString(undefined, { month: "short", day: "numeric" })}`
                  : ""
              }${data.snapshot_days < 7 ? " · momentum still stabilizing" : ""}`
            : "Data collecting…"}
          {data?.generated_at ? ` · updated ${new Date(data.generated_at).toLocaleTimeString()}` : ""}
          {" · "}
          <Link href="/rss.xml">RSS</Link>
        </div>
      </div>
    </div>
  );
}

function Stat({ n, l, ember }: { n: string; l: string; ember?: boolean }) {
  return (
    <div>
      <div className={`n${ember ? " e" : ""}`}>{n}</div>
      <div className="l">{l}</div>
    </div>
  );
}

/** ▲3 / ▼2 / NEW compared with yesterday's rank on the daily-gain board. */
function RankMove({ rank, prev }: { rank: number; prev: number | null | undefined }) {
  if (prev === undefined) return null; // API without rank history
  if (prev === null) return <span className="move new">new</span>;
  const d = prev - rank;
  if (d === 0) return <span className="move">–</span>;
  return <span className={`move ${d > 0 ? "up" : "dn"}`}>{d > 0 ? `▲${d}` : `▼${-d}`}</span>;
}

function SideList({
  items,
  hasVelocity,
  sparks,
}: {
  items: RepoCard[];
  hasVelocity: boolean;
  sparks: Record<string, number[]>;
}) {
  const [page, setPage] = useState(0);
  const perPage = 5;
  const totalPages = Math.max(1, Math.ceil(items.length / perPage));
  const clamped = Math.min(page, totalPages - 1);
  const pageItems = items.slice(clamped * perPage, clamped * perPage + perPage);

  return (
    <>
      <div className="sidehead">
        <h3>{hasVelocity ? "Trending Now" : "Most Starred"}</h3>
        {totalPages > 1 && (
          <div className="sidenav">
            <button aria-label="Previous page" disabled={clamped <= 0} onClick={() => setPage(clamped - 1)}>
              ‹
            </button>
            <span className="pg">
              {clamped + 1}/{totalPages}
            </span>
            <button
              aria-label="Next page"
              disabled={clamped >= totalPages - 1}
              onClick={() => setPage(clamped + 1)}
            >
              ›
            </button>
          </div>
        )}
      </div>
      {pageItems.map((r, i) => {
        const rank = clamped * perPage + i + 1;
        return (
          <Link key={r.id} className="row" href={`/repos/${r.id}`}>
            <span className="n">{String(rank).padStart(2, "0")}</span>
            <div className="body">
              <div className="t">{r.name}</div>
              <div className="m">
                {r.language ?? "—"} ·{" "}
                {hasVelocity ? (
                  <>
                    <b>{Math.round(r.momentum_score)}</b> momentum ·{" "}
                    {formatDelta(r.stars_gained_today)}
                  </>
                ) : (
                  <>{formatStat(r.latest_stars)} stars</>
                )}
              </div>
            </div>
            <span className="spark">
              {(sparks[String(r.id)]?.length ?? 0) > 1 && (
                <Sparkline values={sparks[String(r.id)]} color="var(--ember)" />
              )}
            </span>
          </Link>
        );
      })}
    </>
  );
}

function LeaderEntry({
  rank,
  repo,
  metric,
  label,
  spark,
  showMove,
}: {
  rank: number;
  repo: RepoCard;
  metric: number;
  label: string;
  spark?: number[];
  showMove?: boolean;
}) {
  return (
    <Link className="lentry" href={`/repos/${repo.id}`}>
      <div className="rk">
        {rank}
        {showMove && <RankMove rank={rank} prev={repo.prev_rank} />}
      </div>
      <div>
        <div className="nm">
          {repo.name}
          {repo.language && <span className="lang">{repo.language}</span>}
        </div>
        <div className="ds">{repo.verdict ?? repo.description ?? "No description provided."}</div>
      </div>
      <div className="rt rtwatch">
        <div>
          {spark && spark.length > 1 && (
            <div style={{ marginBottom: 4 }}>
              <Sparkline values={spark} width={72} height={20} color="var(--gain)" />
            </div>
          )}
          <div className="gv" style={metric ? undefined : { color: "var(--dim2)" }}>
            {metric ? formatDelta(metric) : "—"}
          </div>
          <div className="gl">stars/{label}</div>
        </div>
        <WatchButton
          variant="icon"
          repo={{
            id: repo.id,
            full_name: repo.full_name,
            name: repo.name,
            language: repo.language,
            momentum_score: repo.momentum_score,
            stars_gained_week: repo.stars_gained_week,
          }}
        />
      </div>
    </Link>
  );
}

function BreakoutEntry({ rank, b }: { rank: number; b: Breakout }) {
  return (
    <Link className="lentry" href={`/repos/${b.id}`}>
      <div className="rk">{rank}</div>
      <div>
        <div className="nm">
          {b.name}
          {b.language && <span className="lang">{b.language}</span>}
          {b.age_days != null && <span className="badge-new">{b.age_days}d</span>}
        </div>
        <div className="ds">{b.verdict ?? b.full_name}</div>
      </div>
      <div className="rt">
        <div className="gv" style={{ color: "var(--ember)" }}>
          {Math.round(b.momentum_score)}
        </div>
        <div className="gl">momentum</div>
      </div>
    </Link>
  );
}

function CategoryCard({ c }: { c: CategoryMomentum }) {
  const status = (c.radar_status ?? "stable") as "rising" | "stable" | "declining";
  return (
    <Link className="cat" href={`/trends/${c.category.slug}`}>
      <div className="cn">{c.category.name}</div>
      <div className="cs">
        <span className={`pill ${status}`}>{status}</span>
        <span>{c.repo_count.toLocaleString()} repos</span>
      </div>
      <div className="score">{Math.round(c.momentum_score)}</div>
      <div className="sub" style={c.stars_gained_week ? undefined : { color: "var(--dim2)" }}>
        {c.stars_gained_week ? `${formatDelta(c.stars_gained_week)} stars / wk` : "— stars / wk"}
      </div>
      <div className="bar">
        <i style={{ width: `${Math.min(100, Math.round(c.momentum_score))}%` }} />
      </div>
    </Link>
  );
}

function EmptyState() {
  return (
    <div className="note" style={{ marginTop: 30 }}>
      No dashboard data yet. Once the backend has ingested trending repositories, the Big Story and
      leaderboards will populate here automatically.
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div style={{ marginTop: 40 }}>
      <div className="skel" style={{ height: 60, width: "70%", marginBottom: 16 }} />
      <div className="skel" style={{ height: 20, width: "50%", marginBottom: 40 }} />
      <div className="cols">
        {[0, 1].map((col) => (
          <div key={col}>
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="skel" style={{ height: 54, marginBottom: 12 }} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
