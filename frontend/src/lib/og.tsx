// Shared pieces for the 1200×630 share images (next/og renders these at the edge).

export const OG_SIZE = { width: 1200, height: 630 };

export const OG = {
  bg: "#1c1712",
  panel: "#241d16",
  fg: "#efe7d8",
  dim: "#b6a893",
  dim2: "#7e6f5c",
  ember: "#ef9367",
  gain: "#8fc46b",
  rule: "#4a3f32",
};

/** Filled sparkline as an SVG path pair (line, area) in a w×h box. */
export function ogSpark(values: number[], w: number, h: number): { line: string; area: string } | null {
  if (values.length < 2) return null;
  const mx = Math.max(...values);
  const mn = Math.min(...values);
  const range = mx - mn || 1;
  const pts = values.map((v, i) => [(i / (values.length - 1)) * w, h - 6 - ((v - mn) / range) * (h - 12)]);
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  return { line, area: `${line} L${w} ${h} L0 ${h} Z` };
}

export function OgFrame({ kicker, children }: { kicker: string; children: React.ReactNode }) {
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        background: OG.bg,
        color: OG.fg,
        padding: "56px 64px",
        fontFamily: "serif",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          borderBottom: `3px solid ${OG.fg}`,
          paddingBottom: 18,
          fontSize: 26,
          fontWeight: 700,
        }}
      >
        <div style={{ display: "flex" }}>
          First<span style={{ color: OG.ember }}>Light</span>
        </div>
        <div style={{ display: "flex", fontSize: 20, color: OG.dim, letterSpacing: 3, textTransform: "uppercase" }}>
          {kicker}
        </div>
      </div>
      {children}
    </div>
  );
}
