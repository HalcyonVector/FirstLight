import type { ChartMarker } from "@/components/shared/Charts";
import type { DailyMetric, Release } from "./types";
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
