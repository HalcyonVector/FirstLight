import { ImageResponse } from "next/og";
import { getRepository, getRepositoryMetrics } from "@/lib/api";
import { formatStat } from "@/lib/utils";
import { OG, OG_SIZE, OgFrame, ogSpark } from "@/lib/og";

export const runtime = "nodejs";
export const alt = "Repository momentum and star growth";
export const size = OG_SIZE;
export const contentType = "image/png";
// Data refreshes every 6h; an hour of edge caching keeps renders (and API hits) rare.
export const revalidate = 3600;

export default async function Image({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [repo, metrics] = await Promise.all([
    getRepository(Number(id)).catch(() => null),
    getRepositoryMetrics(Number(id), "30d").catch(() => null),
  ]);

  if (!repo) {
    return new ImageResponse(
      (
        <OgFrame kicker="Repository">
          <div style={{ display: "flex", marginTop: 80, fontSize: 64, fontWeight: 800 }}>Repository not found</div>
        </OgFrame>
      ),
      size
    );
  }

  const spark = ogSpark((metrics?.daily ?? []).map((d) => d.stars_total), 1072, 140);
  const desc = (repo.description ?? "").slice(0, 90) + ((repo.description?.length ?? 0) > 90 ? "…" : "");

  return new ImageResponse(
    (
      <OgFrame kicker={repo.lifecycle ? `${repo.lifecycle} · ${repo.language ?? "repo"}` : repo.language ?? "Repository"}>
        <div style={{ display: "flex", flexDirection: "column", marginTop: 34 }}>
          <div style={{ display: "flex", fontSize: 30, color: OG.dim }}>{repo.owner} /</div>
          <div style={{ display: "flex", fontSize: 72, fontWeight: 800, lineHeight: 1.05 }}>{repo.name}</div>
          {desc && <div style={{ display: "flex", fontSize: 28, color: OG.dim, marginTop: 10 }}>{desc}</div>}
        </div>
        <div style={{ display: "flex", flex: 1, alignItems: "flex-end", marginTop: 16 }}>
          {spark && (
            <svg width="1072" height="140" viewBox="0 0 1072 140">
              <path d={spark.area} fill={OG.ember} fillOpacity="0.18" />
              <path d={spark.line} fill="none" stroke={OG.ember} strokeWidth="4" />
            </svg>
          )}
        </div>
        <div style={{ display: "flex", gap: 56, borderTop: `1px solid ${OG.rule}`, paddingTop: 18, marginTop: 8 }}>
          <Stat v={String(Math.round(repo.momentum_score))} l="momentum" ember />
          <Stat v={`+${formatStat(repo.stars_gained_week)}`} l="stars this week" />
          <Stat v={formatStat(repo.latest_stars)} l="total stars" />
        </div>
      </OgFrame>
    ),
    size
  );
}

function Stat({ v, l, ember }: { v: string; l: string; ember?: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
      <div style={{ display: "flex", fontSize: 46, fontWeight: 800, color: ember ? OG.ember : OG.fg }}>{v}</div>
      <div style={{ display: "flex", fontSize: 22, color: OG.dim2 }}>{l}</div>
    </div>
  );
}
