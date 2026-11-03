from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "FirstLight"
    DEBUG: bool = False
    API_VERSION: str = "v1"
    CORS_ORIGINS: list[str] = [
        "http://localhost:2326",
        "http://localhost:3000",
        "https://yourapp.vercel.app",
    ]
    # Production frontend origin (e.g. https://your-app.vercel.app). When set, it is
    # appended to CORS_ORIGINS at startup so you don't have to edit the list above.
    FRONTEND_URL: str = ""

    # Database
    DATABASE_URL: str  # postgresql+asyncpg://user:pass@host/db

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # GitHub — only the ingestion pipeline (GitHub Actions) needs this; the API
    # server never calls GitHub, so it's optional and defaults to empty.
    GITHUB_TOKEN: str = ""
    GITHUB_API_BASE: str = "https://api.github.com"
    GITHUB_GRAPHQL_URL: str = "https://api.github.com/graphql"

    # Web Push (VAPID) — free browser push. Generate with `python scripts/generate_vapid.py`.
    # Leave blank to disable push; the API and workers degrade gracefully.
    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    VAPID_SUBJECT: str = "mailto:admin@example.com"

    # AI insight generation — pluggable provider.
    # "ollama" (free, local) | "groq"/"openai" (free/paid API) | "anthropic" (paid) | "off"
    AI_PROVIDER: str = "ollama"
    AI_MAX_TOKENS: int = 1536  # includes the reasoning tokens gpt-oss spends before answering

    # Free/hosted OpenAI-compatible LLM (Groq, Gemini's OpenAI endpoint, OpenAI, etc.).
    # Used when AI_PROVIDER is "groq" or "openai". Groq's free tier needs no credit card.
    # Grab a current model id from https://console.groq.com/docs/models
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.groq.com/openai/v1"
    LLM_MODEL: str = "openai/gpt-oss-120b"
    # gpt-oss models reason before answering; "low" keeps that short so free-tier
    # tokens go to the answer. Blank to omit it (for models that reject the field).
    LLM_REASONING_EFFORT: str = "low"

    # Ollama (local / self-hosted, free). host.docker.internal reaches the host
    # from inside a container; change to your Ollama URL when you host it.
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"

    # Anthropic Claude (optional, paid). Leave key blank unless AI_PROVIDER=anthropic.
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-20241022"
    AI_DAILY_BUDGET_USD: float = 5.0  # rough guard, tracked manually

    # Cache TTLs (seconds)
    CACHE_TTL_DASHBOARD: int = 300        # 5 min
    CACHE_TTL_REPO_DETAIL: int = 600      # 10 min
    CACHE_TTL_SEARCH: int = 30            # 30 sec
    CACHE_TTL_INSIGHTS: int = 86400       # 24 hrs
    CACHE_TTL_TRENDS: int = 3600          # 1 hr

    # Ingestion
    INGEST_BATCH_SIZE: int = 100          # repos per cron run to deep-fetch
    TOP_REPOS_FOR_INSIGHTS: int = 20      # top N repos to generate AI insights for (per run; fills in over cycles)
    INSIGHT_MAX_AGE_DAYS: int = 7         # an expired insight younger than this is kept...
    INSIGHT_REFRESH_DELTA: float = 10.0   # ...unless momentum moved by at least this many points
    SIGNALS_TOP_N: int = 200              # repos to fetch contributor/commit velocity for
    SIGNALS_CONCURRENCY: int = 8          # parallel GitHub requests when fetching signals
    DATA_RETENTION_DAYS: int = 90         # prune daily_metrics older than this (Supabase 500MB)

    # AI insight pacing (free-tier rate limits)
    AI_INSIGHT_DELAY_SEC: float = 12.0    # ~1.3k tokens a call; stays under the free tier's ~8k tokens/minute

    # Notifications — fan out to whichever channels are configured (all optional).
    DISCORD_WEBHOOK_URL: str = ""
    SLACK_WEBHOOK_URL: str = ""
    RESEND_API_KEY: str = ""              # https://resend.com free tier
    ALERT_EMAIL_TO: str = ""              # one address, or comma-separated for multiple subscribers
    ALERT_EMAIL_FROM: str = "FirstLight <onboarding@resend.dev>"  # Resend's shared test sender

    # Breakout detection: young + accelerating repos
    BREAKOUT_MAX_AGE_DAYS: int = 30
    BREAKOUT_MIN_MOMENTUM: float = 30.0
    DIGEST_TOP_N: int = 10

    # Breakout calls: predictions made before a repo reaches the weekly top list
    CALLS_PER_WEEK: int = 10              # most new calls in one Monday-Sunday week
    CALL_HIT_RANK: int = 25               # a call "comes true" on reaching this weekly rank...
    CALL_WINDOW_DAYS: int = 30            # ...within this many days

    # Enrichment (GitHub API budget per 6-hourly run; Actions token allows 1,000/hr)
    RELEASES_TOP_N: int = 60              # top repos by momentum to fetch releases for (+ watched)
    RELEASES_MAX_REPOS: int = 100
    STAR_SAMPLE_TOP_N: int = 20           # GraphQL stargazer samples per run (~1 point each)
    STAR_SAMPLE_MIN_WEEK: int = 300       # only sample repos gaining at least this many stars/week
    STAR_SAMPLE_EVERY_DAYS: int = 3

    # Retention for tables that would otherwise grow forever (Supabase 500MB)
    RELEASE_RETENTION_DAYS: int = 180
    INSIGHT_RETENTION_DAYS: int = 30      # older insights are pruned, except each repo's newest

    # "Ask the data": natural-language question -> structured filter.
    # A small model keeps this on its own Groq free quota (separate per model),
    # away from the 120B model the insights use.
    ASK_MODEL: str = "openai/gpt-oss-20b"
    ASK_DAILY_LIMIT: int = 150            # LLM-parsed questions per day; beyond this, keyword parsing only


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
