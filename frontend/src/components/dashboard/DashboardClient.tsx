"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { getCalls, getDashboard, getDigest, getRepository, getRepositoryMetrics } from "@/lib/api";
import type { CategoryMomentum, DashboardData, RepoCard } from "@/lib/types";
import { formatStat, formatDelta, relativeTime } from "@/lib/utils";
import { WatchButton } from "@/components/shared/WatchButton";
import { AreaChart, shortDate } from "@/components/shared/Charts";
import { AskBox, LifecycleChip } from "@/components/shared/Signals";
import { releaseMarkers } from "@/lib/markers";

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

  const week = data?.top_gaining_week ?? [];
  const today = data?.top_gaining_today ?? [];
  const hasVelocity = week.some((r) => r.stars_gained_week > 0);
  // Before there is any velocity (fresh database), lead with the biggest repo instead.
  const ranked = hasVelocity ? week : [...week].sort((a, b) => b.latest_stars - a.latest_stars);
  const lead = ranked[0];
  const tier2 = ranked.slice(1, 4);
  const cats = data?.trending_categories ?? [];
  const aiEco = data?.ai_ecosystem ?? [];

  if (isLoading && !data) return <DashboardSkeleton />;

  return (
    <div className="fade-up">
      <AskBox />

      {lead ? (
        <section className="front">
          <LeadStory repo={lead} hasVelocity={hasVelocity} />
          <aside className="side frontside">
            <div className="sidehead">
              <h3>Hottest today</h3>
              <span className="pg">▲▼ vs yesterday</span>
            </div>
            {today.slice(0, 8).map((r, i) => (
              <LeaderEntry key={r.id} rank={i + 1} repo={r} />
            ))}
          </aside>
        </section>
      ) : (
        <EmptyState />
      )}

      {tier2.length > 0 && (
        <>
          <div className="rulehead">
            Also rising this week <span className="meta">by stars gained</span>
          </div>
          <div className="tier2">
            {tier2.map((r, i) => (
              <Story key={r.id} repo={r} rank={i + 2} />
            ))}
          </div>
        </>
      )}

      <div className="cols">
        <CallsBox />
        <ShippedBox />
      </div>

      <div className="rulehead">
        Category Momentum <span className="meta">composite velocity · 0–100</span>
      </div>
      <div className="catgrid">
        {cats.map((c) => (
          <CategoryCard key={c.category.id} c={c} />
        ))}
      </div>

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
              }`
            : "Data collecting…"}
          {data?.generated_at ? ` · updated ${new Date(data.generated_at).toLocaleTimeString()}` : ""}
          {" · "}
          <Link href="/rss.xml">RSS</Link>
        </div>
      </div>
    </div>
  );
}

/** The front-page lead: biggest mover of the week, written up from its AI analysis. */
function LeadStory({ repo, hasVelocity }: { repo: RepoCard; hasVelocity: boolean }) {
  const { data: detail } = useQuery({
    queryKey: ["repo", repo.id],
    queryFn: () => getRepository(repo.id),
    staleTime: 5 * 60_000,
    retry: false,
  });
  const { data: metrics } = useQuery({
    queryKey: ["repo-metrics", repo.id, "30d"],
    queryFn: () => getRepositoryMetrics(repo.id, "30d"),
    staleTime: 5 * 60_000,
    retry: false,
  });
  const insight = detail?.latest_insight;
  const daily = metrics?.daily ?? [];

  return (
    <article className="leadstory">
      <div className="kicker" style={{ marginTop: 26 }}>
        Lead story · {hasVelocity ? "this week's biggest mover" : "most starred"}
      </div>
      <h1 className="big">
        <Link href={`/repos/${repo.id}`}>{repo.name}</Link>{" "}
        <span className="ember">
          {hasVelocity ? `adds ${formatStat(repo.stars_gained_week)} stars in a week.` : "leads the board."}
        </span>
      </h1>
      <p className="standfirst">{repo.description ?? "No description provided."}</p>
      <div className="byline">
        <LifecycleChip stage={detail?.lifecycle} />
        <span>{repo.full_name}</span>
        {repo.language && <span>{repo.language}</span>}
        <span>momentum {Math.round(repo.momentum_score)}</span>
        <span>{formatStat(repo.latest_stars)} stars</span>
      </div>
      {daily.length > 2 && (
        <div className="leadchart">
          <AreaChart
            values={daily.map((d) => d.stars_total)}
            labels={daily.map((d) => shortDate(d.date))}
            markers={releaseMarkers(daily, detail?.releases ?? [])}
            height={140}
          />
        </div>
      )}
      <p className="drop">
        {insight?.why_growing ??
          (hasVelocity
            ? `${repo.full_name} gained ${formatStat(repo.stars_gained_week)} stars in the last seven days, more than any other repository we track.`
            : `${repo.full_name} has ${formatStat(repo.latest_stars)} stars. Weekly velocity appears after a second daily snapshot.`)}
      </p>
      {insight?.verdict && <div className="verdict">&ldquo;{insight.verdict}&rdquo;</div>}
      <Link className="readmore" href={`/repos/${repo.id}`}>
        Read the full analysis →
      </Link>
    </article>
  );
}

function Story({ repo, rank }: { repo: RepoCard; rank: number }) {
  return (
    <Link className="story" href={`/repos/${repo.id}`}>
      <div className="skick">
        No. {rank}
        {repo.language ? ` · ${repo.language}` : ""}
      </div>
      <h3>{repo.name}</h3>
      <p>{repo.verdict ?? repo.description ?? "No description provided."}</p>
      <div className="smeta">
        <b>{formatDelta(repo.stars_gained_week)}</b> this week · momentum {Math.round(repo.momentum_score)}
      </div>
    </Link>
  );
}

function CallsBox() {
  const { data } = useQuery({ queryKey: ["calls"], queryFn: getCalls, staleTime: 5 * 60_000, retry: false });
  const open = (data?.calls ?? []).filter((c) => c.status === "open").slice(0, 5);
  const rec = data?.record;
  return (
    <div>
      <div className="rulehead">
        Breakout calls <Link className="meta" href="/breakouts">track record →</Link>
      </div>
      {rec && rec.hits + rec.misses > 0 && (
        <p className="callrec">
          <b>{rec.hits}</b> of {rec.hits + rec.misses} called repos reached the weekly top {rec.hit_rank}
          {rec.avg_lead_days != null && <>, on average {rec.avg_lead_days} days after the call</>}.
        </p>
      )}
      {open.length ? (
        open.map((c) => (
          <Link key={c.id} className="mini" href={`/repos/${c.id}`}>
            <span className="mn">{c.full_name}</span>
            <span className="mg">{c.accel.toFixed(1)}× pace</span>
          </Link>
        ))
      ) : (
        <p className="emptyline">
          No open calls. Each refresh flags small repos whose weekly stars jump well above their own
          baseline, before they reach the top lists.
        </p>
      )}
    </div>
  );
}

function ShippedBox() {
  const { data } = useQuery({ queryKey: ["digest"], queryFn: getDigest, staleTime: 5 * 60_000, retry: false });
  const shipped = (data?.shipped ?? []).slice(0, 6);
  return (
    <div>
      <div className="rulehead">
        What shipped <Link className="meta" href="/this-week">this week →</Link>
      </div>
      {shipped.length ? (
        shipped.map((r) => (
          <Link key={`${r.id}-${r.tag}`} className="mini" href={`/repos/${r.id}`}>
            <span className="mn">{r.full_name}</span>
            <span className="reltag">{r.tag}</span>
            <span className="mg" style={{ color: "var(--dim2)", fontWeight: 400 }}>
              {relativeTime(r.published_at)}
            </span>
          </Link>
        ))
      ) : (
        <p className="emptyline">Releases from the top repositories show up here after the next refresh.</p>
      )}
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

function LeaderEntry({ rank, repo }: { rank: number; repo: RepoCard }) {
  return (
    <Link className="lentry compact" href={`/repos/${repo.id}`}>
      <div className="rk">
        {rank}
        <RankMove rank={rank} prev={repo.prev_rank} />
      </div>
      <div>
        <div className="nm">{repo.name}</div>
        <div className="ds">{repo.language ?? "—"}</div>
      </div>
      <div className="rt rtwatch">
        <div>
          <div className="gv" style={repo.stars_gained_today ? undefined : { color: "var(--dim2)" }}>
            {repo.stars_gained_today ? formatDelta(repo.stars_gained_today) : "—"}
          </div>
          <div className="gl">today</div>
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
      No dashboard data yet. Once the backend has ingested trending repositories, the lead story and
      leaderboards will populate here automatically.
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div style={{ marginTop: 40 }}>
      <div className="skel" style={{ height: 52, marginBottom: 30 }} />
      <div className="front">
        <div>
          <div className="skel" style={{ height: 60, width: "80%", marginBottom: 16 }} />
          <div className="skel" style={{ height: 20, width: "60%", marginBottom: 24 }} />
          <div className="skel" style={{ height: 140 }} />
        </div>
        <div>
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="skel" style={{ height: 44, marginBottom: 10 }} />
          ))}
        </div>
      </div>
    </div>
  );
}
