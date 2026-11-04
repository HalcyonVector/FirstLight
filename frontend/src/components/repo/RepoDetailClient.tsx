"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { getRepository, getRepositoryMetrics, getSimilarRepos } from "@/lib/api";
import { addRecentRepo } from "@/lib/recent";
import type { DailyMetric, HypeCurve, MomentumBreakdown, RepoDetail, StarQuality, StarSpike } from "@/lib/types";
import { formatStat, formatDelta, getLanguageColor, relativeTime } from "@/lib/utils";
import { parseCompetitors } from "@/lib/chart";
import { WatchButton } from "@/components/shared/WatchButton";
import { AreaChart, BarChart, shortDate } from "@/components/shared/Charts";
import { LifecycleChip, OddsChip } from "@/components/shared/Signals";
import { milestoneMarkers, releaseMarkers, spikeMarkers } from "@/lib/markers";

type Range = "30d" | "90d";

export function RepoDetailClient({ id }: { id: number }) {
  const [range, setRange] = useState<Range>("90d");

  const { data: repo, isLoading, isError } = useQuery({
    queryKey: ["repo", id],
    queryFn: () => getRepository(id),
    staleTime: 5 * 60_000,
    retry: false,
  });

  const { data: metrics } = useQuery({
    queryKey: ["repo-metrics", id, range],
    queryFn: () => getRepositoryMetrics(id, range),
    staleTime: 5 * 60_000,
    retry: false,
    placeholderData: keepPreviousData,
  });

  const { data: similar } = useQuery({
    queryKey: ["similar", id],
    queryFn: () => getSimilarRepos(id),
    staleTime: 5 * 60_000,
    retry: false,
  });

  useEffect(() => {
    if (repo) addRecentRepo({ id: repo.id, full_name: repo.full_name });
  }, [repo]);

  if (isLoading) return <RepoSkeleton />;
  if (isError || !repo) {
    return (
      <div className="fade-up">
        <Link className="crumb" href="/" style={{ display: "inline-block", marginTop: 34 }}>
          ← Dashboard
        </Link>
        <div className="note">Repository not found, or the backend is unavailable.</div>
      </div>
    );
  }

  const daily: DailyMetric[] = metrics?.daily ?? [];
  const latestDaily = daily[daily.length - 1];
  const contributors = latestDaily?.contributors_count;
  const insight = repo.latest_insight;
  const competitors = parseCompetitors(insight?.competitors);

  const starsSeries = daily.map((d) => d.stars_total);
  const markers = [
    ...releaseMarkers(daily, repo.releases ?? []),
    ...milestoneMarkers(daily),
    ...spikeMarkers(daily, repo.spikes ?? []),
  ];
  const dayLabels = daily.map((d) => shortDate(d.date));
  const gainedDays = daily.slice(-30);

  // ── Hype vs. substance: is momentum backed by real dev activity, or just stars? ──
  const weekly = metrics?.weekly ?? [];
  const lastWeek = weekly[weekly.length - 1];
  const commitAct = lastWeek?.commit_activity ?? latestDaily?.commit_count_week ?? 0;
  const newContrib = lastWeek?.new_contributors ?? 0;
  const forkRatio = repo.latest_stars ? repo.latest_forks / repo.latest_stars : 0;
  const hasActivity = commitAct > 0 || newContrib > 0 || forkRatio > 0.04;
  const anomaly = repo.momentum_breakdown?.star_anomaly ?? false;
  const signal = anomaly
    ? { label: "Unusual star spike", cls: "warn" }
    : hasActivity
      ? { label: "Backed by activity", cls: "good" }
      : { label: "Star-driven", cls: "" };
  const signalWhy = [
    `${commitAct} commits this week`,
    `${newContrib} new contributors`,
    `${(forkRatio * 100).toFixed(1)}% fork-to-star ratio`,
    anomaly ? "large star jump with almost no fork, contributor or commit growth" : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const momentumSeries = weekly.map((w) => w.momentum_score);
  const weekLabels = weekly.map((w) => `Week of ${shortDate(w.week_start)}`);
  const githubUrl = `https://github.com/${repo.full_name}`;

  return (
    <div className="fade-up">
      <div className="rhero">
        <div className="crumb">
          <Link href="/">Dashboard</Link> / <Link href="/repositories">Repositories</Link>
        </div>
        <div className="rtitle">
          {/* GitHub serves owner avatars publicly; plain <img> avoids next/image remote config. */}
          <img
            className="ravatar"
            src={`https://github.com/${repo.owner}.png?size=96`}
            alt=""
            width={48}
            height={48}
            loading="lazy"
          />
          <h1>
            <span className="ow">{repo.owner} /</span> {repo.name}
          </h1>
        </div>
        <p className="rdesc">{repo.description ?? "No description provided."}</p>
        <div className="rmeta">
          {repo.language && (
            <span>
              <span className="langdot" style={{ background: getLanguageColor(repo.language) }} />
              {repo.language}
            </span>
          )}
          {repo.license && <span>{repo.license}</span>}
          {repo.github_created_at && <span>◇ Created {new Date(repo.github_created_at).getFullYear()}</span>}
          {repo.last_synced_at && <span>↻ Synced {relativeTime(repo.last_synced_at)}</span>}
          <LifecycleChip stage={repo.lifecycle} />
          {repo.categories[0] && (
            <Link className="aitag" href={`/trends/${repo.categories[0].slug}`}>
              {repo.categories[0].name}
            </Link>
          )}
          <span className={`signal ${signal.cls}`} title={signalWhy}>
            {signal.label}
          </span>
        </div>
        {repo.breakout_call && <CallNote call={repo.breakout_call} />}
        <p className="sigwhy">{signalWhy}</p>
      </div>

      <div className="metrics">
        <Metric v={formatStat(repo.latest_stars)} d="Stars" chg={`${formatDelta(repo.stars_gained_week)} / wk`} ember />
        <Metric v={formatStat(repo.latest_forks)} d="Forks" chg="" />
        <Metric v={contributors ? formatStat(contributors) : "—"} d="Contributors" chg="" />
        <Metric v={String(Math.round(repo.momentum_score))} d="Momentum" chg={`${formatDelta(repo.stars_gained_today)} today`} ember />
      </div>

      <div className="chartcard herochart">
        <h4>
          <span>
            Stars over time
            <span className="legend">
              <i className="release" /> release <i className="milestone" /> milestone <i className="spike" /> spike
            </span>
          </span>
          <span className="rangetabs" role="group" aria-label="Chart range">
            {(["30d", "90d"] as Range[]).map((r) => (
              <button key={r} className={`chip ${range === r ? "on" : ""}`} onClick={() => setRange(r)}>
                {r === "30d" ? "30 days" : "90 days"}
              </button>
            ))}
          </span>
        </h4>
        {starsSeries.length > 2 ? (
          <AreaChart values={starsSeries} labels={dayLabels} markers={markers} height={200} />
        ) : (
          <div className="note" style={{ margin: 0 }}>Metrics will appear once daily snapshots accumulate.</div>
        )}
      </div>

      {(repo.spikes?.length ?? 0) > 0 && <WhyItJumped spikes={repo.spikes!} />}

      <div className="detailgrid">
        <div>
          <div className="chartcard">
            <h4>
              Daily stars gained <span>last {gainedDays.length} days</span>
            </h4>
            {gainedDays.length > 1 ? (
              <BarChart
                values={gainedDays.map((d) => d.stars_gained)}
                labels={gainedDays.map((d) => shortDate(d.date))}
                format={(v) => formatDelta(v)}
              />
            ) : (
              <div className="note" style={{ margin: 0 }}>No daily velocity recorded yet.</div>
            )}
          </div>
          <div className="chartcard" style={{ marginTop: 22 }}>
            <h4>
              Momentum over time <span>last {momentumSeries.length} weeks</span>
            </h4>
            {momentumSeries.length > 1 ? (
              <AreaChart values={momentumSeries} labels={weekLabels} format={(v) => v.toFixed(0)} />
            ) : (
              <div className="note" style={{ margin: 0 }}>Momentum history builds each week.</div>
            )}
          </div>
          {repo.momentum_breakdown && (
            <ScoreBreakdown b={repo.momentum_breakdown} score={repo.momentum_score} />
          )}
          {repo.hype && <AfterTheHype h={repo.hype} />}
          {repo.star_quality && <StarCheck q={repo.star_quality} />}
          {(repo.releases?.length ?? 0) > 0 && <Releases repo={repo} />}
        </div>

        <div className="insight">
          <div className="rulehead" style={{ marginTop: 0 }}>
            AI Analyst
            <span className="meta">
              {insight
                ? `${insight.model_used ?? "llm"} · written ${relativeTime(insight.generated_at)}`
                : "pending"}
            </span>
          </div>
          {insight ? (
            <>
              {insight.why_growing && (
                <>
                  <h4>Why it&apos;s growing</h4>
                  <p>{insight.why_growing}</p>
                </>
              )}
              {insight.what_it_solves && (
                <>
                  <h4>What it solves</h4>
                  <p>{insight.what_it_solves}</p>
                </>
              )}
              {insight.who_uses_it && (
                <>
                  <h4>Who uses it</h4>
                  <p>{insight.who_uses_it}</p>
                </>
              )}
              {insight.tech_stack && (
                <>
                  <h4>Under the hood</h4>
                  <p>{insight.tech_stack}</p>
                </>
              )}
              {insight.verdict && <div className="verdict">&ldquo;{insight.verdict}&rdquo;</div>}
              {competitors.length > 0 && (
                <>
                  <h4>Competitors / alternatives</h4>
                  <div className="compet">
                    {competitors.map((c) => (
                      <Link key={c} href={`/search?q=${encodeURIComponent(c)}`}>
                        {c}
                      </Link>
                    ))}
                  </div>
                </>
              )}
            </>
          ) : (
            <p style={{ color: "var(--dim)" }}>
              No AI insight generated yet. Insights are written for the highest-momentum
              repositories on each refresh.
            </p>
          )}
          {repo.topics.length > 0 && (
            <>
              <h4>Topics</h4>
              <div className="compet">
                {repo.topics.slice(0, 8).map((t) => (
                  <Link key={t} href={`/search?q=${encodeURIComponent(t)}`}>
                    {t}
                  </Link>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {(similar?.similar?.length ?? 0) > 0 && (
        <>
          <div className="rulehead">
            Similar Repositories <span className="meta">shared categories</span>
          </div>
          {similar!.similar.map((r) => (
            <Link key={r.id} className="lentry" href={`/repos/${r.id}`}>
              <div className="rk" style={{ fontSize: 15 }}>
                →
              </div>
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
        </>
      )}

      <div className="actbar">
        <span className="abname">{repo.full_name}</span>
        <WatchButton
          repo={{
            id: repo.id,
            full_name: repo.full_name,
            name: repo.name,
            language: repo.language,
            momentum_score: repo.momentum_score,
            stars_gained_week: repo.stars_gained_week,
          }}
        />
        <Link className="watchbtn" href={`/compare?ids=${repo.id}`}>
          Compare with…
        </Link>
        {repo.homepage_url && (
          <a className="watchbtn hidesm" href={repo.homepage_url} target="_blank" rel="noopener noreferrer">
            Homepage ↗
          </a>
        )}
        <a className="watchbtn on" href={githubUrl} target="_blank" rel="noopener noreferrer">
          GitHub ↗
        </a>
      </div>

      <div className="foot">
        <div className="fb">{repo.full_name}</div>
        <div className="fm">
          {repo.last_synced_at ? `Last synced ${relativeTime(repo.last_synced_at)}` : "Not synced yet"}
          {" · "}
          <BadgeCopy id={repo.id} />
        </div>
      </div>
    </div>
  );
}

const PART_LABELS: Record<keyof MomentumBreakdown["parts"], string> = {
  stars: "Star velocity",
  forks: "Fork velocity",
  contributors: "New contributors",
  commits: "Commit activity",
  issues: "Issues opened",
};
const PART_MAX: Record<keyof MomentumBreakdown["parts"], number> = {
  stars: 45,
  forks: 20,
  contributors: 20,
  commits: 10,
  issues: 5,
};

function ScoreBreakdown({ b, score }: { b: MomentumBreakdown; score: number }) {
  const keys = Object.keys(PART_LABELS) as (keyof MomentumBreakdown["parts"])[];
  return (
    <div className="chartcard" style={{ marginTop: 22 }}>
      <h4>
        How the score is built <span>week of {shortDate(b.week_start)}</span>
      </h4>
      {keys.map((k) => (
        <div key={k} className="bdrow">
          <span className="bdl">{PART_LABELS[k]}</span>
          <span className="bdbar">
            <i style={{ width: `${(b.parts[k] / PART_MAX[k]) * 100}%` }} />
          </span>
          <span className="bdv">
            {b.parts[k].toFixed(1)} <em>/ {PART_MAX[k]}</em>
          </span>
        </div>
      ))}
      <div className="bdfoot">
        {b.recency_multiplier > 1
          ? `× ${b.recency_multiplier} new-project bonus = ${Math.round(score)}`
          : `= ${Math.round(score)} momentum`}
      </div>
    </div>
  );
}

/** "We called this" line for repos that were flagged as breakout calls. */
function CallNote({ call }: { call: NonNullable<RepoDetail["breakout_call"]> }) {
  const on = shortDate(call.called_on);
  const text =
    call.status === "hit"
      ? `Called as a breakout on ${on} at ${formatStat(call.stars_at_call)} stars. It reached #${call.best_rank} on the weekly list${
          call.hit_on ? ` on ${shortDate(call.hit_on)}` : ""
        }.`
      : call.status === "open"
        ? `Called as a breakout on ${on} at ${formatStat(call.stars_at_call)} stars. Still open.`
        : `Called as a breakout on ${on}, but it did not reach the weekly top list in time.`;
  return (
    <Link className={`callnote ${call.status}`} href="/breakouts">
      ◎ {text} {call.status === "open" && <OddsChip prob={call.prob} />}
    </Link>
  );
}

/** Each recent star spike with what we found behind it. */
function WhyItJumped({ spikes }: { spikes: StarSpike[] }) {
  return (
    <div className="chartcard whyjump">
      <h4>
        Why it jumped <span>Hacker News and releases, checked each refresh</span>
      </h4>
      {spikes.map((s) => (
        <div key={s.date} className="spikerow">
          <div className="spikeday">
            <b>+{formatStat(s.gain)}</b>
            <span>
              {shortDate(s.date)} · usually {formatStat(s.baseline)}/day
            </span>
          </div>
          <div className="spikecauses">
            {s.causes.length ? (
              s.causes.map((c, i) => (
                <a key={i} href={c.url ?? undefined} target="_blank" rel="noopener noreferrer" className={`cause ${c.kind}`}>
                  <span className="ck">{c.kind === "hn" ? "Hacker News" : "Release"}</span>
                  <span className="ct">{c.title}</span>
                  {c.kind === "hn" && (
                    <span className="cm">
                      {formatStat(c.points ?? 0)} points · {formatStat(c.comments ?? 0)} comments
                    </span>
                  )}
                </a>
              ))
            ) : (
              <span className="nocause">
                No public trigger found on Hacker News or in releases. It may have come from social media or a
                newsletter.
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

/** Where the repo is relative to its biggest week. */
function AfterTheHype({ h }: { h: HypeCurve }) {
  const pct = h.peak_gain7 ? Math.round((100 * h.now_gain7) / h.peak_gain7) : 0;
  const halfDays = h.half_on
    ? Math.round((new Date(h.half_on).getTime() - new Date(h.peak_on).getTime()) / 86_400_000)
    : null;
  const commitsHeld = h.commits_peak > 0 ? h.commits_now >= Math.max(1, h.commits_peak / 2) : null;
  return (
    <div className="chartcard" style={{ marginTop: 22 }}>
      <h4>
        After the hype <span>peak week ended {shortDate(h.peak_on)}</span>
      </h4>
      <div className="bdrow">
        <span className="bdl">Now vs peak</span>
        <span className="bdbar">
          <i style={{ width: `${Math.min(100, pct)}%` }} />
        </span>
        <span className="bdv">{pct}%</span>
      </div>
      <p className="sigwhy">
        Best week: {formatDelta(h.peak_gain7)} stars. This week: {formatDelta(h.now_gain7)}.{" "}
        {halfDays != null
          ? `Weekly stars fell to half the peak ${halfDays} day${halfDays === 1 ? "" : "s"} later.`
          : "Weekly stars have not fallen to half the peak."}{" "}
        {commitsHeld === true && "Commit activity has held up."}
        {commitsHeld === false && "Commit activity has dropped off since."}
      </p>
    </div>
  );
}

const STAR_VERDICT: Record<StarQuality["verdict"], string> = {
  organic: "Looks organic",
  mixed: "Mixed signals",
  suspicious: "Looks inflated",
};

/** Result of sampling the most recent stargazers (account age and activity). */
function StarCheck({ q }: { q: StarQuality }) {
  return (
    <div className="chartcard" style={{ marginTop: 22 }}>
      <h4>
        Star check <span>{relativeTime(q.sampled_at)}</span>
      </h4>
      <div className={`starverdict ${q.verdict}`}>{STAR_VERDICT[q.verdict]}</div>
      <div className="bdrow">
        <span className="bdl">New accounts</span>
        <span className="bdbar">
          <i style={{ width: `${q.pct_new}%` }} />
        </span>
        <span className="bdv">{q.pct_new}%</span>
      </div>
      <div className="bdrow">
        <span className="bdl">Empty accounts</span>
        <span className="bdbar">
          <i style={{ width: `${q.pct_empty}%` }} />
        </span>
        <span className="bdv">{q.pct_empty}%</span>
      </div>
      <p className="sigwhy">
        From the {q.sample_size} most recent stargazers. New means the account was under 30 days old
        when it starred; empty means no followers and no public repos. Bought stars usually come from
        accounts like these.
      </p>
    </div>
  );
}

function Releases({ repo }: { repo: RepoDetail }) {
  return (
    <div className="chartcard" style={{ marginTop: 22 }}>
      <h4>
        Recent releases <span>{repo.releases!.length}</span>
      </h4>
      {repo.releases!.map((r) => (
        <a
          key={r.tag}
          className="relrow"
          href={r.url ?? `https://github.com/${repo.full_name}/releases`}
          target="_blank"
          rel="noopener noreferrer"
        >
          <span className="reltag">{r.tag}</span>
          <span className="relbody">
            {r.name && r.name !== r.tag && <b>{r.name}</b>}
            {r.snippet && <span>{r.snippet}</span>}
          </span>
          <span className="reldate">
            {shortDate(r.published_at)}
            {r.prerelease ? " · pre" : ""}
          </span>
        </a>
      ))}
    </div>
  );
}

/** Copies a Markdown README badge that links back to this page. */
function BadgeCopy({ id }: { id: number }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    const origin = window.location.origin;
    const md = `[![momentum](${origin}/badge/${id})](${origin}/repos/${id})`;
    try {
      await navigator.clipboard.writeText(md);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt("Copy this Markdown:", md);
    }
  }
  return (
    <button className="linkbtn" onClick={copy}>
      {copied ? "Badge Markdown copied" : "Copy README badge"}
    </button>
  );
}

function Metric({ v, d, chg, ember }: { v: string; d: string; chg: string; ember?: boolean }) {
  return (
    <div className="mc">
      <div className={`mv${ember ? " e" : ""}`}>{v}</div>
      <div className="md">{d}</div>
      {chg && <div className="mch up">{chg}</div>}
    </div>
  );
}

function RepoSkeleton() {
  return (
    <div style={{ marginTop: 40 }}>
      <div className="skel" style={{ height: 48, width: "60%", marginBottom: 14 }} />
      <div className="skel" style={{ height: 20, width: "80%", marginBottom: 26 }} />
      <div className="skel" style={{ height: 90, marginBottom: 24 }} />
      <div className="detailgrid">
        <div className="skel" style={{ height: 260 }} />
        <div className="skel" style={{ height: 260 }} />
      </div>
    </div>
  );
}
