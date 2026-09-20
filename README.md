# 🤖 AI News Agent

[中文文档](./README.zh-CN.md)

A multi-agent AI news aggregation system built on LangGraph. Automatically collects, cleans, deduplicates, extracts structured information via LLM, and generates daily briefings (English professional, Chinese professional, Chinese developer edition) with multi-channel publishing.

**Features:**
- **10+ data sources**: Reddit, Hacker News, ArXiv, GitHub Trending, RSS blogs, HuggingFace Papers & Spaces, Anthropic News, Twitter/X, Product Hunt
- **LLM-powered**: AI relevance filtering, structured extraction, Chinese title generation, English translation
- **Smart dedup**: Title matching + pgvector semantic dedup + event-level merging
- **Zero-cost deploy**: GitHub Actions cron + Neon free PostgreSQL + GitHub Pages
- **Multi-model**: OpenAI / Kimi (Moonshot) / DeepSeek / any OpenAI-compatible API

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/wyh0626/ai-news-agent.git
cd ai-news-agent

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[prod]"
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your API keys
```

**Minimal config** (one LLM API Key runs 6 free sources: Reddit / HN / ArXiv / GitHub / RSS / HuggingFace):

```bash
OPENAI_API_KEY=sk-your-api-key
OPENAI_MODEL=gpt-4o-mini
```

> 💡 **No third-party keys needed**: The 6 sources above use public RSS / API endpoints — zero extra cost.

**Using Kimi (Moonshot) / DeepSeek**:

```bash
# Kimi
OPENAI_API_KEY=sk-your-moonshot-key
OPENAI_BASE_URL=https://api.moonshot.cn/v1
OPENAI_MODEL=moonshot-v1-auto
# Kimi has no Embedding API — configure separately for semantic dedup
EMBEDDING_API_KEY=sk-your-openai-key
EMBEDDING_BASE_URL=https://api.openai.com/v1

# DeepSeek
OPENAI_API_KEY=sk-your-deepseek-key
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

**Enable semantic dedup** (recommended):

```bash
# Option 1: Local Docker
docker compose up -d postgres

# Option 2: Neon free cloud database (recommended, pgvector built-in)
POSTGRES_URL=postgresql://user:pass@xxx.neon.tech/neondb?sslmode=require
```

### 3. Run

```bash
# Run all default sources
python scripts/run_pipeline.py

# Specify sources
python scripts/run_pipeline.py reddit hackernews arxiv

# Single source
python scripts/run_pipeline.py twitter
```

Available sources: `reddit` `hackernews` `arxiv` `github` `rss` `huggingface` `huggingface_spaces` `anthropic` `producthunt` `twitter`

### 4. Output

```
output/
├── ai-daily-2026-02-18.md       # Chinese report
├── ai-daily-2026-02-18-en.md    # English report
```

---

## Data Sources In-Depth

Each data source has its own collection strategy, filtering pipeline, and configuration. Overview:

| Source | Collection Method | API Key Required | Enabled by Default |
|--------|-------------------|:----------------:|:------------------:|
| Reddit | RSS | ❌ | ✅ |
| Hacker News | RSS (hnrss) | ❌ | ✅ |
| ArXiv | RSS | ❌ | ✅ |
| GitHub Trending | RSS (community) | ❌ | ✅ |
| RSS (AI Blogs) | RSS / Atom | ❌ | ✅ |
| HuggingFace Papers | HTTP API | ❌ | ✅ |
| HuggingFace Spaces | HTTP API | ❌ | ✅ |
| Anthropic News | Sitemap / HTML | ❌ | ✅ |
| Product Hunt | GraphQL API | ⚠️ Recommended | ❌ |
| Twitter/X | Firecrawl + Nitter | ✅ | ❌ |

---

### 🟢 Reddit

**How it works**: Fetches hot posts from specified subreddits via Reddit's official RSS feed (`/r/{subreddit}/hot.rss`). No API Key required.

**Two-stage filtering**:
1. **Time filter**: Only keeps posts from the last 24h
2. **LLM AI filter**: Batch classifies all titles + descriptions via LLM for precise AI relevance

**Config**:

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `REDDIT_SUBREDDITS` | `LocalLLaMA,MachineLearning,artificial,OpenAI,ClaudeAI,singularity,...` | Comma-separated subreddit list |

```bash
# Example: customize monitored subreddits
REDDIT_SUBREDDITS=LocalLLaMA,MachineLearning,artificial,OpenAI,DeepSeek
```

> 💡 **Works out of the box**: No config needed. Monitors 13 AI-related subreddits by default.

---

### 🟢 Hacker News

**How it works**: Uses [hnrss.org](https://hnrss.org) to fetch HN content with AI keywords (`AI OR LLM OR GPT OR machine learning ...`) for API-side pre-filtering, plus a minimum score threshold.

**Two-stage filtering**:
1. **hnrss `q=` parameter**: API-side keyword pre-filter + score threshold
2. **LLM AI filter**: Batch title classification, auto-adapts to new terminology

**Config**:

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `HN_MIN_SCORE` | `50` | Minimum score threshold (upvotes) |

```bash
# Lower threshold for more content
HN_MIN_SCORE=30
```

> 💡 **Works out of the box**: No config needed. Fetches AI posts with 50+ upvotes by default.

---

### 🟢 ArXiv

**How it works**: Fetches latest papers from ArXiv's official RSS feed for `cs.AI` (Artificial Intelligence), `cs.LG` (Machine Learning), and `cs.CL` (Computation & Language).

**Two-stage filtering**:
1. **Category restriction**: Only pulls from AI-related categories
2. **LLM AI filter**: Filters out pure theoretical/math papers, keeps practical AI papers

**Config**:

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `ARXIV_MAX_ITEMS` | `5` | Max papers in the final report (prevents paper overrepresentation) |

> 💡 **Works out of the box**: No config needed. Categories fixed to cs.AI/cs.LG/cs.CL, top 5 selected.

---

### 🟢 GitHub Trending

**How it works**: Fetches daily trending repos via community-maintained [GitHub Trending RSS](https://github.com/mshibanami/GitHubTrendingRSS), then uses LLM to determine AI relevance.

**Special feature**:
- **Cross-day dedup**: Local JSON cache of recently trending repos (N days) prevents the same project from appearing on consecutive days

**Two-stage filtering**:
1. **LLM AI filter**: Judges AI relevance from repo name + description
2. **Cross-day dedup**: Repos that appeared in recent days are automatically skipped

**Config**:

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `GITHUB_TRENDING_DEDUP_DAYS` | `3` | Days to cache for cross-day dedup |
| `GITHUB_TRENDING_MAX_ITEMS` | `3` | Max highly relevant repos in the briefing |

> 💡 **Works out of the box**: No config needed. Fetches all-language daily trending by default.

---

### 🟢 RSS (AI Blogs)

**How it works**: Subscribes to official blogs from major AI companies/projects via standard RSS/Atom feeds. Content is inherently AI-related — no LLM filtering needed.

**12 built-in feeds** (OpenAI URL is `https://openai.com/news/rss.xml`):
- OpenAI News, DeepMind Blog, HuggingFace Blog, PyTorch Blog
- AWS Blog, Dev.to AI, Towards Data Science
- InfoQ 中文, 掘金 (full-site feeds; AI relevance via existing filter/scorer)
- ByteByteGo, Developers Digest, Kenashe

Collector keeps a **per-feed floor** (`MIN_ITEMS_PER_RSS_FEED`, default 2) so extra blogs are not squeezed out of the shared RSS quota.

**Config**:

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `RSS_FEEDS` | empty (uses built-in) | Extra RSS feeds, format: `name1=url1,name2=url2` |
| `MIN_ITEMS_PER_RSS_FEED` | `2` | Guaranteed items per RSS feed |
| `MAX_ITEMS_PER_RSS_FEED` | `3` | Cap per RSS feed |

```bash
# Add custom RSS feeds (stacked on top of built-in sources)
RSS_FEEDS=mistral=https://mistral.ai/feed
```

> 💡 **Works out of the box**: No config needed. Anthropic has no RSS — it is a dedicated source (`anthropic`), not an RSS URL.

---

### 🟢 HuggingFace Spaces

**How it works**: `GET https://huggingface.co/api/spaces?limit=30`, ranked by `trendingScore` / likes. No token.

---

### 🟢 Anthropic News

**How it works**: Anthropic has no RSS. The dedicated source parses `sitemap.xml` for `/news/` URLs, then falls back to the HTML list at `https://www.anthropic.com/news`. Titles + URLs + dates only; article body is filled by the existing enricher.

---

### ⚪ Not connected yet

These sites have no stable public RSS/API (or need a headless browser / anti-bot), so they are deferred to keep cost down (no SerpAPI / Browserless):

- 机器之心 (JiQizhixin)
- The Batch (DeepLearning.AI newsletter)
- Futurepedia / AITools-style directories
- A dedicated InfoQ AI-topic channel (the full-site InfoQ CN feed is already in RSS)

---

### 🟢 HuggingFace Papers

**How it works**: Fetches daily curated papers via HuggingFace's public API (`/api/daily_papers`). Papers are community-voted; upvotes represent real interest. **All AI-related — no LLM filtering needed**.

**Config**:

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `HF_PAPERS_MIN_UPVOTES` | `5` | Minimum upvote threshold |

> 💡 **Works out of the box**: No config needed, no token required. Fetches papers with 5+ upvotes by default.

---

### 🟡 Product Hunt

**How it works**: Queries today's top products via Product Hunt's GraphQL API, sorted by votes.

**Two-stage filtering**:
1. **Vote threshold**: Only keeps products with votes ≥ threshold
2. **LLM AI filter**: Judges AI relevance from product name + tagline

**Config**:

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `PRODUCTHUNT_API_TOKEN` | empty | Product Hunt API Token ([apply here](https://www.producthunt.com/v2/oauth/applications)) |
| `PRODUCTHUNT_MIN_VOTES` | `50` | Minimum vote threshold |

```bash
PRODUCTHUNT_API_TOKEN=your-token-here
PRODUCTHUNT_MIN_VOTES=50
```

> ⚠️ **API Token required**: Apply for free at [Product Hunt Developer](https://www.producthunt.com/v2/oauth/applications). May not return data without a token.

---

### 🟡 Twitter/X

**How it works**: Since the Twitter API is prohibitively expensive, this project uses a **Firecrawl + Nitter mirror** approach:

1. Create a [Twitter List](https://help.x.com/en/using-x/x-lists) and add AI KOLs you follow
2. Configure a Nitter mirror URL — the system converts your Twitter List URL to a Nitter URL
3. [Firecrawl](https://www.firecrawl.dev/) scrapes the Nitter page into Markdown
4. Regex parses tweets (author, text, timestamp, engagement metrics)
5. Auto-paginates to collect tweets within a 24h window, with cross-page dedup
6. LLM batch-filters for AI relevance, sorts by engagement score, takes Top 20

**Config**:

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `FIRECRAWL_API_KEY` | empty | Firecrawl API Key ([sign up](https://www.firecrawl.dev/), free tier available) |
| `TWITTER_LIST_URL` | preset AI KOL list | Your Twitter List URL (e.g. `https://x.com/i/lists/xxx`) |
| `NITTER_MIRROR_URL` | `https://nitter.net` | Nitter mirror URL |

```bash
FIRECRAWL_API_KEY=fc-your-api-key
TWITTER_LIST_URL=https://x.com/i/lists/1585430245762441216
NITTER_MIRROR_URL=https://nitter.net
```

**How to create a Twitter List**:
1. Go to [x.com](https://x.com) → side menu → Lists → Create a new List
2. Add AI KOLs you follow (e.g. @kaboroevoda, @AndrewYNg, @ylecun)
3. Copy the List URL into `TWITTER_LIST_URL`

> ⚠️ **Firecrawl API Key required**: Sign up at [firecrawl.dev](https://www.firecrawl.dev/) — free tier is sufficient. Nitter mirrors may be unstable; switch mirrors if needed.

---

## Architecture

```
Collector → Cleaner → Dedup → Extractor → Reviewer → Writer → Translator → Publisher → Memory
  Fetch      Clean   Rule+Semantic  LLM      Event     LLM      ZH→EN      Multi-ch   Long-term
                                   Extract   Merge    Compose   Translate   Publish    Memory
```

| Agent | Role | Implementation |
|-------|------|----------------|
| **Collector** | Parallel multi-source fetching | feedparser + httpx + Firecrawl |
| **Cleaner** | Normalize format, remove noise | Rule engine |
| **Dedup** | Title dedup + semantic dedup | Title matching + pgvector |
| **Extractor** | Topic classification, summary, Chinese titles | LLM concurrent batch |
| **Reviewer** | Event-level dedup & merge | LLM identifies same events |
| **Writer** | Compose briefing (Top Stories + Featured + Quick Bites) | LLM + template fallback |
| **Translator** | Chinese report → English version | LLM translation |
| **Publisher** | Save Markdown + Email + Webhook | Multi-channel |

## Deployment

> ⚠️ Reddit RSS blocks GitHub Actions IP ranges, so the pipeline cannot run inside GitHub Actions. Deploy locally or on a VPS instead.

### Option 1: Local / VPS (Recommended)

The simplest approach — run directly with cron:

```bash
# 1. Clone & install (see Quick Start)

# 2. Test a single run
python scripts/run_pipeline.py

# 3. Set up a cron job (daily at UTC 00:00)
crontab -e
# Add the following line (adjust the path):
0 0 * * * cd /path/to/ai-news-agent && bash scripts/run_and_push.sh >> output/pipeline.log 2>&1
```

`run_and_push.sh` handles the full cycle: run pipeline → sync content to site → git push → trigger GitHub Pages deploy.

**Auto git push config** (pick one):

```bash
# Option A: GitHub Token (HTTPS, recommended)
GIT_TOKEN=ghp_your-github-token
GIT_REPO=your-username/ai-news-agent

# Option B: SSH Key
# Ensure ~/.ssh/id_ed25519 has GitHub access
```

### Option 2: Docker (Build Your Own Image)

A Dockerfile is provided, but no pre-built image is published yet — you need to build locally:

```bash
# 1. Build the image
docker build -t ai-news-agent .

# 2. Single run
docker run --rm --env-file .env -v ./output:/app/output ai-news-agent

# 3. Scheduled run (via docker-compose)
# Edit the image name in docker-compose.yml to your local build
docker compose up -d
```

### GitHub Pages (Static Site)

The project includes an Astro static site (`site/` directory). After the pipeline pushes new content, GitHub Actions auto-deploys:

1. Fork this repo
2. Go to **Settings → Pages**, set Source to **GitHub Actions**
3. When the pipeline pushes new content, `.github/workflows/deploy-site.yml` auto-builds and deploys the site

## Multi-channel Publishing

Configure in `.env` to auto-enable:

```bash
# Slack / Discord / Feishu (Lark)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
DISCORD_WEBHOOK_URL=https://hooks.discord.com/api/webhooks/...
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/...

# Email newsletter
SMTP_HOST=smtp.gmail.com
SMTP_USER=your@email.com
SMTP_PASSWORD=your-app-password
NEWSLETTER_RECIPIENTS=reader1@email.com,reader2@email.com
```

## Pipeline Tuning

Fine-tune pipeline behavior in `.env`:

```bash
MAX_ITEMS_PER_RUN=50       # Max items per run
MAX_ITEMS_PER_SOURCE=15    # Max items per source
ARXIV_MAX_ITEMS=5          # ArXiv cap (prevents paper overrepresentation)
TOP_K_FEATURED=10          # Number of featured items
SCORING_PROFILE=tech-news  # scoring ruleset; auto lets the LLM pick a profile
SCORING_BATCH_SIZE=10
SCORING_MAX_ITEMS=20       # cap after threshold and category quotas
GITHUB_TRENDING_MAX_ITEMS=3
REPORT_MODE=daily          # daily / weekly
LOG_LEVEL=INFO             # DEBUG for verbose collection logs
```

Outputs land in `output/`:

- `ai-daily-YYYY-MM-DD.md` — English professional edition
- `ai-daily-YYYY-MM-DD-zh.md` — Chinese professional edition (may be missing if translation fails)
- `ai-daily-YYYY-MM-DD-dev.md` — Chinese developer edition; each item has **Fact** (only what the candidate JSON supports) and **Practical note** (conditional advice)

### Scoring profiles

Each profile lives in `profiles/<name>/`:

- `profile.toml` — threshold, item cap, `category_groups` maxima, `category_minimums` floors
- `analysis.md` — 0–10 rubric and structured scoring prompt
- `match.md` — used when `SCORING_PROFILE=auto`

Built-in `tech-news` is for business agent developers. The four pillars are harness methodology, shipped model capabilities, first-hand lab writing, and GitHub Trending OSS (at most 3). From items that already clear 7.0, selection tries to keep at least 2 harness, 1 model-capability, and 1 official-insight pieces; it does not pad empty categories. Pre-training / post-training research is dropped by default. The developer edition’s top stories match the English edition, and model launches must not be deleted as “training papers”.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent Framework | LangGraph (StateGraph) |
| LLM | OpenAI / Kimi / DeepSeek (compatible API) |
| Embedding | text-embedding-3-small + pgvector |
| Database | PostgreSQL + pgvector (Neon free tier) |
| Static Site | Astro + TailwindCSS |
| CI/CD | GitHub Actions + GitHub Pages |

## License

MIT
