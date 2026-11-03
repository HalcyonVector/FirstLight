# FirstLight — Architecture & PRD

> **Stack**: Next.js 14 · FastAPI · PostgreSQL · Redis · Celery · Claude API  
> **Deployment**: Vercel (frontend) · Railway (backend) · Supabase (DB) · Upstash (Redis)

---

## 1. System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        USERS (Browser)                           │
└──────────────────────────────┬───────────────────────────────────┘
                               │ HTTPS
┌──────────────────────────────▼───────────────────────────────────┐
│              FRONTEND — Next.js 14 App Router (Vercel)           │
│  /          Dashboard — Bento layout, velocity charts            │
│  /repos/[id] Repository detail — growth chart, AI summary       │
│  /trends     Category momentum — radar scores, timelines        │
│  /radar      Technology radar — Rising / Stable / Declining      │
│  /search     Full-text + filter search                           │
└──────────────────────────────┬───────────────────────────────────┘
                               │ REST JSON  (≤500ms cached)
┌──────────────────────────────▼───────────────────────────────────┐
│              BACKEND — FastAPI (Railway)                          │
│  GET /api/v1/dashboard      Aggregated home feed                 │
│  GET /api/v1/repositories   Paginated repo list                  │
│  GET /api/v1/repositories/{id}  Repo detail + metrics           │
│  GET /api/v1/trends         Category trends                      │
│  GET /api/v1/radar          Technology radar data                │
│  GET /api/v1/search         Full-text search                     │
│  GET /api/v1/insights/{id}  AI-generated repo/category summary   │
└──────┬────────────────────────────────────────┬──────────────────┘
       │ SQLAlchemy async                        │ aioredis
┌──────▼────────┐                    ┌──────────▼──────────────────┐
│  PostgreSQL   │                    │         Redis               │
│  (Supabase)   │                    │  Cache + Celery Broker      │
│               │                    │  TTL: 5m dashboard          │
│  repos        │                    │       1h insights           │
│  daily_metrics│                    │       30s search            │
│  weekly_metrics                    └──────────┬──────────────────┘
│  categories   │                               │
│  trend_snaps  │                    ┌──────────▼──────────────────┐
│  insights     │                    │     Celery Workers           │
└───────────────┘                    │                             │
                                     │  ingest_trending_repos()    │
                                     │    → every 6h               │
                                     │  compute_trend_scores()     │
                                     │    → every 6h (after ingest)│
                                     │  generate_ai_insights()     │
                                     │    → daily, top 50 repos    │
                                     │  refresh_search_index()     │
                                     │    → every 12h              │
                                     └──────────┬──────────────────┘
                                                │
                                   ┌────────────▼───────────────────┐
                                   │       External APIs            │
                                   │  GitHub REST API (v3)          │
                                   │  GitHub GraphQL API (v4)       │
                                   │  Claude API (claude-sonnet)    │
                                   └────────────────────────────────┘
```

---

## 2. Database Schema (ER Diagram)

```
repositories
  id (PK)
  github_id (UNIQUE)
  owner
  name
  full_name (UNIQUE INDEX)
  description
  language
  license
  topics[]
  homepage_url
  default_branch
  is_archived
  is_fork
  github_created_at
  github_updated_at
  github_pushed_at
  first_seen_at
  last_synced_at
       │
       │ 1:N
       ▼
daily_metrics
  id (PK)
  repository_id (FK → repositories)
  date (UNIQUE with repo_id)
  stars_total
  stars_gained          ← computed: today - yesterday
  forks_total
  forks_gained
  watchers
  open_issues
  contributors_count
  commit_count_week
  releases_count
  created_at

       │
       │ 1:N
       ▼
weekly_metrics
  id (PK)
  repository_id (FK → repositories)
  week_start (UNIQUE with repo_id)
  stars_gained
  forks_gained
  new_contributors
  commit_activity
  momentum_score        ← composite velocity score 0–100
  created_at

repositories ──N:M──▶ technology_categories
  (via repository_categories)
    repository_id (FK)
    category_id (FK)
    confidence_score    ← 0.0–1.0 from keyword/topic matching

technology_categories
  id (PK)
  name
  slug (UNIQUE)
  description
  keywords[]
  parent_id (FK → self, for subcategories)
  icon
  color_hex

trend_snapshots
  id (PK)
  category_id (FK → technology_categories)
  date
  total_stars
  repo_count
  stars_gained_week
  stars_gained_month
  contributor_count
  momentum_score        ← aggregate of repo momentum in category
  radar_status          ← 'rising' | 'stable' | 'declining'
  (UNIQUE: category_id + date)

insight_reports
  id (PK)
  report_type           ← 'repository' | 'category' | 'weekly_digest'
  subject_id            ← repository_id or category_id
  period_start
  period_end
  title
  summary               ← 2-sentence executive summary
  why_growing           ← AI paragraph
  who_uses_it
  competitors           ← JSON array
  full_content          ← JSONB (full structured insight)
  model_used
  tokens_used
  generated_at
  expires_at            ← insights refreshed after 24h for top repos

organizations
  id (PK)
  github_id (UNIQUE)
  login
  name
  avatar_url
  public_repos_count
  followers
  github_created_at
```

**Key indexes:**
```sql
CREATE INDEX idx_daily_metrics_date ON daily_metrics(date DESC);
CREATE INDEX idx_daily_metrics_stars_gained ON daily_metrics(stars_gained DESC);
CREATE INDEX idx_repositories_language ON repositories(language);
CREATE INDEX idx_repositories_topics ON repositories USING GIN(topics);
CREATE INDEX idx_weekly_momentum ON weekly_metrics(momentum_score DESC);
CREATE INDEX idx_trend_snapshots_date ON trend_snapshots(date DESC, momentum_score DESC);
-- Full-text search
CREATE INDEX idx_repos_fts ON repositories USING GIN(
  to_tsvector('english', coalesce(name,'') || ' ' || coalesce(description,''))
);
```

---

## 3. API Design

All endpoints return JSON. Authentication is not required for Phase 1 (public read-only). Pagination uses `cursor`-based pagination for performance.

### Dashboard
```
GET /api/v1/dashboard
Response:
{
  "top_gaining_today": [RepoCard x10],
  "top_gaining_week": [RepoCard x10],
  "trending_categories": [CategoryMomentum x8],
  "ai_ecosystem": [RepoCard x5],  // filtered by AI categories
  "new_entrants": [RepoCard x5],  // first seen < 7 days, high velocity
  "generated_at": "ISO8601"
}
```

### Repositories
```
GET /api/v1/repositories
  ?sort=stars_gained_today|stars_gained_week|momentum_score|stars_total
  &language=Python
  &category=ai-agents
  &period=1d|7d|30d
  &page=1&limit=20
  → { items: [RepoCard], total, page, pages }

GET /api/v1/repositories/{id}
  → RepositoryDetail (full metadata + latest metrics + top insights)

GET /api/v1/repositories/{id}/metrics
  ?period=7d|30d|90d|1y
  → { daily: [DailyMetric], weekly: [WeeklyMetric] }

GET /api/v1/repositories/{id}/insights
  → InsightReport (AI-generated, cached 24h)
```

### Trends
```
GET /api/v1/trends
  ?period=7d|30d
  → { categories: [CategoryTrend sorted by momentum] }

GET /api/v1/trends/{category_slug}
  ?period=30d
  → { category, snapshots: [TrendSnapshot], top_repos: [RepoCard x10] }
```

### Radar
```
GET /api/v1/radar
  → {
      rising:   [CategoryRadar],   // momentum_score > 70, trending up
      stable:   [CategoryRadar],   // momentum_score 40–70
      declining:[CategoryRadar]    // momentum_score < 40, trending down
    }
```

### Search
```
GET /api/v1/search
  ?q=vector+database
  &type=repos|categories|topics
  &limit=20
  → { repos: [RepoCard], categories: [Category], took_ms: 45 }
```

### Insights
```
POST /api/v1/insights/generate
  Body: { subject_type: "repository", subject_id: 123 }
  → triggers background generation, returns job_id
  
GET /api/v1/insights/status/{job_id}
  → { status: "pending|complete|failed", insight?: InsightReport }
```

---

## 4. Momentum Score Algorithm

The `momentum_score` (0–100) is the core signal. Computed for each repository weekly:

```python
def compute_momentum_score(repo_metrics: WeeklyMetrics) -> float:
    # Normalize each signal to 0-1 using log scale to handle outliers
    star_velocity   = normalize_log(repo.stars_gained_week, p95=500)
    fork_velocity   = normalize_log(repo.forks_gained_week, p95=100)
    contributor_vel = normalize_log(repo.new_contributors, p95=20)
    commit_activity = normalize_log(repo.commit_count_week, p95=50)
    issue_activity  = normalize_log(repo.issues_opened_week, p95=30)

    # Recency bonus: repos < 30 days old get 1.2x multiplier
    recency_mult = 1.2 if repo.age_days < 30 else 1.0

    # Weighted composite
    score = (
        star_velocity   * 0.45 +
        fork_velocity   * 0.20 +
        contributor_vel * 0.20 +
        commit_activity * 0.10 +
        issue_activity  * 0.05
    ) * 100 * recency_mult

    return min(score, 100.0)
```

Category `momentum_score` = weighted avg of top-20 repos in category by star velocity.

Radar status classification:
- **Rising**: momentum_score ≥ 65 AND week-over-week score change > +5
- **Stable**: momentum_score 35–65 OR small change
- **Declining**: momentum_score < 35 OR week-over-week change < -5

---

## 5. GitHub Ingestion Pipeline

```
Every 6 hours (Celery beat):

1. ingest_trending_repos()
   ├── Fetch GitHub /search/repositories sorted by stars, updated today
   ├── Fetch predefined topic lists: ai-agents, mcp, llm, devtools, etc.
   ├── For each repo returned:
   │   ├── Upsert repositories table
   │   ├── Fetch contributor count via /repos/{owner}/{repo}/contributors?per_page=1
   │   ├── Fetch weekly commit activity via /repos/{owner}/{repo}/stats/commit_activity
   │   └── Insert daily_metrics row for today
   └── Rate limit: 5,000 req/hr authenticated → ~1,400 repos/cycle safely

2. compute_trend_scores()  (after ingest)
   ├── Compute stars_gained for each repo (today.stars - yesterday.stars)
   ├── Compute momentum_score per repo
   ├── Aggregate category trend_snapshots
   ├── Update radar_status per category
   └── Invalidate Redis cache keys

3. generate_ai_insights()  (daily, staggered)
   ├── Select top 50 repos by momentum_score without fresh insight
   ├── For each: call Claude API with structured prompt
   ├── Store result in insight_reports
   └── Set expires_at = now + 24h
```

**Rate limiting strategy:**
- GitHub unauthenticated: 60 req/hr → always use token
- GitHub authenticated: 5,000 req/hr → 1 req/720ms safe baseline
- Use exponential backoff on 429/403
- Track X-RateLimit-Remaining header
- Celery task priority queue: ingestion > analysis > insights

---

## 6. AI Insight Prompt Design

```
System: You are a developer intelligence analyst. Analyze GitHub repositories 
and produce structured, factual insights for software engineers.
Be specific, cite numbers. Never be vague. Max 3 sentences per section.

User:
Repository: {full_name}
Description: {description}
Language: {language}
Topics: {topics}
Stars total: {stars_total:,}
Stars this week: {stars_gained_week:,}
Stars this month: {stars_gained_month:,}
Forks: {forks:,}
Contributors: {contributors:,}
Created: {github_created_at}
Recent commits/week: {commit_count_week}
Category: {category_name}

Produce a JSON response with these keys:
{
  "why_growing": "...",        // Why is this repo gaining stars right now?
  "what_it_solves": "...",     // What problem does it solve?
  "who_uses_it": "...",        // Target audience and use cases
  "tech_stack": "...",         // Key technical decisions / architecture
  "competitors": ["repo1", "repo2"],  // 2-3 alternatives
  "verdict": "...",            // 1-sentence "should I care?" for a busy engineer
  "tags": ["tag1", "tag2"]     // 3-5 descriptive tags
}
```

---

## 7. Frontend Component Inventory

### Layout
| Component | Description |
|---|---|
| `AppShell` | Root layout: sidebar nav + top bar |
| `Sidebar` | Nav: Dashboard, Trends, Radar, Search |
| `TopBar` | Search input (⌘K), theme toggle |
| `CommandPalette` | Global search overlay (⌘K) |

### Dashboard
| Component | Description |
|---|---|
| `VelocityLeaderboard` | Top N repos by stars gained, with sparklines |
| `CategoryMomentumGrid` | Bento grid of category cards with score ring |
| `NewEntrantsPanel` | Repos < 7 days old with high velocity |
| `AIEcosystemFeed` | Live feed filtered to AI/ML categories |
| `StatsBar` | Global counts: total repos tracked, stars today |

### Charts
| Component | Description |
|---|---|
| `StarGrowthChart` | Area chart: cumulative stars over time |
| `VelocityChart` | Bar chart: daily stars gained |
| `MomentumSparkline` | 7-day mini sparkline for cards |
| `CategoryRadarChart` | Recharts RadarChart for category comparison |
| `ContributorGrowthChart` | Line chart: contributor count over time |

### Repository
| Component | Description |
|---|---|
| `RepoCard` | Summary card: name, language, description, sparkline, gained |
| `RepoDetailHeader` | Hero section: name, org, description, badges |
| `MetricsGrid` | 4-up stat tiles: stars, forks, contributors, issues |
| `InsightPanel` | AI-generated insight sections with skeleton loader |
| `CompetitorsList` | Linked list of competitor repos |

### Shared
| Component | Description |
|---|---|
| `LanguageBadge` | Colored dot + language name |
| `MomentumBadge` | Score ring with color (green/yellow/red) |
| `SkeletonCard` | Loading placeholder matching RepoCard shape |
| `EmptyState` | Illustrated empty states per context |
| `ErrorBoundary` | Graceful error UI with retry |

---

## 8. Design System

### Colors (CSS variables, dark-first)
```css
--bg-base:     #0a0a0f;   /* near-black */
--bg-surface:  #111118;   /* card surface */
--bg-elevated: #1a1a24;   /* hover/active */
--border:      #ffffff14; /* subtle divider */
--text-primary:#f0f0f8;
--text-muted:  #8888a0;
--accent-blue: #3b82f6;
--accent-green:#22c55e;
--accent-amber:#f59e0b;
--accent-red:  #ef4444;
--accent-purple:#a855f7;
```

### Typography
- **Font**: Geist (Next.js default) — clean, modern, excellent at small sizes
- **Mono**: Geist Mono — for stats and numbers
- **Scale**: 12 / 14 / 16 / 20 / 24 / 32 / 48

### Spacing
- Base unit: 4px
- Card padding: 16px / 24px
- Section gap: 24px / 32px

### Motion
```ts
// Framer Motion presets
export const fadeUp = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.2, ease: [0.16, 1, 0.3, 1] }
}
export const stagger = {
  animate: { transition: { staggerChildren: 0.05 } }
}
```

### Card Anatomy
```
┌─────────────────────────────────────────┐
│  ● Python    ★ +1,240 this week   [↗]  │  ← header row
│                                         │
│  owner / repo-name                      │  ← title (semibold)
│  Short description truncated to...      │  ← muted, 2 lines
│                                         │
│  ▁▂▃▄▅▆▇█  (sparkline 7d)    Score: 87 │  ← footer
└─────────────────────────────────────────┘
```

---

## 9. Technology Categories (Seed Data)

| Slug | Name | Keywords |
|---|---|---|
| `ai-agents` | AI Agents | agent, autonomous, agentic, tool-use, ai-agent |
| `mcp-servers` | MCP Servers | mcp, model-context-protocol |
| `llm-frameworks` | LLM Frameworks | llm, langchain, llamaindex, dspy |
| `coding-assistants` | Coding Assistants | copilot, code-completion, code-generation |
| `vector-databases` | Vector Databases | vector-db, embeddings, semantic-search |
| `ml-infra` | ML Infrastructure | mlops, training, inference, serving |
| `frontend-frameworks` | Frontend Frameworks | react, vue, svelte, solidjs |
| `backend-frameworks` | Backend Frameworks | fastapi, django, express, nest |
| `databases` | Databases | postgresql, sqlite, duckdb, clickhouse |
| `devtools` | Developer Tools | cli, developer-tools, productivity |
| `infrastructure` | Infrastructure | kubernetes, terraform, docker, iac |
| `security` | Security | security, vulnerability, pentest |
| `data-engineering` | Data Engineering | dbt, airflow, spark, data-pipeline |
| `observability` | Observability | tracing, metrics, logging, opentelemetry |
| `fintech` | Fintech | payments, finance, trading |

---

## 10. Testing Strategy

### Backend
| Layer | Tool | What |
|---|---|---|
| Unit | pytest | Services, score algorithms, transformers |
| Integration | pytest + testcontainers | DB queries, API routes with real Postgres |
| Mocks | respx | GitHub API responses |
| Load | locust | /dashboard and /search under 1,000 concurrent |

Key test cases:
- `momentum_score` returns 0–100 for all edge inputs
- `stars_gained` never negative (handle missing yesterday row)
- API returns 200 with empty data, not 500
- Cache hit returns identical response to DB hit
- Insight generation fails gracefully if Claude API down

### Frontend
| Layer | Tool | What |
|---|---|---|
| Component | Vitest + Testing Library | RepoCard, Charts render correctly |
| E2E | Playwright | Dashboard loads, search returns results |
| Visual | Chromatic | Component snapshot regression |

---

## 11. Deployment Plan

### Infrastructure
```
Vercel (frontend)
  - Auto-deploys from main branch
  - Edge network CDN
  - Environment: NEXT_PUBLIC_API_URL

Railway (backend)
  - FastAPI service: 1 instance, 512MB RAM
  - Celery worker service: 1 instance, 512MB RAM
  - Celery beat scheduler: 1 instance
  - Auto-deploys from main branch

Supabase (PostgreSQL)
  - Free tier: 500MB, sufficient for MVP
  - Connection pooling via pgBouncer

Upstash (Redis)
  - Serverless Redis, pay-per-request
  - Free tier: 10,000 commands/day
```

### Environment Variables
```bash
# Backend
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
GITHUB_TOKEN=ghp_...
ANTHROPIC_API_KEY=sk-ant-...
SECRET_KEY=...  # for future auth

# Frontend
NEXT_PUBLIC_API_URL=https://api.yourapp.com
```

### Rollout sequence
1. Deploy PostgreSQL (Supabase) → run schema.sql
2. Deploy backend to Railway → test /health endpoint
3. Trigger first manual ingestion run → verify data in DB
4. Deploy frontend to Vercel → connect to backend URL
5. Enable Celery beat scheduler → verify cron runs

---

## 12. Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| GitHub API rate limit exhausted | Medium | High | Authenticated token (5k/hr), backoff, stagger crons |
| GitHub changes API response schema | Low | High | Schema validation (Pydantic), alert on parse errors |
| Claude API cost runaway | Medium | Medium | Max tokens per insight, daily budget cap, cache 24h |
| Cold start latency (Railway) | High (free tier) | Medium | Keep-alive ping every 5min, or upgrade to $5/mo |
| DB schema migrations with live traffic | Medium | High | Alembic migrations, always additive in Phase 1 |
| Search slowness at scale | Low (MVP) | Medium | PostgreSQL FTS sufficient to 50k repos; add Typesense later |
| Supabase free tier storage limit | Low | Low | 500MB covers ~100k repos + 1 year metrics |
| Frontend bundle size | Low | Low | Dynamic imports for Recharts, route-level code splitting |

---

## 13. Phase Roadmap

### Phase 1 — MVP (Weeks 1–4)
- [ ] PostgreSQL schema + migrations
- [ ] GitHub ingestion worker (daily_metrics, trending repos)
- [ ] FastAPI: /dashboard, /repositories, /search
- [ ] Next.js: Dashboard, Repo detail, Search
- [ ] Recharts: StarGrowthChart, VelocityLeaderboard
- [ ] Redis caching on dashboard + search
- [ ] Deploy to Vercel + Railway

### Phase 2 — Trends (Weeks 5–7)
- [ ] Category classification (keyword matching + topic matching)
- [ ] Momentum score computation
- [ ] Trend snapshots aggregation
- [ ] /trends and /radar API endpoints
- [ ] TrendDiscovery page, TechnologyRadar page
- [ ] CategoryMomentumGrid component

### Phase 3 — AI Layer (Weeks 8–10)
- [ ] Claude API integration
- [ ] Insight generation worker
- [ ] /insights API endpoint
- [ ] InsightPanel component on Repo detail page
- [ ] Weekly digest generation (email or in-app)

### Phase 4 — Personalization (Weeks 11–14)
- [ ] User accounts (Supabase Auth)
- [ ] Watchlists (saved repos + categories)
- [ ] Email alerts (star velocity threshold)
- [ ] GitHub OAuth login
- [ ] Personalized feed
