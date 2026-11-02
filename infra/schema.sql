-- GitHub Trending Intelligence — PostgreSQL Schema
-- Run: psql $DATABASE_URL -f schema.sql

-- ============================================================
-- Extensions
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- trigram similarity for search

-- ============================================================
-- Organizations
-- ============================================================
CREATE TABLE organizations (
    id              BIGSERIAL PRIMARY KEY,
    github_id       BIGINT      UNIQUE NOT NULL,
    login           VARCHAR(255) UNIQUE NOT NULL,
    name            VARCHAR(255),
    avatar_url      TEXT,
    description     TEXT,
    public_repos    INT         DEFAULT 0,
    followers       INT         DEFAULT 0,
    github_created  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- Technology Categories
-- ============================================================
CREATE TABLE technology_categories (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) UNIQUE NOT NULL,
    slug        VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    keywords    TEXT[]       NOT NULL DEFAULT '{}',
    github_topics TEXT[]     NOT NULL DEFAULT '{}',
    icon        VARCHAR(50),          -- lucide icon name
    color_hex   VARCHAR(7),           -- e.g. #3b82f6
    parent_id   INT          REFERENCES technology_categories(id),
    sort_order  INT          DEFAULT 0,
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- ============================================================
-- Repositories
-- ============================================================
CREATE TABLE repositories (
    id                  BIGSERIAL   PRIMARY KEY,
    github_id           BIGINT      UNIQUE NOT NULL,
    owner               VARCHAR(255) NOT NULL,
    name                VARCHAR(255) NOT NULL,
    full_name           VARCHAR(511) UNIQUE NOT NULL,
    description         TEXT,
    language            VARCHAR(100),
    license             VARCHAR(100),
    topics              TEXT[]      NOT NULL DEFAULT '{}',
    homepage_url        TEXT,
    default_branch      VARCHAR(100) DEFAULT 'main',
    is_archived         BOOLEAN     DEFAULT FALSE,
    is_fork             BOOLEAN     DEFAULT FALSE,
    is_template         BOOLEAN     DEFAULT FALSE,
    open_graph_url      TEXT,
    -- GitHub timestamps
    github_created_at   TIMESTAMPTZ,
    github_updated_at   TIMESTAMPTZ,
    github_pushed_at    TIMESTAMPTZ,
    -- Tracking timestamps
    first_seen_at       TIMESTAMPTZ DEFAULT NOW(),
    last_synced_at      TIMESTAMPTZ,
    -- Derived/cached fields (updated by worker)
    latest_stars        INT         DEFAULT 0,
    latest_forks        INT         DEFAULT 0,
    latest_watchers     INT         DEFAULT 0,
    stars_gained_today  INT         DEFAULT 0,
    stars_gained_week   INT         DEFAULT 0,
    momentum_score      DECIMAL(5,2) DEFAULT 0,
    -- Timestamps
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    -- FK
    org_id              BIGINT      REFERENCES organizations(id)
);

-- ============================================================
-- Repository ↔ Category (many-to-many)
-- ============================================================
CREATE TABLE repository_categories (
    repository_id   BIGINT  NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    category_id     INT     NOT NULL REFERENCES technology_categories(id) ON DELETE CASCADE,
    confidence      DECIMAL(3,2) DEFAULT 1.0,   -- 0.0–1.0
    tagged_by       VARCHAR(20) DEFAULT 'auto',  -- 'auto' | 'manual'
    PRIMARY KEY (repository_id, category_id)
);

-- ============================================================
-- Daily Metrics
-- ============================================================
CREATE TABLE daily_metrics (
    id                  BIGSERIAL   PRIMARY KEY,
    repository_id       BIGINT      NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    date                DATE        NOT NULL,
    -- Cumulative snapshots
    stars_total         INT         NOT NULL DEFAULT 0,
    forks_total         INT         NOT NULL DEFAULT 0,
    watchers            INT         NOT NULL DEFAULT 0,
    open_issues         INT         NOT NULL DEFAULT 0,
    -- Deltas (computed from prev day)
    stars_gained        INT         NOT NULL DEFAULT 0,
    forks_gained        INT         NOT NULL DEFAULT 0,
    -- Activity
    contributors_count  INT         DEFAULT 0,
    commit_count_week   INT         DEFAULT 0,  -- commits in trailing 7d (from GitHub)
    releases_count      INT         DEFAULT 0,
    -- Meta
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (repository_id, date)
);

-- ============================================================
-- Weekly Metrics (pre-aggregated, computed Sunday)
-- ============================================================
CREATE TABLE weekly_metrics (
    id                  BIGSERIAL   PRIMARY KEY,
    repository_id       BIGINT      NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    week_start          DATE        NOT NULL,  -- Monday of the week
    stars_gained        INT         NOT NULL DEFAULT 0,
    forks_gained        INT         NOT NULL DEFAULT 0,
    new_contributors    INT         DEFAULT 0,
    commit_activity     INT         DEFAULT 0,
    issues_opened       INT         DEFAULT 0,
    pr_count            INT         DEFAULT 0,
    momentum_score      DECIMAL(5,2) DEFAULT 0,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (repository_id, week_start)
);

-- ============================================================
-- Trend Snapshots (per category, per day)
-- ============================================================
CREATE TABLE trend_snapshots (
    id                  BIGSERIAL   PRIMARY KEY,
    category_id         INT         NOT NULL REFERENCES technology_categories(id) ON DELETE CASCADE,
    date                DATE        NOT NULL,
    -- Aggregates
    total_stars         BIGINT      DEFAULT 0,
    repo_count          INT         DEFAULT 0,
    stars_gained_week   INT         DEFAULT 0,
    stars_gained_month  INT         DEFAULT 0,
    contributor_count   INT         DEFAULT 0,
    -- Scores
    momentum_score      DECIMAL(5,2) DEFAULT 0,
    radar_status        VARCHAR(20) DEFAULT 'stable'
                            CHECK (radar_status IN ('rising', 'stable', 'declining')),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (category_id, date)
);

-- ============================================================
-- AI Insight Reports
-- ============================================================
CREATE TABLE insight_reports (
    id              BIGSERIAL   PRIMARY KEY,
    report_type     VARCHAR(30) NOT NULL
                        CHECK (report_type IN ('repository', 'category', 'weekly_digest')),
    subject_id      BIGINT,             -- repository_id or category_id
    period_start    DATE,
    period_end      DATE,
    -- Content
    title           TEXT,
    summary         TEXT,               -- 2-sentence exec summary
    why_growing     TEXT,
    what_it_solves  TEXT,
    who_uses_it     TEXT,
    tech_stack      TEXT,
    verdict         TEXT,               -- 1-sentence "should I care?"
    competitors     TEXT  DEFAULT '[]', -- JSON string: ["owner/repo", ...]
    tags            TEXT[] DEFAULT '{}',
    full_content    JSONB,              -- raw Claude response
    -- Meta
    model_used      VARCHAR(100),
    tokens_used     INT,
    generated_at    TIMESTAMPTZ DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,        -- null = never expires
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- Indexes
-- ============================================================

-- Repositories
CREATE INDEX idx_repos_language      ON repositories(language) WHERE language IS NOT NULL;
CREATE INDEX idx_repos_momentum      ON repositories(momentum_score DESC);
CREATE INDEX idx_repos_stars_gained_today ON repositories(stars_gained_today DESC);
CREATE INDEX idx_repos_stars_gained_week  ON repositories(stars_gained_week DESC);
CREATE INDEX idx_repos_latest_stars  ON repositories(latest_stars DESC);
CREATE INDEX idx_repos_first_seen    ON repositories(first_seen_at DESC);
CREATE INDEX idx_repos_topics        ON repositories USING GIN(topics);
CREATE INDEX idx_repos_fts           ON repositories USING GIN(
    to_tsvector('english',
        coalesce(name, '') || ' ' ||
        coalesce(owner, '') || ' ' ||
        coalesce(description, '')
    )
);
CREATE INDEX idx_repos_trgm_name     ON repositories USING GIN(name gin_trgm_ops);

-- Daily metrics
-- (repository_id, date) lookups use the UNIQUE (repository_id, date) index above.
-- Newer tables and columns live in backend/app/core/schema_upgrade.py and are
-- created automatically by the refresh pipeline and on API startup.
CREATE INDEX idx_daily_date          ON daily_metrics(date DESC);
CREATE INDEX idx_daily_stars_gained  ON daily_metrics(stars_gained DESC, date DESC);

-- Weekly metrics
CREATE INDEX idx_weekly_repo         ON weekly_metrics(repository_id, week_start DESC);
CREATE INDEX idx_weekly_momentum     ON weekly_metrics(momentum_score DESC);

-- Trend snapshots
CREATE INDEX idx_trend_cat_date      ON trend_snapshots(category_id, date DESC);
CREATE INDEX idx_trend_date_score    ON trend_snapshots(date DESC, momentum_score DESC);

-- Insights
CREATE INDEX idx_insights_subject    ON insight_reports(report_type, subject_id);
CREATE INDEX idx_insights_expires    ON insight_reports(expires_at);

-- ============================================================
-- Updated_at trigger
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_repos_updated_at
    BEFORE UPDATE ON repositories
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_orgs_updated_at
    BEFORE UPDATE ON organizations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- Seed: Technology Categories
-- ============================================================
INSERT INTO technology_categories (name, slug, description, keywords, github_topics, color_hex, sort_order) VALUES
('AI Agents',         'ai-agents',         'Autonomous AI agents and agentic frameworks',     ARRAY['agent','autonomous','agentic','tool-use','ai-agent','multi-agent'],  ARRAY['ai-agent','agents','autonomous-agents'],                '#a855f7', 1),
('MCP Servers',       'mcp-servers',        'Model Context Protocol servers and tools',         ARRAY['mcp','model-context-protocol','mcp-server'],                          ARRAY['mcp','model-context-protocol'],                         '#3b82f6', 2),
('LLM Frameworks',    'llm-frameworks',     'Frameworks for building with large language models',ARRAY['llm','langchain','llamaindex','dspy','rag','retrieval'],               ARRAY['llm','large-language-models','langchain','llamaindex'],  '#8b5cf6', 3),
('Coding Assistants', 'coding-assistants',  'AI-powered code generation and completion tools',  ARRAY['copilot','code-generation','code-completion','autocomplete'],          ARRAY['code-generation','code-completion','ai-coding'],        '#06b6d4', 4),
('Vector Databases',  'vector-databases',   'Databases optimized for vector embeddings',        ARRAY['vector-db','embeddings','semantic-search','ann','pgvector'],           ARRAY['vector-database','embeddings','semantic-search'],       '#14b8a6', 5),
('ML Infrastructure', 'ml-infra',           'Tools for training, serving, and scaling ML models',ARRAY['mlops','inference','model-serving','training','gpu'],                  ARRAY['mlops','machine-learning','inference'],                  '#f59e0b', 6),
('Frontend Frameworks','frontend-frameworks','JavaScript/TypeScript UI frameworks',              ARRAY['react','vue','svelte','solidjs','astro','nextjs','nuxt'],              ARRAY['react','vue','svelte','frontend'],                       '#ec4899', 7),
('Backend Frameworks', 'backend-frameworks', 'Server-side web frameworks',                       ARRAY['fastapi','django','express','nest','hono','elysia','axum'],            ARRAY['fastapi','django','express','backend'],                  '#f97316', 8),
('Databases',         'databases',          'Data storage and query engines',                   ARRAY['postgresql','sqlite','duckdb','clickhouse','turso','mysql'],           ARRAY['database','sql','nosql'],                               '#84cc16', 9),
('Developer Tools',   'devtools',           'CLI tools, productivity tools, dev utilities',     ARRAY['cli','terminal','developer-tools','productivity','dx'],                ARRAY['developer-tools','cli','productivity'],                  '#64748b',10),
('Infrastructure',    'infrastructure',     'Infrastructure-as-code, containers, orchestration', ARRAY['kubernetes','terraform','docker','iac','helm','k8s'],                 ARRAY['kubernetes','terraform','infrastructure'],               '#0ea5e9',11),
('Security',          'security',           'Security tools, vulnerability scanners, auth',     ARRAY['security','vulnerability','pentest','auth','zero-trust'],             ARRAY['security','cybersecurity','vulnerability'],              '#ef4444',12),
('Data Engineering',  'data-engineering',   'Data pipelines, ETL, orchestration',              ARRAY['dbt','airflow','spark','data-pipeline','etl','orchestration'],        ARRAY['dbt','airflow','data-engineering','etl'],               '#f59e0b',13),
('Observability',     'observability',      'Monitoring, tracing, logging, and alerting',      ARRAY['tracing','metrics','logging','opentelemetry','observability'],        ARRAY['observability','opentelemetry','monitoring'],            '#22c55e',14),
('Fintech',           'fintech',            'Payments, trading, financial infrastructure',      ARRAY['payments','finance','trading','defi','crypto','banking'],              ARRAY['fintech','payments','finance'],                          '#eab308',15)
ON CONFLICT (slug) DO NOTHING;

-- ============================================================
-- Web Push subscriptions (free browser push via VAPID)
-- One row per browser push endpoint. repo_ids mirrors the
-- user's local watchlist; alerted_repo_ids tracks which repos
-- have already fired so we don't re-notify until they re-arm.
-- ============================================================
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id                BIGSERIAL PRIMARY KEY,
    endpoint          TEXT UNIQUE NOT NULL,
    p256dh            TEXT NOT NULL,
    auth              TEXT NOT NULL,
    repo_ids          BIGINT[] NOT NULL DEFAULT '{}',
    threshold         INTEGER NOT NULL DEFAULT 80,
    alerted_repo_ids  BIGINT[] NOT NULL DEFAULT '{}',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_push_subs_endpoint ON push_subscriptions(endpoint);
