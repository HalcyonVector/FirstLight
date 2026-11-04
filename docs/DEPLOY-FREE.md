# Deploying for Free (no laptop, no Docker, always on)

This runs the whole project on free tiers with **no machine of yours staying on**:

| Piece | Host | Free-tier reality |
|---|---|---|
| Scheduled pipeline (ingest → score → aggregate → AI insights) | **GitHub Actions cron** | Runs every 6h on GitHub's servers. Also keeps Supabase awake. |
| Postgres database | **Supabase** | 500 MB; pauses after ~7 days of DB inactivity — the 6h cron prevents that. |
| Backend API | **Render** (free web service) | Spins down after ~15 min idle; first visit then cold-starts in ~30–60s. |
| Frontend | **Vercel** | Next.js's native host. |
| AI insights | **Groq** free API | OpenAI-compatible; no credit card. |
| Redis | *not used* | The scheduler bypasses Celery, and the API now runs fine with no cache. |

Total cost: **$0**. The only trade-off is the API cold-start on the first visit after it's been idle.

> The code changes that make this work are already in the repo: a free-LLM provider in the AI service, a Supabase-safe database engine, a Redis-optional cache, a configurable CORS origin, `render.yaml`, and `.github/workflows/refresh.yml`.

---

## 0. Push the repo to GitHub

If it isn't already on GitHub:

```bash
git add .
git commit -m "Add free hosting: scheduler, Supabase/Groq support, Render+Vercel config"
git push
```

Everything below wires the hosted services to this repo.

---

## 1. Database — Supabase

1. Create an account at https://supabase.com and click **New project**. Pick a region near you and set a database password (save it).
2. When it's ready, open **SQL Editor**, paste the contents of `infra/schema.sql`, and **Run**. This creates the tables and seeds the 15 categories.
3. Get the connection string: **Project Settings → Database → Connection string → URI**. It looks like:
   `postgresql://postgres.xxxx:[PASSWORD]@aws-0-<region>.pooler.supabase.com:6543/postgres`
4. Two edits to that string before you use it anywhere:
   - change the scheme `postgresql://` → **`postgresql+asyncpg://`**
   - put your real password in place of `[PASSWORD]`

   Keep this final value handy — it's your `DATABASE_URL`. (Both the pooler port `6543` and the session port `5432` work; the app disables the prepared-statement cache so PgBouncer is fine.)

---

## 2. AI key — Groq (free)

1. Sign in at https://console.groq.com and create an **API key** (starts with `gsk_`). No credit card.
2. Check https://console.groq.com/docs/models for a **current** model id. Groq rotates these; good picks are `openai/gpt-oss-120b` or `openai/gpt-oss-20b` (the Llama models were retired from the free tier in August 2026). Whatever you choose becomes `LLM_MODEL`.

> Prefer Google Gemini's free tier or OpenAI instead? Same setup — just change `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY`. Or set `AI_PROVIDER=off` to skip written analyses entirely; everything else still works.

---

## 3. The scheduler — GitHub Actions

The workflow is already at `.github/workflows/refresh.yml` (every 6h + a manual run button).

In your GitHub repo → **Settings → Secrets and variables → Actions**, add:

**Secrets** (the "Secrets" tab):

| Name | Value |
|---|---|
| `GH_PAT` | A GitHub personal access token (Settings → Developer settings → Tokens). Public data needs no scopes. *(Stored as `GH_PAT` because `GITHUB_TOKEN` is reserved.)* |
| `DATABASE_URL` | The `postgresql+asyncpg://…` string from step 1 |
| `LLM_API_KEY` | Your `gsk_…` Groq key |

**Variables** (the "Variables" tab — optional, they have defaults):

| Name | Value |
|---|---|
| `AI_PROVIDER` | `groq` |
| `LLM_MODEL` | the model id from step 2 |
| `LLM_BASE_URL` | `https://api.groq.com/openai/v1` |

Then go to the **Actions** tab → **refresh-data** → **Run workflow** to do the first load immediately (don't wait 6h). Watch the run; it should ingest ~1–2k repos. Momentum stays 0 until the **second** run on a later date gives it a day-over-day delta — same velocity rule as local.

---

## 4. Backend API — Render

1. Sign in at https://render.com with your GitHub account.
2. **New + → Blueprint**, select this repo. Render reads `render.yaml` and proposes a service named `gti-api`.
3. It will ask for the values marked as secrets. Fill in:
   - `DATABASE_URL` — same Supabase string
   - `GITHUB_TOKEN` — your PAT
   - `REDIS_URL` — from a free Upstash Redis database (https://console.upstash.com → Connect → **TCP** tab): just the `rediss://default:<password>@<host>:6379` part, no quotes. Without it the API runs uncached and Ask uses keyword parsing only.
   - `LLM_API_KEY` — your Groq key
   - `FRONTEND_URL` — leave blank for now; you'll set it in step 5
4. **Apply / Create**. First build takes a few minutes. When live you'll get a URL like `https://gti-api.onrender.com`. Open `https://gti-api.onrender.com/health` to confirm it's up (it returns `{"status":"ok"}`); interactive API docs are at `/api/docs`.

---

## 5. Frontend — Vercel

1. Sign in at https://vercel.com with GitHub and **Import** this repo.
2. Set **Root Directory** to `frontend`.
3. Add an environment variable:
   - `NEXT_PUBLIC_API_URL` = your Render URL from step 4 (e.g. `https://gti-api.onrender.com`, no trailing slash)
4. **Deploy**. You'll get a URL like `https://your-app.vercel.app`.
5. Back in **Render → gti-api → Environment**, set `FRONTEND_URL` to that Vercel URL and save (it redeploys). This lets the browser call the API (CORS). For more than one address, separate them with commas (`https://new.vercel.app,https://old.vercel.app`); the first is the one emails link to.

---

## 6. Verify

- Visit your Vercel URL. The dashboard loads (first hit may wait ~30–60s while Render wakes).
- After the **second** scheduled/manual `refresh-data` run lands on a new date, momentum, leaderboards, and radar populate with real numbers.
- Repository pages show AI write-ups once an insights run has completed.

---

## How it behaves day to day

- **Every 6 hours**, GitHub Actions runs the pipeline against Supabase. Nothing of yours needs to be on.
- The dashboard is always reachable; it just cold-starts if the API has been idle >15 min.
- Supabase never pauses because the cron touches the database well within the 7-day window.

## Notes & limits

- GitHub Actions disables scheduled workflows after ~60 days of **no repo activity** — a commit or a manual run resets that.
- Groq free tier is rate-limited (thousands of requests/day); the pipeline only writes insights for the top ~50 repos per run, well within limits.
- Supabase free DB is 500 MB. If it fills over time, prune old `daily_metrics` rows.
- Want no cold starts? A paid Render instance (~$7/mo) stays warm — optional, not required.

## Where the config lives

- `.github/workflows/refresh.yml` — the scheduler
- `render.yaml` — the API service definition
- `infra/.env.production.example` — backend hosted values (reference)
- `frontend/.env.production.example` — frontend value (reference)
