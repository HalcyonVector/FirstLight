import { getRepository } from "@/lib/api";

// README badge: ![momentum](https://<site>/badge/<repo id>)
// Cached at the edge for an hour; the data itself only refreshes every 6 hours.
export const revalidate = 3600;

const LABEL = "momentum";
const CHAR_W = 6.5; // rough width of an 11px Verdana glyph

function color(score: number): string {
  if (score >= 65) return "#e8724a";
  if (score >= 40) return "#c99a2e";
  return "#7e6f5c";
}

function svg(value: string, fill: string): string {
  const lw = Math.round(LABEL.length * CHAR_W + 12);
  const vw = Math.round(value.length * CHAR_W + 12);
  const w = lw + vw;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="20" role="img" aria-label="${LABEL}: ${value}">
  <title>${LABEL}: ${value}</title>
  <clipPath id="r"><rect width="${w}" height="20" rx="3"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="${lw}" height="20" fill="#2b231a"/>
    <rect x="${lw}" width="${vw}" height="20" fill="${fill}"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11">
    <text x="${lw / 2}" y="14">${LABEL}</text>
    <text x="${lw + vw / 2}" y="14">${value}</text>
  </g>
</svg>`;
}

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let body: string;
  try {
    const repo = await getRepository(Number(id));
    const score = Math.round(repo.momentum_score);
    body = svg(`${score} / 100`, color(score));
  } catch {
    body = svg("unknown", "#7e6f5c");
  }
  return new Response(body, {
    headers: {
      "Content-Type": "image/svg+xml; charset=utf-8",
      "Cache-Control": "s-maxage=3600, stale-while-revalidate=21600",
    },
  });
}
