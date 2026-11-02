"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueries, useQuery } from "@tanstack/react-query";
import { getRepository, getRepositoryMetrics, search as searchApi } from "@/lib/api";
import type { RepoDetail, RepoMetrics } from "@/lib/types";
import { formatStat, formatDelta } from "@/lib/utils";

const COLORS = ["var(--ember)", "var(--plasma)", "var(--gain)", "var(--dim)"];
const MAX = 4;

export function CompareClient() {
  const router = useRouter();
  const params = useSearchParams();

  const [ids, setIds] = useState<number[]>(() =>
    (params.get("ids") ?? "")
      .split(",")
      .map((s) => Number(s.trim()))
      .filter((n) => Number.isFinite(n) && n > 0)
      .slice(0, MAX)
  );
  const [pick, setPick] = useState("");

  // Keep URL in sync
  useEffect(() => {
    const sp = new URLSearchParams();
    if (ids.length) sp.set("ids", ids.join(","));
    router.replace(`/compare${sp.toString() ? `?${sp}` : ""}`, { scroll: false });
  }, [ids, router]);

  const repoQueries = useQueries({
    queries: ids.map((id) => ({
      queryKey: ["repo", id],
      queryFn: () => getRepository(id),
      staleTime: 5 * 60_000,
      retry: false,
    })),
  });
  const metricQueries = useQueries({
    queries: ids.map((id) => ({
      queryKey: ["repo-metrics", id],
      queryFn: () => getRepositoryMetrics(id, "90d"),
      staleTime: 5 * 60_000,
      retry: false,
    })),
  });

  const repos = repoQueries.map((q) => q.data).filter(Boolean) as RepoDetail[];
  const metrics = metricQueries.map((q) => q.data) as (RepoMetrics | undefined)[];

  // Picker search
  const { data: searchData } = useQuery({
    queryKey: ["compare-search", pick],
    queryFn: () => searchApi(pick, 6),
    enabled: pick.trim().length >= 2,
    staleTime: 30_000,
  });

  function add(id: number) {
    setPick("");
    setIds((cur) => (cur.includes(id) || cur.length >= MAX ? cur : [...cur, id]));
  }
  function removeId(id: number) {
    setIds((cur) => cur.filter((x) => x !== id));
  }

  const rows: { label: string; get: (r: RepoDetail) => string; ember?: boolean }[] = [
    { label: "Language", get: (r) => r.language ?? "—" },
    { label: "Stars", get: (r) => formatStat(r.latest_stars) },
    { label: "Forks", get: (r) => formatStat(r.latest_forks) },
    { label: "Stars / today", get: (r) => formatDelta(r.stars_gained_today) },
    { label: "Stars / week", get: (r) => formatDelta(r.stars_gained_week) },
    { label: "Momentum", get: (r) => String(Math.round(r.momentum_score)), ember: true },
  ];

  return (
    <div className="fade-up">
      <div className="kicker">Head to head</div>
      <h1 className="big">
        Compare, side by <span className="ember">side.</span>
      </h1>
      <p className="standfirst">
        Line up to four repositories — metrics and relative star-growth shape, overlaid. Add from
        search or link straight here with <span className="mono">?ids=</span>.
      </p>

      <div className="cmptop">
        <div className="cmppick">
          <input
            value={pick}
            onChange={(e) => setPick(e.target.value)}
            placeholder={ids.length >= MAX ? "Maximum of 4 repos" : "Add a repository…"}
            disabled={ids.length >= MAX}
          />
          {pick.trim().length >= 2 && searchData?.repos?.length ? (
            <div className="cmpdrop">
              {searchData.repos
                .filter((r) => !ids.includes(r.id))
                .slice(0, 6)
                .map((r) => (
                  <div key={r.id} className="cr" onClick={() => add(r.id)}>
                    <span className="cn">{r.full_name}</span>
                    <span className="cg">{formatDelta(r.stars_gained_week)}</span>
                  </div>
                ))}
            </div>
          ) : null}
        </div>
        <div className="cmpchips">
          {repos.map((r, i) => (
            <span key={r.id} className="cmpchip">
              <i style={{ width: 10, height: 10, borderRadius: "50%", background: COLORS[i], display: "inline-block" }} />
              {r.name}
              <button onClick={() => removeId(r.id)} title="Remove">
                ✕
              </button>
            </span>
          ))}
        </div>
      </div>

      {ids.length === 0 ? (
        <div className="note" style={{ marginTop: 30 }}>
          Add repositories above to compare them. Tip: open any repo and press{" "}
          <b style={{ color: "var(--ember)" }}>+ Compare</b>.
        </div>
      ) : (
        <>
          <div className="chartcard" style={{ marginTop: 28 }}>
            <h4>
              Relative star growth <span>window-normalized · 90 days</span>
            </h4>
            <GrowthOverlay metrics={metrics} />
            <div className="cmplegend">
              {repos.map((r, i) => (
                <span key={r.id}>
                  <i style={{ background: COLORS[i] }} />
                  {r.name}
                </span>
              ))}
            </div>
          </div>

          <table className="cmptable">
            <thead>
              <tr>
                <th>Metric</th>
                {repos.map((r) => (
                  <th key={r.id}>{r.full_name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.label}>
                  <td className="lbl">{row.label}</td>
                  {repos.map((r) => (
                    <td key={r.id} className={row.ember ? "e" : ""}>
                      {row.get(r)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <div className="foot">
        <div className="fb">{ids.length} / {MAX} repositories</div>
        <div className="fm">Copy the URL to share this comparison</div>
      </div>
    </div>
  );
}

function GrowthOverlay({ metrics }: { metrics: (RepoMetrics | undefined)[] }) {
  const w = 640;
  const h = 240;
  const pad = 10;

  const series = metrics.map((m) => (m?.daily ?? []).map((d) => d.stars_total));
  const maxLen = Math.max(1, ...series.map((s) => s.length));
  const hasAny = series.some((s) => s.length > 2);

  if (!hasAny) {
    return <div className="note" style={{ margin: 0 }}>No metric history yet for these repositories.</div>;
  }

  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: "auto" }}>
      {series.map((s, i) => {
        if (s.length < 2) return null;
        const mn = Math.min(...s);
        const mx = Math.max(...s);
        const range = mx - mn || 1;
        const X = (idx: number) => pad + (idx / (maxLen - 1)) * (w - pad * 2);
        const Y = (v: number) => h - pad - ((v - mn) / range) * (h - pad * 2);
        const d = s.map((v, idx) => `${idx ? "L" : "M"}${X(idx).toFixed(1)} ${Y(v).toFixed(1)}`).join(" ");
        return (
          <path
            key={i}
            d={d}
            fill="none"
            stroke={COLORS[i]}
            strokeWidth="2"
            strokeLinejoin="round"
            style={{ strokeDasharray: 4000, strokeDashoffset: 4000, animation: `draw 1.6s var(--ease) ${i * 0.15}s forwards` }}
          />
        );
      })}
    </svg>
  );
}
