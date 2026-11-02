"use client";

import Link from "next/link";
import { useQueries, useQuery } from "@tanstack/react-query";
import { getCategoryTrend, getLanguages, getReleases, getRepositories, getTrends } from "@/lib/api";
import type { RepoCard } from "@/lib/types";
import { formatDelta, relativeTime } from "@/lib/utils";
import { useWatchlist } from "@/hooks/useWatchlist";
import { FollowChip, useFollows } from "@/components/shared/Signals";
import { WatchButton } from "@/components/shared/WatchButton";

export function ForYouClient() {
  const follows = useFollows();
  const { items: watched } = useWatchlist();
  const watchedIds = watched.map((w) => w.id);

  const { data: trends } = useQuery({ queryKey: ["trends", "7d"], queryFn: () => getTrends("7d"), staleTime: 10 * 60_000 });
  const { data: langs } = useQuery({ queryKey: ["languages"], queryFn: getLanguages, staleTime: 10 * 60_000 });
  const { data: rel } = useQuery({
    queryKey: ["releases", watchedIds.join(",")],
    queryFn: () => getReleases(watchedIds, 30),
    enabled: watchedIds.length > 0,
    staleTime: 10 * 60_000,
  });

  const catFeeds = useQueries({
    queries: follows.categories.map((slug) => ({
      queryKey: ["category", slug, "7d"],
      queryFn: () => getCategoryTrend(slug, "7d"),
      staleTime: 10 * 60_000,
    })),
  });
  const langFeeds = useQueries({
    queries: follows.languages.map((language) => ({
      queryKey: ["repos", "lang-week", language],
      queryFn: () => getRepositories({ language, sort: "stars_gained_week", limit: 5 }),
      staleTime: 10 * 60_000,
    })),
  });

  const categories = (trends?.categories ?? []).map((c) => c.category);
  const catName = (slug: string) => categories.find((c) => c.slug === slug)?.name ?? slug;
  const topLangs = [...(langs?.languages ?? [])].sort((a, b) => b.repo_count - a.repo_count).slice(0, 12);
  const nothingYet = !watched.length && !follows.categories.length && !follows.languages.length;

  return (
    <div className="fade-up">
      <div className="kicker">For you · saved in this browser, no account</div>
      <h1 className="big">
        Your <span className="ember">corner</span> of GitHub.
      </h1>
      <p className="standfirst">
        Follow the categories and languages you care about. Your watchlist and its latest releases sit
        at the top.
      </p>

      <div className="rulehead">
        Follow categories <span className="meta">{follows.categories.length} followed</span>
      </div>
      <div className="filters">
        {categories.map((c) => (
          <FollowChip key={c.slug} kind="categories" value={c.slug} label={c.name} />
        ))}
      </div>
      <div className="rulehead">
        Follow languages <span className="meta">{follows.languages.length} followed</span>
      </div>
      <div className="filters">
        {topLangs.map((l) => (
          <FollowChip key={l.language} kind="languages" value={l.language} />
        ))}
      </div>

      {nothingYet && (
        <div className="note">
          Pick a few chips above, or ☆ a repo anywhere on the site, and your feed fills in here.
        </div>
      )}

      {watched.length > 0 && (
        <>
          <div className="rulehead">
            Watching <Link className="meta" href="/watchlist">manage watchlist →</Link>
          </div>
          <div className="panelrow">
            <div>
              {watched.slice(0, 8).map((w) => (
                <Link key={w.id} className="mini" href={`/repos/${w.id}`}>
                  <span className="mn">{w.full_name}</span>
                  <span className="mg">{formatDelta(w.stars_gained_week)}</span>
                </Link>
              ))}
            </div>
            <div>
              <div className="sidelabel">Shipped in the last 30 days</div>
              {(rel?.releases ?? []).length ? (
                rel!.releases.slice(0, 8).map((r) => (
                  <a
                    key={`${r.id}-${r.tag}`}
                    className="mini"
                    href={r.url ?? `https://github.com/${r.full_name}/releases`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <span className="mn">{r.full_name}</span>
                    <span className="reltag">{r.tag}</span>
                    <span className="mg" style={{ color: "var(--dim2)", fontWeight: 400 }}>
                      {relativeTime(r.published_at)}
                    </span>
                  </a>
                ))
              ) : (
                <p className="emptyline">No releases from your watched repos lately.</p>
              )}
            </div>
          </div>
        </>
      )}

      {follows.categories.map((slug, i) => (
        <Feed
          key={slug}
          title={catName(slug)}
          href={`/trends/${slug}`}
          repos={catFeeds[i]?.data?.top_repos?.slice(0, 5)}
          loading={catFeeds[i]?.isLoading}
        />
      ))}
      {follows.languages.map((language, i) => (
        <Feed
          key={language}
          title={language}
          href={`/repositories?language=${encodeURIComponent(language)}`}
          repos={langFeeds[i]?.data?.items}
          loading={langFeeds[i]?.isLoading}
        />
      ))}

      <div className="foot">
        <div className="fb">For You</div>
        <div className="fm">Follows and watchlist stay on this device · export them from the watchlist</div>
      </div>
    </div>
  );
}

function Feed({ title, href, repos, loading }: { title: string; href: string; repos?: RepoCard[]; loading?: boolean }) {
  return (
    <>
      <div className="rulehead">
        {title} <Link className="meta" href={href}>see all →</Link>
      </div>
      {loading
        ? Array.from({ length: 3 }).map((_, i) => <div key={i} className="skel" style={{ height: 50, marginBottom: 8 }} />)
        : (repos ?? []).map((r) => (
            <Link key={r.id} className="lentry" href={`/repos/${r.id}`}>
              <div className="rk" style={{ fontSize: 15 }}>
                →
              </div>
              <div>
                <div className="nm">
                  {r.full_name}
                  {r.language && <span className="lang">{r.language}</span>}
                </div>
                <div className="ds">{r.verdict ?? r.description ?? "No description provided."}</div>
              </div>
              <div className="rt rtwatch">
                <div>
                  <div className="gv">{formatDelta(r.stars_gained_week)}</div>
                  <div className="gl">stars/wk</div>
                </div>
                <WatchButton
                  variant="icon"
                  repo={{
                    id: r.id,
                    full_name: r.full_name,
                    name: r.name,
                    language: r.language,
                    momentum_score: r.momentum_score,
                    stars_gained_week: r.stars_gained_week,
                  }}
                />
              </div>
            </Link>
          ))}
    </>
  );
}
