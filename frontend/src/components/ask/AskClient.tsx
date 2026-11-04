"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ask } from "@/lib/api";
import { formatStat, formatDelta } from "@/lib/utils";
import { AskBox, LifecycleChip, StarFlag, useStarChecks } from "@/components/shared/Signals";
import { WatchButton } from "@/components/shared/WatchButton";
import { Sparkline } from "@/components/shared/Sparkline";
import { useSparklines } from "@/hooks/useSparklines";

export function AskClient() {
  const q = useSearchParams().get("q")?.trim() ?? "";
  const { data, isFetching, isError } = useQuery({
    queryKey: ["ask", q],
    queryFn: () => ask(q),
    enabled: q.length >= 3,
    staleTime: 10 * 60_000,
    retry: false,
  });
  const sparks = useSparklines((data?.repos ?? []).map((r) => r.id));
  const checks = useStarChecks((data?.repos ?? []).map((r) => r.id));

  return (
    <div className="fade-up">
      <div className="kicker">Ask the data</div>
      <h1 className="big">
        Ask in <span className="ember">plain English.</span>
      </h1>
      <p className="standfirst">
        Mention a language, a category, a size (&ldquo;under 2k stars&rdquo;), an age (&ldquo;new&rdquo;) or a
        stage (&ldquo;breaking out&rdquo;, &ldquo;fading&rdquo;), and how to rank (&ldquo;fastest-growing&rdquo;,
        &ldquo;today&rdquo;, &ldquo;most starred&rdquo;).
      </p>
      <AskBox initial={q} autoFocus={!q} />

      {q.length >= 3 && (
        <>
          {data && (
            <div className="understood">
              <span>{data.understood}</span>
              <em>{data.parsed_by === "ai" ? "read by AI" : "read by keywords"}</em>
            </div>
          )}
          <div className="rulehead">
            Results <span className="meta">{data ? `${data.repos.length} repos · ${data.took_ms}ms` : ""}</span>
          </div>
          {isFetching && !data ? (
            Array.from({ length: 5 }).map((_, i) => <div key={i} className="skel" style={{ height: 58, marginBottom: 10 }} />)
          ) : isError ? (
            <div className="note">Couldn&apos;t answer that right now. Try again in a moment.</div>
          ) : data?.repos.length ? (
            data.repos.map((r, i) => (
              <Link key={r.id} className="lentry" href={`/repos/${r.id}`}>
                <div className="rk">{i + 1}</div>
                <div>
                  <div className="nm">
                    {r.full_name}
                    {r.language && <span className="lang">{r.language}</span>}
                    <LifecycleChip stage={r.lifecycle} />
                    <StarFlag check={checks[String(r.id)]} />
                  </div>
                  <div className="ds">{r.description ?? "No description provided."}</div>
                </div>
                <div className="rt rtwatch">
                  <span className="lspark">
                    <Sparkline values={sparks[String(r.id)]} width={56} height={20} color="var(--gain)" />
                  </span>
                  <div>
                    <div className="gv">{formatDelta(r.stars_gained_week)}</div>
                    <div className="gl">
                      wk · {formatStat(r.latest_stars)} ★ · {Math.round(r.momentum_score)}
                    </div>
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
            ))
          ) : data ? (
            <div className="note">
              Nothing matched. Try fewer conditions, or a broader word (&ldquo;database&rdquo; instead of a product
              name).
            </div>
          ) : null}
        </>
      )}

      <div className="foot">
        <div className="fb">Ask the data</div>
        <div className="fm">Questions become filters over tracked repos · nothing is generated</div>
      </div>
    </div>
  );
}
