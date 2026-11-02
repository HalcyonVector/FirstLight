"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { search as searchApi, getLanguages } from "@/lib/api";
import { formatDelta, getLanguageColor } from "@/lib/utils";

export function SearchClient() {
  const router = useRouter();
  const params = useSearchParams();
  const initial = params.get("q") ?? "";
  const [q, setQ] = useState(initial);
  const [debounced, setDebounced] = useState(initial);
  const [filter, setFilter] = useState(params.get("language") ?? "All");

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q), 250);
    return () => clearTimeout(t);
  }, [q]);

  // Keep the URL in sync so results are shareable
  useEffect(() => {
    const sp = new URLSearchParams();
    if (debounced.trim()) sp.set("q", debounced.trim());
    if (filter !== "All") sp.set("language", filter);
    router.replace(`/search${sp.toString() ? `?${sp}` : ""}`, { scroll: false });
  }, [debounced, filter, router]);

  const { data, isFetching } = useQuery({
    queryKey: ["search", debounced, filter],
    queryFn: () => searchApi(debounced, 20, filter === "All" ? undefined : filter),
    enabled: debounced.trim().length >= 2,
    staleTime: 30_000,
  });

  const results = data?.repos ?? [];

  const { data: langData } = useQuery({
    queryKey: ["languages"],
    queryFn: getLanguages,
    staleTime: 10 * 60_000,
  });
  const FILTERS = [
    "All",
    ...[...(langData?.languages ?? [])]
      .sort((a, b) => b.repo_count - a.repo_count)
      .slice(0, 8)
      .map((l) => l.language),
  ];
  if (!FILTERS.includes(filter)) FILTERS.push(filter);

  return (
    <div className="fade-up">
      <div className="kicker">Search every tracked repository</div>
      <h1 className="big">
        Find it before it <span className="ember">trends.</span>
      </h1>

      <div className="searchbox">
        <span className="ico">⌕</span>
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="vector database · ai agent · mcp server …"
        />
      </div>

      <div className="filters">
        {FILTERS.map((f) => (
          <button key={f} className={`chip ${filter === f ? "on" : ""}`} onClick={() => setFilter(f)}>
            {f}
          </button>
        ))}
      </div>

      <div style={{ marginTop: 20 }}>
        {debounced.trim().length < 2 ? (
          <div className="note">Type at least two characters to search across every tracked repository.</div>
        ) : results.length ? (
          results.map((r) => (
            <Link key={r.id} className="sresult" href={`/repos/${r.id}`}>
              <span className="langdot" style={{ background: getLanguageColor(r.language) }} />
              <div>
                <div className="sn">{r.full_name}</div>
                <div className="sd">{r.description ?? "No description provided."}</div>
                <div className="st">
                  {r.language && <span className="tag">{r.language}</span>}
                  {r.topics.slice(0, 3).map((t) => (
                    <span key={t} className="tag">
                      {t}
                    </span>
                  ))}
                </div>
              </div>
              <div className="ss">
                <div className="a">{formatDelta(r.stars_gained_week)}</div>
                <div className="b">momentum {Math.round(r.momentum_score)}</div>
              </div>
            </Link>
          ))
        ) : (
          <div className="note">No matches for “{debounced}”.</div>
        )}
      </div>

      {data && debounced.trim().length >= 2 && (
        <div className="tookms">
          {data.total_repos.toLocaleString()} results · took {data.took_ms}ms
          {isFetching ? " · updating…" : ""}
        </div>
      )}

      <div className="foot">
        <div className="fb">Search</div>
        <div className="fm">Matches names, descriptions and topics</div>
      </div>
    </div>
  );
}
