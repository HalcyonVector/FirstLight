"use client";

import Link from "next/link";
import { TrendsViewTabs } from "@/components/trends/TrendsClient";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getRadar } from "@/lib/api";
import type { RadarCategory } from "@/lib/types";
import { formatDelta } from "@/lib/utils";

export function RadarClient() {
  const { data, isLoading } = useQuery({ queryKey: ["radar"], queryFn: getRadar, staleTime: 5 * 60_000 });

  const points: RadarCategory[] = useMemo(() => {
    if (!data) return [];
    return [...data.rising, ...data.stable, ...data.declining]
      .sort((a, b) => b.momentum_score - a.momentum_score)
      .slice(0, 12);
  }, [data]);

  return (
    <div className="fade-up">
      <div className="kicker">Technology Radar · live</div>
      <h1 className="big">
        The <span className="ember">radar.</span>
      </h1>
      <p className="standfirst">
        One glance: what&apos;s accelerating, what&apos;s holding, what&apos;s fading. Distance from
        center is momentum; the dashed ring is the 65-point breakout line.
      </p>
      <TrendsViewTabs active="radar" />

      <div className="radarwrap">
        <div>
          <RadarChart points={points} />
        </div>
        <div>
          <div className="note" style={{ marginTop: 0 }}>
            Rising categories crossed +5 momentum week-over-week and sit above 65. Declining fell
            below 35 or dropped more than five points. Everything between is holding station.
          </div>
        </div>
      </div>

      <div className="rails">
        <Rail title="Rising" mark="▲" cls="r" items={data?.rising ?? []} loading={isLoading && !data} />
        <Rail title="Stable" mark="—" cls="s" items={data?.stable ?? []} loading={isLoading && !data} />
        <Rail title="Declining" mark="▼" cls="d" items={data?.declining ?? []} loading={isLoading && !data} />
      </div>

      <div className="foot">
        <div className="fb">{data?.as_of ? `As of ${data.as_of}` : "Live radar"}</div>
        <div className="fm">Recomputed after every ingestion cycle</div>
      </div>
    </div>
  );
}

function RadarChart({ points }: { points: RadarCategory[] }) {
  const cx = 200;
  const cy = 200;
  const R = 160;
  const n = points.length || 1;

  const status = (c: RadarCategory): "rising" | "declining" | "stable" => {
    if (c.momentum_score >= 65 && c.change_vs_last_week > 5) return "rising";
    if (c.momentum_score < 35 || c.change_vs_last_week < -5) return "declining";
    return "stable";
  };
  const color = (c: RadarCategory) =>
    status(c) === "rising" ? "var(--gain)" : status(c) === "declining" ? "var(--loss)" : "var(--dim)";

  const poly = points
    .map((c, i) => {
      const a = (i / n) * Math.PI * 2 - Math.PI / 2;
      const rr = (c.momentum_score / 100) * R;
      return `${(cx + Math.cos(a) * rr).toFixed(1)},${(cy + Math.sin(a) * rr).toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg className="radarsvg" viewBox="0 0 400 400" role="img" aria-label="Technology momentum radar">
      {[40, 80, 120, 160].map((r) => (
        <circle key={r} cx={cx} cy={cy} r={r} fill="none" stroke="var(--rule)" strokeWidth="1" />
      ))}
      <circle
        cx={cx}
        cy={cy}
        r={(65 / 100) * R}
        fill="none"
        stroke="var(--ember)"
        strokeWidth="1.4"
        strokeDasharray="3 4"
        opacity="0.7"
      />
      {points.length > 2 && <polygon points={poly} fill="var(--aur1)" stroke="var(--ember)" strokeWidth="1" opacity="0.5" />}
      {points.map((c, i) => {
        const a = (i / n) * Math.PI * 2 - Math.PI / 2;
        const rr = (c.momentum_score / 100) * R;
        const x = cx + Math.cos(a) * rr;
        const y = cy + Math.sin(a) * rr;
        const lx = cx + Math.cos(a) * (R + 14);
        const ly = cy + Math.sin(a) * (R + 14);
        const anchor = Math.cos(a) < -0.3 ? "end" : Math.cos(a) > 0.3 ? "start" : "middle";
        return (
          <g key={c.category.id}>
            <line
              x1={cx}
              y1={cy}
              x2={(cx + Math.cos(a) * R).toFixed(1)}
              y2={(cy + Math.sin(a) * R).toFixed(1)}
              stroke="var(--rule)"
              strokeWidth="0.6"
            />
            <circle cx={x.toFixed(1)} cy={y.toFixed(1)} r="5" fill={color(c)}>
              <animate attributeName="r" values="3;6;3" dur="2.6s" begin={`${i * 0.2}s`} repeatCount="indefinite" />
            </circle>
            <text
              x={lx.toFixed(1)}
              y={ly.toFixed(1)}
              fill="var(--dim)"
              fontSize="8.5"
              fontFamily="var(--font-mono), monospace"
              textAnchor={anchor}
              dominantBaseline="middle"
            >
              {c.category.name.split(" ")[0]}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function Rail({
  title,
  mark,
  cls,
  items,
  loading,
}: {
  title: string;
  mark: string;
  cls: "r" | "s" | "d";
  items: RadarCategory[];
  loading: boolean;
}) {
  return (
    <div className={`rail ${cls}`}>
      <h4>
        <span>{title}</span>
        <span>{mark}</span>
      </h4>
      {loading
        ? Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="skel" style={{ height: 42, marginBottom: 8 }} />
          ))
        : items.map((c) => (
            <Link key={c.category.id} className="ri" href={`/trends/${c.category.slug}`}>
              <div className="rn">{c.category.name}</div>
              <div className="rm">
                {Math.round(c.momentum_score)} momentum · {formatDelta(c.change_vs_last_week)} wow ·{" "}
                {c.repo_count.toLocaleString()} repos
              </div>
            </Link>
          ))}
      {!loading && !items.length && <div className="rm" style={{ color: "var(--dim2)", padding: "12px 0" }}>None</div>}
    </div>
  );
}
