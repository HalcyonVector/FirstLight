import { ImageResponse } from "next/og";
import { getCategoryTrend } from "@/lib/api";
import { formatStat } from "@/lib/utils";
import { OG, OG_SIZE, OgFrame, ogSpark } from "@/lib/og";

export const runtime = "nodejs";
export const alt = "Category momentum and top repositories";
export const size = OG_SIZE;
export const contentType = "image/png";
export const revalidate = 3600;

export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const cat = await getCategoryTrend(slug, "30d").catch(() => null);

  if (!cat) {
    return new ImageResponse(
      (
        <OgFrame kicker="Category">
          <div style={{ display: "flex", marginTop: 80, fontSize: 64, fontWeight: 800 }}>Category not found</div>
        </OgFrame>
      ),
      size
    );
  }

  const spark = ogSpark(cat.snapshots.map((s) => s.momentum_score), 560, 220);
  const top = cat.top_repos.slice(0, 4);

  return new ImageResponse(
    (
      <OgFrame kicker={`${cat.radar_status} category`}>
        <div style={{ display: "flex", fontSize: 76, fontWeight: 800, marginTop: 34 }}>{cat.category.name}</div>
        <div style={{ display: "flex", flex: 1, gap: 48, marginTop: 24 }}>
          <div style={{ display: "flex", flexDirection: "column", width: 560 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 14 }}>
              <div style={{ display: "flex", fontSize: 96, fontWeight: 800, color: OG.ember }}>
                {Math.round(cat.current_momentum)}
              </div>
              <div style={{ display: "flex", fontSize: 24, color: OG.dim2 }}>momentum</div>
            </div>
            {spark && (
              <svg width="560" height="220" viewBox="0 0 560 220">
                <path d={spark.area} fill={OG.ember} fillOpacity="0.18" />
                <path d={spark.line} fill="none" stroke={OG.ember} strokeWidth="4" />
              </svg>
            )}
          </div>
          <div style={{ display: "flex", flexDirection: "column", flex: 1 }}>
            {top.map((r, i) => (
              <div
                key={r.id}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  borderBottom: `1px solid ${OG.rule}`,
                  padding: "14px 0",
                  fontSize: 28,
                }}
              >
                <div style={{ display: "flex" }}>
                  <span style={{ color: OG.dim2, marginRight: 14 }}>{i + 1}</span>
                  {r.name.slice(0, 22)}
                </div>
                <div style={{ display: "flex", color: OG.gain }}>+{formatStat(r.stars_gained_week)}</div>
              </div>
            ))}
          </div>
        </div>
      </OgFrame>
    ),
    size
  );
}
