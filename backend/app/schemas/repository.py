from datetime import datetime, date
from decimal import Decimal

from pydantic import BaseModel, Field, HttpUrl


# ─── Shared ────────────────────────────────────────────────────────────────────

class CategoryOut(BaseModel):
    id: int
    name: str
    slug: str
    icon: str | None
    color_hex: str | None

    class Config:
        from_attributes = True


# ─── Repository ────────────────────────────────────────────────────────────────

class RepoCard(BaseModel):
    """Compact representation used in lists and cards."""
    id: int
    full_name: str
    owner: str
    name: str
    description: str | None
    language: str | None
    latest_stars: int
    stars_gained_today: int
    stars_gained_week: int
    latest_forks: int
    momentum_score: float
    topics: list[str] = []
    categories: list[CategoryOut] = []
    github_created_at: datetime | None
    first_seen_at: datetime
    verdict: str | None = None
    prev_rank: int | None = None  # rank on yesterday's daily-gain board (dashboard only)

    class Config:
        from_attributes = True


class DailyMetricOut(BaseModel):
    date: date
    stars_total: int
    forks_total: int
    stars_gained: int
    forks_gained: int
    open_issues: int
    contributors_count: int
    commit_count_week: int

    class Config:
        from_attributes = True


class WeeklyMetricOut(BaseModel):
    week_start: date
    stars_gained: int
    forks_gained: int
    new_contributors: int
    commit_activity: int
    momentum_score: float

    class Config:
        from_attributes = True


class InsightOut(BaseModel):
    id: int
    title: str | None
    summary: str | None
    why_growing: str | None
    what_it_solves: str | None
    who_uses_it: str | None
    tech_stack: str | None
    verdict: str | None
    competitors: str | None  # JSON string
    tags: list[str] = []
    model_used: str | None = None
    generated_at: datetime

    class Config:
        from_attributes = True


class MomentumBreakdown(BaseModel):
    """Points each signal contributes to the score, before the recency multiplier."""
    parts: dict[str, float]
    recency_multiplier: float
    star_anomaly: bool
    week_start: date


class RepoDetail(BaseModel):
    """Full repository page data."""
    id: int
    github_id: int
    full_name: str
    owner: str
    name: str
    description: str | None
    language: str | None
    license: str | None
    topics: list[str] = []
    homepage_url: str | None
    is_archived: bool
    is_fork: bool
    latest_stars: int
    latest_forks: int
    stars_gained_today: int
    stars_gained_week: int
    momentum_score: float
    github_created_at: datetime | None
    github_pushed_at: datetime | None
    first_seen_at: datetime
    last_synced_at: datetime | None
    categories: list[CategoryOut] = []
    latest_insight: InsightOut | None = None
    momentum_breakdown: MomentumBreakdown | None = None

    class Config:
        from_attributes = True


class RepoMetricsResponse(BaseModel):
    repository_id: int
    daily: list[DailyMetricOut]
    weekly: list[WeeklyMetricOut]


# ─── Dashboard ─────────────────────────────────────────────────────────────────

class CategoryMomentum(BaseModel):
    category: CategoryOut
    momentum_score: float
    stars_gained_week: int
    repo_count: int
    radar_status: str
    top_repos: list[RepoCard] = []


class DashboardResponse(BaseModel):
    top_gaining_today: list[RepoCard]
    top_gaining_week: list[RepoCard]
    trending_categories: list[CategoryMomentum]
    ai_ecosystem: list[RepoCard]
    new_entrants: list[RepoCard]
    generated_at: datetime
    data_since: str | None = None
    snapshot_days: int = 0


# ─── Trends ────────────────────────────────────────────────────────────────────

class TrendSnapshotOut(BaseModel):
    date: date
    total_stars: int
    repo_count: int
    stars_gained_week: int
    momentum_score: float
    radar_status: str

    class Config:
        from_attributes = True


class CategoryTrendDetail(BaseModel):
    category: CategoryOut
    snapshots: list[TrendSnapshotOut]
    top_repos: list[RepoCard]
    current_momentum: float
    radar_status: str


class TrendsResponse(BaseModel):
    categories: list[CategoryMomentum]
    period: str


# ─── Radar ─────────────────────────────────────────────────────────────────────

class RadarCategory(BaseModel):
    category: CategoryOut
    momentum_score: float
    change_vs_last_week: float
    repo_count: int
    stars_gained_week: int


class RadarResponse(BaseModel):
    rising: list[RadarCategory]
    stable: list[RadarCategory]
    declining: list[RadarCategory]
    as_of: date


# ─── Search ────────────────────────────────────────────────────────────────────

class SearchResponse(BaseModel):
    repos: list[RepoCard]
    categories: list[CategoryOut]
    total_repos: int
    took_ms: int


# ─── Pagination ────────────────────────────────────────────────────────────────

class PaginatedRepos(BaseModel):
    items: list[RepoCard]
    total: int
    page: int
    pages: int
    limit: int
