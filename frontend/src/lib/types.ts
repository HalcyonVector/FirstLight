// ─── Core types matching API responses ────────────────────────────────────────

export interface Category {
  id: number;
  name: string;
  slug: string;
  icon: string | null;
  color_hex: string | null;
}

export interface RepoCard {
  id: number;
  full_name: string;
  owner: string;
  name: string;
  description: string | null;
  language: string | null;
  latest_stars: number;
  stars_gained_today: number;
  stars_gained_week: number;
  latest_forks: number;
  momentum_score: number;
  topics: string[];
  categories: Category[];
  github_created_at: string | null;
  first_seen_at: string;
  verdict?: string | null;
  prev_rank?: number | null;
  lifecycle?: Lifecycle | null;
}

export type Lifecycle = "breakout" | "emerging" | "established" | "fading";

export interface Release {
  tag: string;
  name: string | null;
  published_at: string;
  url: string | null;
  prerelease: boolean;
  snippet: string | null;
}


export interface RepoBreakoutCall {
  called_on: string;
  stars_at_call: number;
  status: "open" | "hit" | "miss";
  hit_on: string | null;
  best_rank: number | null;
  /** 0-1 odds the call comes true, when the model existed at call time. */
  prob?: number | null;
}

export interface SpikeCause {
  kind: "hn" | "release";
  title: string;
  url: string | null;
  at: string | null;
  points?: number | null;
  comments?: number | null;
}

export interface StarSpike {
  date: string;
  gain: number;
  baseline: number;
  causes: SpikeCause[];
}

export interface HypeCurve {
  peak_on: string;
  peak_gain7: number;
  now_gain7: number;
  half_on: string | null;
  commits_peak: number;
  commits_now: number;
}

export interface DailyMetric {
  date: string;
  stars_total: number;
  forks_total: number;
  stars_gained: number;
  forks_gained: number;
  open_issues: number;
  contributors_count: number;
  commit_count_week: number;
}

export interface WeeklyMetric {
  week_start: string;
  stars_gained: number;
  forks_gained: number;
  new_contributors: number;
  commit_activity: number;
  momentum_score: number;
}

export interface Insight {
  id: number;
  title: string | null;
  summary: string | null;
  why_growing: string | null;
  what_it_solves: string | null;
  who_uses_it: string | null;
  tech_stack: string | null;
  verdict: string | null;
  competitors: string | null; // JSON string
  tags: string[];
  model_used?: string | null;
  generated_at: string;
}

export interface RepoDetail extends RepoCard {
  github_id: number;
  license: string | null;
  homepage_url: string | null;
  is_archived: boolean;
  is_fork: boolean;
  github_pushed_at: string | null;
  last_synced_at: string | null;
  latest_insight: Insight | null;
  momentum_breakdown?: MomentumBreakdown | null;
  star_check?: RepoStarCheck | null;
  releases?: Release[];
  breakout_call?: RepoBreakoutCall | null;
  spikes?: StarSpike[];
  hype?: HypeCurve | null;
}

export interface MomentumBreakdown {
  parts: Record<"stars" | "forks" | "contributors" | "commits" | "issues", number>;
  recency_multiplier: number;
  star_anomaly: boolean;
  week_start: string;
}

export interface RepoMetrics {
  repository_id: number;
  daily: DailyMetric[];
  weekly: WeeklyMetric[];
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

export interface CategoryMomentum {
  category: Category;
  momentum_score: number;
  stars_gained_week: number;
  repo_count: number;
  radar_status: "rising" | "stable" | "declining";
  top_repos: RepoCard[];
}

export interface DashboardData {
  top_gaining_today: RepoCard[];
  top_gaining_week: RepoCard[];
  trending_categories: CategoryMomentum[];
  ai_ecosystem: RepoCard[];
  new_entrants: RepoCard[];
  generated_at: string;
  data_since?: string | null;
  snapshot_days?: number;
}

// ─── Trends / Radar ──────────────────────────────────────────────────────────

export interface TrendSnapshot {
  date: string;
  total_stars: number;
  repo_count: number;
  stars_gained_week: number;
  momentum_score: number;
  radar_status: string;
}

export interface CategoryTrendDetail {
  category: Category;
  snapshots: TrendSnapshot[];
  top_repos: RepoCard[];
  current_momentum: number;
  radar_status: string;
}

export interface RadarCategory {
  category: Category;
  momentum_score: number;
  change_vs_last_week: number;
  repo_count: number;
  stars_gained_week: number;
}

export interface RadarData {
  rising: RadarCategory[];
  stable: RadarCategory[];
  declining: RadarCategory[];
  as_of: string;
}

// ─── Search ──────────────────────────────────────────────────────────────────

export interface SearchResult {
  repos: RepoCard[];
  categories: Category[];
  total_repos: number;
  took_ms: number;
}

// ─── Paginated ───────────────────────────────────────────────────────────────

export interface PaginatedRepos {
  items: RepoCard[];
  total: number;
  page: number;
  pages: number;
  limit: number;
}

// ─── Breakout calls ──────────────────────────────────────────────────────────

export interface BreakoutCall {
  id: number;
  full_name: string;
  description: string | null;
  language: string | null;
  called_on: string;
  stars_at_call: number;
  gain7_at_call: number;
  accel: number;
  latest_stars: number;
  stars_gained_week: number;
  momentum_score: number;
  status: "open" | "hit" | "miss";
  hit_on: string | null;
  best_rank: number | null;
  lead_days: number | null;
  prob?: number | null;
}

export interface CallRecord {
  total: number;
  hits: number;
  misses: number;
  open: number;
  hit_rate: number | null;
  avg_lead_days: number | null;
  hit_rank: number;
  window_days: number;
}

export interface CalibrationBin {
  lo: number;
  hi: number;
  n: number;
  predicted: number;
  actual: number;
}

export interface CallBacktest {
  test_n: number;
  test_from: string;
  test_to: string;
  bins: CalibrationBin[];
  brier: number;
  brier_base: number;
  skill: number | null;
  base_rate: number;
  top_third_rate: number;
}

export interface CallModelInfo {
  trained_on: string;
  samples: number;
  positives: number;
  base_rate: number;
  backtest: CallBacktest | null;
  /** False while the model doesn't beat the plain average; calls then show the average odds. */
  usable?: boolean;
}

export interface CallsResponse {
  calls: BreakoutCall[];
  record: CallRecord;
  live_calibration?: { n: number; bins: CalibrationBin[]; brier: number | null };
  model?: CallModelInfo | null;
}

export interface ExplainedSpike extends StarSpike {
  id: number;
  full_name: string;
  name: string;
  language: string | null;
}

export interface HypeSummary {
  n: number;
  fade_days: number | null;
  holding_pct: number;
  building_pct: number | null;
}

export interface HypeData {
  as_of: string | null;
  overall: HypeSummary | null;
  categories: (HypeSummary & { slug: string; name: string })[];
}

/** This week's forks per star against the typical fast grower's (GitHub hides stargazer lists). */
export interface StarCheck {
  verdict: "organic" | "mixed" | "suspicious";
  stars_week: number;
  forks_week: number;
  typical_ratio: number;
}

export interface RepoStarCheck extends StarCheck {
  checked_on: string;
}

export interface ForUserRepo extends RepoCard {
  shared_topics: string[];
  like: string | null;
}

export interface ForUserResult {
  login: string;
  starred: number;
  topics: string[];
  languages: string[];
  repos: ForUserRepo[];
}

// ─── Digest (This Week) ──────────────────────────────────────────────────────

export interface DigestRepo {
  id: number;
  full_name: string;
  description: string | null;
  language: string | null;
  category: string | null;
  latest_stars: number;
  stars_gained_today: number;
  stars_gained_week: number;
  momentum_score: number;
  github_created_at: string | null;
  backed_by_activity: boolean;
}

export interface ShippedRelease extends Release {
  id: number;
  full_name: string;
}

export interface DigestData {
  breakouts: DigestRepo[];
  movers: DigestRepo[];
  shipped: ShippedRelease[];
}

// ─── Ask ─────────────────────────────────────────────────────────────────────

export interface AskResult {
  question: string;
  understood: string;
  parsed_by: "ai" | "keywords";
  repos: RepoCard[];
  took_ms: number;
}
