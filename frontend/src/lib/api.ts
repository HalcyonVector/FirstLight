import type {
  AskResult,
  ExplainedSpike,
  ForUserResult,
  HypeData,
  StarCheck,
  CallsResponse,
  CategoryMomentum,
  DigestData,
  ShippedRelease,
  CategoryTrendDetail,
  DashboardData,
  PaginatedRepos,
  RadarData,
  RepoCard,
  RepoDetail,
  RepoMetrics,
  SearchResult,
} from "./types";

export interface TrendsResponse {
  categories: CategoryMomentum[];
  period: string;
}

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API = `${BASE_URL}/api/v1`;

async function fetchJSON<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const url = new URL(`${API}${path}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
    });
  }

  const res = await fetch(url.toString(), {
    next: { revalidate: 60 },
    headers: { "Content-Type": "application/json" },
  });

  if (!res.ok) {
    const error = await res.text();
    throw new Error(`API error ${res.status}: ${error}`);
  }

  return res.json() as Promise<T>;
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`API error ${res.status}: ${error}`);
  }
  return res.json() as Promise<T>;
}

// ─── Web Push ─────────────────────────────────────────────────────────────────
export interface VapidInfo {
  public_key: string;
  enabled: boolean;
}
export interface PushSubscribeBody {
  endpoint: string;
  keys: { p256dh: string; auth: string };
  repo_ids: number[];
  threshold: number;
}
export const getVapidPublicKey = (): Promise<VapidInfo> =>
  fetch(`${API}/push/vapid-public-key`).then((r) => r.json() as Promise<VapidInfo>);
export const subscribePush = (body: PushSubscribeBody) =>
  postJSON<{ status: string }>("/push/subscribe", body);
export const unsubscribePush = (endpoint: string) =>
  postJSON<{ status: string }>("/push/unsubscribe", { endpoint });

// ─── Dashboard ────────────────────────────────────────────────────────────────
export const getDashboard = (): Promise<DashboardData> =>
  fetchJSON<DashboardData>("/dashboard");

// ─── Repositories ────────────────────────────────────────────────────────────
export const getRepositories = (params?: {
  sort?: string;
  language?: string;
  category?: string;
  page?: number;
  limit?: number;
}): Promise<PaginatedRepos> =>
  fetchJSON<PaginatedRepos>("/repositories", params as Record<string, string | number>);

export const getRepository = (id: number): Promise<RepoDetail> =>
  fetchJSON<RepoDetail>(`/repositories/${id}`);

export const getRepositoryMetrics = (id: number, period = "30d"): Promise<RepoMetrics> =>
  fetchJSON<RepoMetrics>(`/repositories/${id}/metrics`, { period });

export const getSimilarRepos = (id: number): Promise<{ similar: RepoCard[] }> =>
  fetchJSON<{ similar: RepoCard[] }>(`/repositories/${id}/similar`);

// ─── Trends ──────────────────────────────────────────────────────────────────
export const getTrends = (period = "7d"): Promise<TrendsResponse> =>
  fetchJSON<TrendsResponse>("/trends", { period });

export const getCategoryTrend = (slug: string, period = "30d"): Promise<CategoryTrendDetail> =>
  fetchJSON<CategoryTrendDetail>(`/trends/${slug}`, { period });

export const getRadar = (): Promise<RadarData> =>
  fetchJSON<RadarData>("/trends/radar");

// ─── Search ──────────────────────────────────────────────────────────────────
export const search = (q: string, limit = 20, language?: string): Promise<SearchResult> =>
  fetchJSON<SearchResult>("/search", language ? { q, limit, language } : { q, limit });

// ─── Analytics ───────────────────────────────────────────────────────────────
export interface LanguageStat {
  language: string;
  repo_count: number;
  avg_momentum: number;
  stars_gained_week: number;
  total_stars: number;
}
export const getLanguages = (): Promise<{ languages: LanguageStat[] }> =>
  fetchJSON<{ languages: LanguageStat[] }>("/analytics/languages");
export const getSparklines = (ids: number[]): Promise<{ sparklines: Record<string, number[]> }> =>
  fetchJSON<{ sparklines: Record<string, number[]> }>("/analytics/sparklines", {
    ids: ids.join(","),
  });

// ─── Breakouts (new & accelerating repos) ──────────────────────────────────────
export interface Breakout {
  id: number;
  full_name: string;
  name: string;
  language: string | null;
  latest_stars: number;
  stars_gained_week: number;
  momentum_score: number;
  age_days: number | null;
  verdict?: string | null;
}
export const getBreakouts = (): Promise<{ breakouts: Breakout[] }> =>
  fetchJSON<{ breakouts: Breakout[] }>("/analytics/breakouts");

// ─── Signals: breakout calls, releases, digest, ask ────────────────────────────
export const getCalls = (): Promise<CallsResponse> => fetchJSON<CallsResponse>("/calls");
export const getReleases = (ids: number[], days = 30): Promise<{ releases: ShippedRelease[] }> =>
  fetchJSON<{ releases: ShippedRelease[] }>("/releases", { ids: ids.join(","), days });
export const getDigest = (): Promise<DigestData> => fetchJSON<DigestData>("/digest");
export const ask = (q: string): Promise<AskResult> => fetchJSON<AskResult>("/ask", { q });
export const getSpikes = (days = 7): Promise<{ spikes: ExplainedSpike[] }> =>
  fetchJSON<{ spikes: ExplainedSpike[] }>("/spikes", { days });
export const getHype = (): Promise<HypeData> => fetchJSON<HypeData>("/hype");
export const getStarChecks = (ids: number[]): Promise<{ checks: Record<string, StarCheck> }> =>
  fetchJSON<{ checks: Record<string, StarCheck> }>("/star-checks", { ids: ids.join(",") });

/** The GitHub-stars radar. Errors carry the API's own message (unknown user, paused for today). */
export async function getForUser(login: string): Promise<ForUserResult> {
  const url = new URL(`${API}/for-user`);
  url.searchParams.set("login", login);
  const res = await fetch(url.toString());
  if (!res.ok) {
    let detail = "Couldn't look that up right now.";
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<ForUserResult>;
}
