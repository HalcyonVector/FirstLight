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
