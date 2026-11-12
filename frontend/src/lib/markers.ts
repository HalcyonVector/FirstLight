import type { ChartMarker } from "@/components/shared/Charts";
import type { DailyMetric, Release, SpikeCause, StarSpike } from "./types";
import { formatStat } from "./utils";

const MILESTONES = [100, 500, 1_000, 2_500, 5_000, 10_000, 25_000, 50_000, 100_000, 250_000];

/** Mark each release on the day it was published (skipping releases outside the range). */
export function releaseMarkers(daily: Pick<DailyMetric, "date">[], releases: Release[]): ChartMarker[] {
  if (daily.length < 2) return [];
  const first = daily[0].date.slice(0, 10);
  const out: ChartMarker[] = [];
  for (const r of releases) {
    if (r.prerelease) continue;
    const day = r.published_at.slice(0, 10);
    if (day < first) continue;
    const index = daily.findIndex((d) => d.date.slice(0, 10) >= day);
    if (index >= 0) out.push({ index, label: `Released ${r.tag}`, kind: "release" });
  }
  return out;
}

/** Mark the day a repo's total stars first crossed a round number. */
export function milestoneMarkers(daily: Pick<DailyMetric, "stars_total">[]): ChartMarker[] {
  const out: ChartMarker[] = [];
  for (let i = 1; i < daily.length; i++) {
    const prev = daily[i - 1].stars_total;
    const cur = daily[i].stars_total;
    for (const m of MILESTONES) {
      if (prev > 0 && prev < m && cur >= m) {
        out.push({ index: i, label: `Crossed ${formatStat(m)} ★`, kind: "milestone" });
      }
    }
  }
  return out;
}

export const CAUSE_LABEL: Record<SpikeCause["kind"], string> = {
  hn: "Hacker News",
  lobsters: "Lobsters",
  bluesky: "Bluesky",
  release: "Release",
};

/** "412 points · 120 comments", or "90 likes · 12 reposts" for Bluesky; "" for releases. */
export function causeStats(c: SpikeCause): string {
  if (c.kind === "release") return "";
  const [a, b] = c.kind === "bluesky" ? ["likes", "reposts"] : ["points", "comments"];
  return `${formatStat(c.points ?? 0)} ${a} · ${formatStat(c.comments ?? 0)} ${b}`;
}

/** One line naming what caused a spike: "Hacker News · 412 points", "Released v2.0", or the jump itself. */
export function spikeCauseLine(s: StarSpike): string {
  for (const kind of ["hn", "lobsters", "bluesky"] as const) {
    const c = s.causes.find((x) => x.kind === kind);
    if (c) return `${CAUSE_LABEL[kind]} · ${formatStat(c.points ?? 0)} ${kind === "bluesky" ? "likes" : "points"}`;
  }
  const rel = s.causes.find((c) => c.kind === "release");
  if (rel) return `Released ${rel.title}`;
  return `+${formatStat(s.gain)} stars in a day`;
}

/** Mark each star spike on its day, labelled with its cause when one was found. */
export function spikeMarkers(daily: Pick<DailyMetric, "date">[], spikes: StarSpike[]): ChartMarker[] {
  const out: ChartMarker[] = [];
  for (const s of spikes) {
    const index = daily.findIndex((d) => d.date.slice(0, 10) === s.date.slice(0, 10));
    if (index >= 0) out.push({ index, label: `+${formatStat(s.gain)} ★ · ${spikeCauseLine(s)}`, kind: "spike" });
  }
  return out;
}
