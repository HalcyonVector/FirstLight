"use client";

import { useId, useState } from "react";
import { formatStat } from "@/lib/utils";

// ─── Inline SVG charts with a hover read-out (date + value) ──────────────────

interface ChartProps {
  values: number[];
  /** One label per value (usually a date), shown in the hover read-out. */
  labels?: string[];
  format?: (v: number) => string;
}

const fmtDefault = (v: number) => formatStat(Math.round(v));

/** Index of the point nearest the pointer, given the plot's horizontal span. */
function nearestIndex(e: React.MouseEvent<SVGSVGElement>, n: number, w: number, pad: number) {
  const rect = e.currentTarget.getBoundingClientRect();
  const x = ((e.clientX - rect.left) / rect.width) * w;
  const t = (x - pad) / (w - pad * 2);
  return Math.max(0, Math.min(n - 1, Math.round(t * (n - 1))));
}

function ReadOut({ label, value }: { label?: string; value: string }) {
  return (
    <div className="chartread">
      {label && <span>{label}</span>}
      <b>{value}</b>
    </div>
  );
}

export function AreaChart({ values, labels, format = fmtDefault }: ChartProps) {
  const gid = useId();
  const [hover, setHover] = useState<number | null>(null);
  const w = 560;
  const h = 220;
  const pad = 8;
  const mx = Math.max(...values);
  const mn = Math.min(...values);
  const range = mx - mn || 1;
  const X = (i: number) => pad + (i / (values.length - 1)) * (w - pad * 2);
  const Y = (v: number) => h - pad - ((v - mn) / range) * (h - pad * 2 - 14);
  const line = values.map((v, i) => `${i ? "L" : "M"}${X(i).toFixed(1)} ${Y(v).toFixed(1)}`).join(" ");
  const area = `${line} L${X(values.length - 1).toFixed(1)} ${h} L${X(0).toFixed(1)} ${h} Z`;
  const shown = hover ?? values.length - 1;

  return (
    <div className="chartwrap">
      <ReadOut label={labels?.[shown]} value={format(values[shown])} />
      <svg
        viewBox={`0 0 ${w} ${h}`}
        style={{ width: "100%", height: "auto" }}
        onMouseMove={(e) => setHover(nearestIndex(e, values.length, w, pad))}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="var(--ember)" stopOpacity="0.38" />
            <stop offset="1" stopColor="var(--ember)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill={`url(#${gid})`} />
        <path
          d={line}
          fill="none"
          stroke="var(--ember)"
          strokeWidth="2"
          strokeLinejoin="round"
          style={{ strokeDasharray: 3000, strokeDashoffset: 3000, animation: "draw 1.8s var(--ease) forwards" }}
        />
        {hover !== null && (
          <line x1={X(hover)} x2={X(hover)} y1={0} y2={h} stroke="var(--rule2)" strokeDasharray="3 3" />
        )}
        <circle cx={X(shown).toFixed(1)} cy={Y(values[shown]).toFixed(1)} r="4" fill="var(--ember)" />
      </svg>
    </div>
  );
}

export function BarChart({ values, labels, format = fmtDefault }: ChartProps) {
  const [hover, setHover] = useState<number | null>(null);
  const w = 560;
  const h = 130;
  const pad = 8;
  const mx = Math.max(...values, 1);
  const gap = 2;
  const bw = (w - pad * 2) / values.length - gap;
  const shown = hover ?? values.length - 1;

  return (
    <div className="chartwrap">
      <ReadOut label={labels?.[shown]} value={format(values[shown])} />
      <svg
        viewBox={`0 0 ${w} ${h}`}
        style={{ width: "100%", height: "auto" }}
        onMouseMove={(e) => setHover(nearestIndex(e, values.length, w, pad))}
        onMouseLeave={() => setHover(null)}
      >
        {values.map((v, i) => {
          const bh = (Math.max(v, 0) / mx) * (h - 16);
          return (
            <rect
              key={i}
              x={(pad + i * (bw + gap)).toFixed(1)}
              y={(h - bh).toFixed(1)}
              width={bw.toFixed(1)}
              height={bh.toFixed(1)}
              rx="1.5"
              fill={i === hover ? "var(--fg)" : "var(--ember)"}
              opacity={i === hover ? 1 : (0.35 + (v / mx) * 0.6).toFixed(2)}
            >
              <animate attributeName="height" from="0" to={bh.toFixed(1)} dur="0.7s" begin={`${(i * 0.02).toFixed(2)}s`} fill="freeze" />
              <animate attributeName="y" from={h} to={(h - bh).toFixed(1)} dur="0.7s" begin={`${(i * 0.02).toFixed(2)}s`} fill="freeze" />
            </rect>
          );
        })}
      </svg>
    </div>
  );
}

/** "2026-10-14" → "Oct 14" */
export function shortDate(iso: string): string {
  return new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}
