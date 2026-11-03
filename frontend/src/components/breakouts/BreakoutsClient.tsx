"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getCalls } from "@/lib/api";
import type { BreakoutCall } from "@/lib/types";
import { formatStat, formatDelta } from "@/lib/utils";
import { shortDate } from "@/components/shared/Charts";
import { WatchButton } from "@/components/shared/WatchButton";
import { Sparkline } from "@/components/shared/Sparkline";
import { useSparklines } from "@/hooks/useSparklines";

type Filter = "all" | "open" | "hit" | "miss";

const STATUS_LABEL: Record<BreakoutCall["status"], string> = {
  open: "open",
  hit: "came true",
  miss: "missed",
};

export function BreakoutsClient() {
  const [filter, setFilter] = useState<Filter>("all");
  const { data, isLoading } = useQuery({ queryKey: ["calls"], queryFn: getCalls, staleTime: 5 * 60_000 });
  const rec = data?.record;
  const calls = (data?.calls ?? []).filter((c) => filter === "all" || c.status === filter);
  const resolved = rec ? rec.hits + rec.misses : 0;
  const sparks = useSparklines(calls.map((c) => c.id));

  return (
    <div className="fade-up">
      <div className="kicker">Breakout calls · predictions with a public track record</div>
      <h1 className="big">
        Called <span className="ember">before the crowd.</span>
      </h1>
      <p className="standfirst">
        Every refresh looks for small repositories (under 5k stars, under a year old) whose stars this
        week are at least 2.5× their own weekly average. Each one becomes a dated call. A call comes
        true if the repo reaches the weekly top {rec?.hit_rank ?? 25} within {rec?.window_days ?? 30} days.
      </p>

      <div className="strip">
        <div className="cell">
          <div className="cv e">{rec?.hit_rate != null ? `${rec.hit_rate}%` : "—"}</div>
          <div className="cl">Hit rate{resolved ? ` · ${resolved} resolved` : ""}</div>
        </div>
        <div className="cell">
          <div className="cv g">{rec ? rec.hits : "—"}</div>
          <div className="cl">Came true</div>
        </div>
        <div className="cell">
          <div className="cv">{rec ? rec.open : "—"}</div>
          <div className="cl">Still open</div>
        </div>
        <div className="cell">
          <div className="cv">{rec?.avg_lead_days != null ? `${rec.avg_lead_days}d` : "—"}</div>
          <div className="cl">Avg. days early</div>
        </div>
      </div>

      <div className="filters" role="group" aria-label="Filter calls">
        {(["all", "open", "hit", "miss"] as Filter[]).map((f) => (
          <button key={f} className={`chip ${filter === f ? "on" : ""}`} onClick={() => setFilter(f)}>
            {f === "all" ? "All" : STATUS_LABEL[f]}
          </button>
        ))}
      </div>

      <div className="rulehead">
        Calls <span className="meta">newest first</span>
      </div>
      {isLoading ? (
        Array.from({ length: 5 }).map((_, i) => <div key={i} className="skel" style={{ height: 58, marginBottom: 10 }} />)
      ) : calls.length ? (
        calls.map((c) => <CallRow key={c.id} c={c} spark={sparks[String(c.id)]} />)
      ) : (
        <div className="note">
          {data?.calls.length
            ? "No calls match this filter."
            : "No calls yet. The first ones appear after a few days of history, once a repo's weekly pace can be compared with its own baseline."}
        </div>
      )}

      <div className="foot">
        <div className="fb">Breakout calls</div>
        <div className="fm">At most 10 new calls a week · checked every 6h</div>
      </div>
    </div>
  );
}

function CallRow({ c, spark }: { c: BreakoutCall; spark?: number[] }) {
  return (
    <Link className="lentry callrow" href={`/repos/${c.id}`}>
      <div className="rk">
        <span className={`callstat ${c.status}`}>{STATUS_LABEL[c.status]}</span>
      </div>
      <div>
        <div className="nm">
          {c.full_name}
          {c.language && <span className="lang">{c.language}</span>}
        </div>
        <div className="ds">
          Called {shortDate(c.called_on)} at {formatStat(c.stars_at_call)} stars, gaining{" "}
          {formatStat(c.gain7_at_call)} a week ({c.accel.toFixed(1)}× its usual pace)
          {c.status === "hit" && c.best_rank != null && (
            <>
              {" "}· reached #{c.best_rank}
              {c.lead_days != null ? ` ${c.lead_days} days later` : ""}
            </>
          )}
        </div>
      </div>
      <div className="rt rtwatch">
        <span className="lspark">
          <Sparkline values={spark ?? []} width={56} height={20} color="var(--gain)" />
        </span>
        <div>
          <div className="gv">{formatStat(c.latest_stars)}</div>
          <div className="gl">now · {formatDelta(c.stars_gained_week)}/wk</div>
        </div>
        <WatchButton
          variant="icon"
          repo={{
            id: c.id,
            full_name: c.full_name,
            name: c.full_name.split("/").pop() ?? c.full_name,
            language: c.language,
            momentum_score: c.momentum_score,
            stars_gained_week: c.stars_gained_week,
          }}
        />
      </div>
    </Link>
  );
}
