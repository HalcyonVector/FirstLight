"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { getLanguages } from "@/lib/api";
import { formatStat, formatDelta, getLanguageColor } from "@/lib/utils";

export function LanguagesClient() {
  const { data, isLoading } = useQuery({
    queryKey: ["languages"],
    queryFn: getLanguages,
    staleTime: 5 * 60_000,
  });
  const langs = data?.languages ?? [];

  return (
    <div className="fade-up">
      <div className="kicker">Language momentum</div>
      <h1 className="big">
        Which <span className="ember">languages</span> are moving.
      </h1>
      <p className="standfirst">
        Every tracked language, ranked by the average momentum of its repositories — a read on where
        the energy is by ecosystem, not just by project.
      </p>

      <div className="rulehead">
        Language Rankings <span className="meta">avg momentum · repos · stars/wk</span>
      </div>

      {isLoading && !data ? (
        <div style={{ marginTop: 12 }}>
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="skel" style={{ height: 66, marginBottom: 8 }} />
          ))}
        </div>
      ) : langs.length ? (
        <div>
          {langs.map((l, i) => (
            <Link
              key={l.language}
              className="trendrow"
              href={`/repositories?language=${encodeURIComponent(l.language)}`}
            >
              <div className="idx">{String(i + 1).padStart(2, "0")}</div>
              <div>
                <div className="tn" style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <span
                    className="langdot"
                    style={{ background: getLanguageColor(l.language), width: 14, height: 14 }}
                  />
                  {l.language}
                </div>
                <div className="td">
                  {l.repo_count.toLocaleString()} repos · {formatStat(l.total_stars)} total stars
                </div>
              </div>
              <div className="tspark" style={{ display: "flex", alignItems: "center" }}>
                <div
                  style={{
                    height: 4,
                    width: "100%",
                    background: "var(--rule)",
                    borderRadius: 2,
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      height: "100%",
                      width: `${Math.min(100, l.avg_momentum)}%`,
                      background: "linear-gradient(90deg,var(--ember2),var(--ember))",
                    }}
                  />
                </div>
              </div>
              <div className="tsc">
                <div className="v">{Math.round(l.avg_momentum)}</div>
                <div className="d up">{formatDelta(l.stars_gained_week)} / wk</div>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <div className="note">No language data yet — appears once repositories are ingested.</div>
      )}

      <div className="foot">
        <div className="fb">{langs.length} languages ranked</div>
        <div className="fm">Momentum averaged across each language&apos;s repositories</div>
      </div>
    </div>
  );
}
