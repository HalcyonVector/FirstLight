"use client";

import { useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import Link from "next/link";
import { getRepositories, getLanguages } from "@/lib/api";
import { formatStat, formatDelta, getLanguageColor } from "@/lib/utils";
import { Sparkline } from "@/components/shared/Sparkline";
import { useSparklines } from "@/hooks/useSparklines";

const SORTS: { key: string; label: string }[] = [
  { key: "stars_gained_week", label: "Rising this week" },
  { key: "stars_gained_today", label: "Hot today" },
  { key: "momentum_score", label: "Momentum" },
  { key: "latest_stars", label: "Most stars" },
];

export function RepositoriesClient() {
  const router = useRouter();
  const params = useSearchParams();

  const sort = params.get("sort") ?? "stars_gained_week";
  const language = params.get("language") ?? "All";
  const page = Math.max(1, Number(params.get("page") ?? "1") || 1);

  const setParam = useCallback(
    (updates: Record<string, string | number | null>) => {
      const sp = new URLSearchParams(params.toString());
      Object.entries(updates).forEach(([k, v]) => {
        if (v === null || v === "" || v === "All") sp.delete(k);
        else sp.set(k, String(v));
      });
      router.replace(`/repositories${sp.toString() ? `?${sp}` : ""}`, { scroll: false });
    },
    [params, router]
  );

  const { data, isFetching } = useQuery({
    queryKey: ["repositories", sort, language, page],
    queryFn: () =>
      getRepositories({
        sort,
        language: language === "All" ? undefined : language,
        page,
        limit: 20,
      }),
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });

  const items = data?.items ?? [];
  const pages = data?.pages ?? 1;
  const total = data?.total ?? 0;
  const sparks = useSparklines(items.map((r) => r.id));
  const { data: langData } = useQuery({
    queryKey: ["languages"],
    queryFn: getLanguages,
    staleTime: 10 * 60_000,
  });
  const topLangs = [...(langData?.languages ?? [])]
    .sort((a, b) => b.repo_count - a.repo_count)
    .slice(0, 10)
    .map((l) => l.language);
  if (language !== "All" && !topLangs.includes(language)) topLangs.push(language);
  const LANGS = ["All", ...topLangs];

  const sortLabel = SORTS.find((s) => s.key === sort)?.label ?? sort;

  return (
    <div className="fade-up">
      <div className="kicker">Every tracked repository</div>
      <h1 className="big">
        The <span className="ember">index.</span>
      </h1>
      <p className="standfirst">
        {formatStat(total)} repositories under watch. Sort by velocity or footprint, filter by
        language, and page through the whole board.
      </p>

      <div className="filters" style={{ marginTop: 22 }}>
        {SORTS.map((s) => (
          <button
            key={s.key}
            className={`chip ${sort === s.key ? "on" : ""}`}
            onClick={() => setParam({ sort: s.key, page: 1 })}
          >
            {s.label}
          </button>
        ))}
      </div>
      <div className="filters" style={{ marginTop: 10 }}>
        {LANGS.map((l) => (
          <button
            key={l}
            className={`chip ${language === l ? "on" : ""}`}
            onClick={() => setParam({ language: l, page: 1 })}
          >
            {l}
          </button>
        ))}
        <Link className="chip" href="/languages">
          All languages →
        </Link>
      </div>

      <div className="rulehead">
        {sortLabel}
        <span className="meta">
          page {page} of {pages}
          {isFetching ? " · updating…" : ""}
        </span>
      </div>

      {items.length === 0 ? (
        <div className="note">No repositories match these filters yet.</div>
      ) : (
        <div>
          {items.map((r, i) => (
            <Link key={r.id} className="lentry" href={`/repos/${r.id}`}>
              <div className="rk">{(page - 1) * 20 + i + 1}</div>
              <div>
                <div className="nm">
                  {r.full_name}
                  {r.language && (
                    <span className="lang" style={{ color: getLanguageColor(r.language) }}>
                      {r.language}
                    </span>
                  )}
                </div>
                <div className="ds">{r.description ?? "No description provided."}</div>
              </div>
              <div className="rt">
                {(sparks[String(r.id)]?.length ?? 0) > 1 && (
                  <div style={{ marginBottom: 4 }}>
                    <Sparkline values={sparks[String(r.id)]} width={72} height={20} color="var(--gain)" />
                  </div>
                )}
                <div className="gv">{formatDelta(r.stars_gained_week)}</div>
                <div className="gl">
                  {formatStat(r.latest_stars)} ★ · {Math.round(r.momentum_score)}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}

      <div className="pager">
        <button className="pagerbtn" disabled={page <= 1} onClick={() => setParam({ page: page - 1 })}>
          ← Prev
        </button>
        <span className="pagerinfo">
          {page} / {pages}
        </span>
        <button
          className="pagerbtn"
          disabled={page >= pages}
          onClick={() => setParam({ page: page + 1 })}
        >
          Next →
        </button>
      </div>

      <div className="foot">
        <div className="fb">{formatStat(total)} repositories</div>
        <div className="fm">20 per page · refreshed every 6 hours</div>
      </div>
    </div>
  );
}
