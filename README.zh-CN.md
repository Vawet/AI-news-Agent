# 🤖 AI News Agent

[English](./README.md)

基于 LangGraph 的多 Agent AI 新闻聚合系统。自动从多个数据源采集、清洗、语义去重、LLM 提取结构化信息，生成日报（英文专业版、中文专业版、中文开发落地版），支持多渠道发布。

**特点：**
- **10+ 大数据源**：Reddit、Hacker News、ArXiv、GitHub Trending、RSS 博客、HuggingFace Papers / Spaces、Anthropic News、Twitter/X、Product Hunt
- **LLM 驱动**：AI 相关性过滤、结构化提取、中文标题生成、英文翻译
- **智能去重**：标题去重 + pgvector 语义去重 + 事件级合并
- **零成本部署**：GitHub Actions 定时运行 + Neon 免费 PostgreSQL + GitHub Pages
- **多模型支持**：OpenAI / Kimi (Moonshot) / DeepSeek / 任何 OpenAI 兼容 API

## 快速开始

### 1. 克隆 & 安装

```bash
git clone https://github.com/wyh0626/ai-news-agent.git
cd ai-news-agent

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[prod]"
```

### 2. 配置

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key
```

**最小配置**（只需一个 LLM API Key，即可运行 Reddit / HN / ArXiv / GitHub / RSS / HuggingFace 六个免费源）：

```bash
OPENAI_API_KEY=sk-your-api-key
OPENAI_MODEL=gpt-4o-mini
```

> 💡 **无需任何第三方 Key**：上述 6 个数据源全部通过公开 RSS / API 采集，零额外成本。

**使用 Kimi (Moonshot) / DeepSeek**：

```bash
# Kimi
OPENAI_API_KEY=sk-your-moonshot-key
OPENAI_BASE_URL=https://api.moonshot.cn/v1
OPENAI_MODEL=moonshot-v1-auto
# Kimi 不提供 Embedding API，需要单独配置（用于语义去重）
EMBEDDING_API_KEY=sk-your-openai-key
EMBEDDING_BASE_URL=https://api.openai.com/v1

# DeepSeek
OPENAI_API_KEY=sk-your-deepseek-key
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

**启用语义去重**（推荐，避免重复报道）：

```bash
# 方式一：本地 Docker
docker compose up -d postgres

# 方式二：Neon 免费云数据库（推荐，自带 pgvector）
POSTGRES_URL=postgresql://user:pass@xxx.neon.tech/neondb?sslmode=require
```

### 3. 运行

```bash
# 采集全部默认数据源，生成日报
python scripts/run_pipeline.py

# 指定数据源
python scripts/run_pipeline.py reddit hackernews arxiv

# 只采集 Twitter
python scripts/run_pipeline.py twitter
```

可用数据源标识：`reddit` `hackernews` `arxiv` `github` `rss` `huggingface` `huggingface_spaces` `anthropic` `producthunt` `twitter`

### 4. 查看输出

```
output/
├── ai-daily-2026-02-18.md       # 中文日报
├── ai-daily-2026-02-18-en.md    # 英文日报
```

---

## 数据源详解

每个数据源都有独立的采集策略、过滤机制和配置项。下表总览：

| 数据源 | 采集方式 | 需要 API Key | 默认开启 |
|--------|----------|:------------:|:--------:|
| Reddit | RSS | ❌ | ✅ |
| Hacker News | RSS (hnrss) | ❌ | ✅ |
| ArXiv | RSS | ❌ | ✅ |
| GitHub Trending | RSS (社区维护) | ❌ | ✅ |
| RSS (AI 博客) | RSS / Atom | ❌ | ✅ |
| HuggingFace Papers | HTTP API | ❌ | ✅ |
| HuggingFace Spaces | HTTP API | ❌ | ✅ |
| Anthropic News | Sitemap / HTML | ❌ | ✅ |
| Product Hunt | GraphQL API | ⚠️ 推荐 | ❌ |
| Twitter/X | Firecrawl + Nitter | ✅ | ❌ |

---

### 🟢 Reddit

> ⚠️ Reddit 默认关闭。企业网络常拦截 `reddit.com`。需要时在 `.env` 设 `ENABLE_REDDIT=true`，或命令行：`python scripts/run_pipeline.py reddit hackernews github huggingface`。

**采集思路**：通过 Reddit 官方 RSS feed 获取指定子版块的热门帖子（`/r/{subreddit}/hot.rss`），无需任何 API Key。

**过滤机制（两级）**：
1. **时间过滤**：只保留 24h 内的帖子
2. **LLM AI 过滤**：将所有帖子标题+摘要送入 LLM 批量分类，精准筛选 AI 相关内容

**配置项**：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `REDDIT_SUBREDDITS` | `LocalLLaMA,MachineLearning,artificial,OpenAI,ClaudeAI,singularity,...` | 逗号分隔的子版块列表 |

```bash
# 示例：自定义要监控的子版块
REDDIT_SUBREDDITS=LocalLLaMA,MachineLearning,artificial,OpenAI,DeepSeek
```

> 💡 **开箱即用**：无需配置，默认监控 13 个 AI 相关子版块。

---

### 🟢 Hacker News

**采集思路**：通过 [hnrss.org](https://hnrss.org) 服务获取 HN 内容。请求时附带 AI 关键词（`AI OR LLM OR GPT OR machine learning ...`）进行 API 侧粗筛，同时设置最低分数门槛。

**过滤机制（两级）**：
1. **hnrss `q=` 参数**：API 侧关键词粗筛 + 分数门槛
2. **LLM AI 过滤**：批量标题分类，自动适应新术语

**配置项**：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `HN_MIN_SCORE` | `50` | 最低分数门槛（upvotes） |

```bash
# 降低门槛以获取更多内容
HN_MIN_SCORE=30
```

> 💡 **开箱即用**：无需配置，默认采集 50 分以上的 AI 相关帖子。

---

### 🟢 ArXiv

**采集思路**：通过 ArXiv 官方 RSS feed 采集 `cs.AI`（人工智能）、`cs.LG`（机器学习）、`cs.CL`（计算语言学）三个分类的最新论文。

**过滤机制（两级）**：
1. **分类限定**：只拉取 AI 相关分类
2. **LLM AI 过滤**：过滤纯理论/纯数学论文，保留实用 AI 论文

**配置项**：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `ARXIV_MAX_ITEMS` | `5` | 最终入选日报的论文上限（避免论文占比过高） |

> 💡 **开箱即用**：无需配置。分类固定为 cs.AI/cs.LG/cs.CL，最终精选 5 篇入选日报。

---

### 🟢 GitHub Trending

**采集思路**：通过社区维护的 [GitHub Trending RSS](https://github.com/mshibanami/GitHubTrendingRSS) 源获取每日热门仓库，再通过 LLM 判断是否 AI 相关。

**特色功能**：
- **跨天去重**：本地 JSON 缓存近 N 天已上榜项目，避免同一项目连续多天重复推送

**过滤机制（两级）**：
1. **LLM AI 过滤**：根据仓库名+描述判断是否 AI 相关
2. **跨天去重**：已在近几天上榜的项目自动跳过

**配置项**：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `GITHUB_TRENDING_DEDUP_DAYS` | `3` | 跨天去重缓存天数 |
| `GITHUB_TRENDING_MAX_ITEMS` | `3` | 日报最多推荐的高相关项目数 |

> 💡 **开箱即用**：无需配置，默认采集全语言每日 Trending。

---

### 🟢 RSS (AI 博客)

**采集思路**：通过标准 RSS/Atom feed 直接订阅各大 AI 公司/项目的官方博客。内容天然为 AI 相关，无需 LLM 过滤。

**内置 12 个源**（OpenAI 已校正为 `https://openai.com/news/rss.xml`）：
- OpenAI News、DeepMind Blog、HuggingFace Blog、PyTorch Blog
- AWS Blog、Dev.to AI、Towards Data Science
- InfoQ 中文、掘金（全站 feed，靠现有 AI filter / scorer 筛选）
- ByteByteGo、Developers Digest、Kenashe

采集器对 RSS **按 `feed_name` 保底**（`MIN_ITEMS_PER_RSS_FEED`，默认 2 条），避免博客变多后新源被挤掉。

**配置项**：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `RSS_FEEDS` | 空（使用内置源） | 追加自定义 RSS 源，格式 `name1=url1,name2=url2` |
| `MIN_ITEMS_PER_RSS_FEED` | `2` | 每个 RSS 子源保底条数 |
| `MAX_ITEMS_PER_RSS_FEED` | `3` | 每个 RSS 子源上限 |

```bash
# 添加自定义 RSS 源（会叠加在内置源之上）
RSS_FEEDS=mistral=https://mistral.ai/feed
```

> 💡 **开箱即用**：无需配置。Anthropic 没有 RSS，走独立源 `anthropic`，不要填假的 `/rss.xml`。

---

### 🟢 HuggingFace Spaces

**采集思路**：`GET https://huggingface.co/api/spaces?limit=30`，按 `trendingScore` / likes 排序。无需 Token。

---

### 🟢 Anthropic News

**采集思路**：Anthropic 无 RSS。优先解析 `sitemap.xml` 中的 `/news/` 路径，失败则抓 `https://www.anthropic.com/news` 列表链接。条目仅标题 + URL + 发布时间，正文交给现有 enricher。

---

### ⚪ 暂未接入

以下站点没有稳定公开 RSS/API，或需要无头浏览器/反爬，当前**暂缓**（不引入 SerpAPI / Browserless，控制成本）：

- 机器之心
- The Batch（DeepLearning.AI 邮件周刊）
- Futurepedia / AITools 类目录站
- InfoQ AI 专题独立频道（全站 InfoQ 中文 feed 已在 RSS 内置源中）

若以后要做，应单独做「HTML 列表源」基类，而不是塞进 `GenericRSSSource`。

---

### 🟢 HuggingFace Papers

**采集思路**：通过 HuggingFace 公开 API（`/api/daily_papers`）获取每日社区精选论文。这些论文由社区投票筛选，upvotes 代表真实热度，**全部为 AI 相关，无需 LLM 过滤**。

**配置项**：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `HF_PAPERS_MIN_UPVOTES` | `5` | 最低投票数门槛 |

> 💡 **开箱即用**：无需配置，无需 Token。默认采集 5 票以上的热门论文。

---

### 🟡 Product Hunt

**采集思路**：通过 Product Hunt GraphQL API 查询当日发布的热门产品，按投票数排序。

**过滤机制（两级）**：
1. **投票门槛**：只保留 votes ≥ 阈值的产品
2. **LLM AI 过滤**：根据产品名+tagline 判断是否 AI 相关

**配置项**：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `PRODUCTHUNT_API_TOKEN` | 空 | Product Hunt API Token（[申请地址](https://www.producthunt.com/v2/oauth/applications)） |
| `PRODUCTHUNT_MIN_VOTES` | `50` | 最低投票数门槛 |

```bash
PRODUCTHUNT_API_TOKEN=your-token-here
PRODUCTHUNT_MIN_VOTES=50
```

> ⚠️ **需要 API Token**：前往 [Product Hunt Developer](https://www.producthunt.com/v2/oauth/applications) 免费申请。不配置 Token 时可能无法获取数据。

---

### 🟡 Twitter/X

**采集思路**：由于 Twitter API 价格昂贵，本项目采用 **Firecrawl + Nitter 镜像**的方案。流程如下：

1. 创建一个 [Twitter List](https://help.x.com/en/using-x/x-lists)，将你关注的 AI KOL 添加进去
2. 配置 Nitter 镜像地址，系统将 Twitter List URL 转换为 Nitter 镜像 URL
3. 通过 [Firecrawl](https://www.firecrawl.dev/) 爬取 Nitter 页面的 Markdown 内容
4. 正则解析推文（作者、正文、时间、互动数据）
5. 自动翻页采集 24h 内推文，跨页去重
6. LLM 批量过滤 AI 相关推文，按互动分数排序取 Top 20

**配置项**：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `FIRECRAWL_API_KEY` | 空 | Firecrawl API Key（[申请地址](https://www.firecrawl.dev/)，有免费额度） |
| `TWITTER_LIST_URL` | 预设 AI KOL 列表 | 你的 Twitter List 地址（如 `https://x.com/i/lists/xxx`） |
| `NITTER_MIRROR_URL` | `https://nitter.net` | Nitter 镜像地址 |

```bash
FIRECRAWL_API_KEY=fc-your-api-key
TWITTER_LIST_URL=https://x.com/i/lists/1585430245762441216
NITTER_MIRROR_URL=https://nitter.net
```

**如何创建 Twitter List**：
1. 打开 [x.com](https://x.com) → 右侧菜单 → Lists → Create a new List
2. 添加你关注的 AI KOL（如 @kaboroevoda, @AndrewYNg, @ylecun 等）
3. 复制 List URL 填入 `TWITTER_LIST_URL`

> ⚠️ **需要 Firecrawl API Key**：前往 [firecrawl.dev](https://www.firecrawl.dev/) 注册，免费额度即可使用。Nitter 镜像可能不稳定，如遇问题可更换镜像地址。

---

## 架构

```
Collector → Cleaner → Dedup → Extractor → Reviewer → Writer → Translator → Publisher → Memory
   采集       清洗    规则+语义   LLM提取   事件合并    LLM撰稿   中→英翻译    多渠道      长期记忆
```

| Agent | 职责 | 实现 |
|-------|------|------|
| **Collector** | 并行采集 8 大数据源 | feedparser + httpx + Firecrawl |
| **Cleaner** | 格式标准化、去噪 | 规则引擎 |
| **Dedup** | 标题去重 + 语义去重 | 标题匹配 + pgvector |
| **Extractor** | 主题分类、摘要、中文标题 | LLM 并发批处理 |
| **Reviewer** | 事件级去重合并 | LLM 识别同一事件 |
| **Writer** | 编排简报（今日焦点 + 重点 + 快讯） | LLM + 模板降级 |
| **Translator** | 中文日报 → 英文版 | LLM 翻译 |
| **Publisher** | 保存 Markdown + 邮件 + Webhook | 多渠道 |

## 部署

> ⚠️ 由于 Reddit RSS 屏蔽了 GitHub Actions 的 IP 段，Pipeline 无法在 GitHub Actions 中运行。推荐在本地或 VPS 上部署。

### 方案一：本地 / VPS 直接运行（推荐）

最简单的方式，直接用 cron 定时运行：

```bash
# 1. 克隆 & 安装（见「快速开始」）

# 2. 手动运行一次，确认正常
python scripts/run_pipeline.py

# 3. 设置 cron 定时任务（每天 UTC 00:00 = 北京时间 08:00）
crontab -e
# 添加以下行（根据实际路径修改）：
0 0 * * * cd /path/to/ai-news-agent && bash scripts/run_and_push.sh >> output/pipeline.log 2>&1
```

`run_and_push.sh` 会自动完成：运行 Pipeline → 同步内容到 site → git push → 触发 GitHub Pages 部署。

**自动 git push 配置**（二选一）：

```bash
# 方式一：GitHub Token（HTTPS，推荐）
GIT_TOKEN=ghp_your-github-token
GIT_REPO=your-username/ai-news-agent

# 方式二：SSH Key
# 确保 ~/.ssh/id_ed25519 已配置好 GitHub 访问权限
```

### 方案二：Docker（需自行构建镜像）

项目提供了 Dockerfile，但尚未发布预构建镜像，需要自行构建：

```bash
# 1. 构建镜像
docker build -t ai-news-agent .

# 2. 单次运行
docker run --rm --env-file .env -v ./output:/app/output \
  ai-news-agent python scripts/run_pipeline.py

# 3. 云端常驻服务（镜像默认命令）
# 健康检查：http://localhost:8080/health
docker run --rm --env-file .env -p 8080:8080 ai-news-agent
```

云端服务会在北京时间每周三、周日 10:00 自动运行，通过飞书官方 HTTP 事件回调接收白名单群聊中的
`@机器人` 消息，并把生成报告上传到阿里云 OSS。部署步骤见 [SAE 部署说明](docs/deploy-sae.md)。

### GitHub Pages 静态站部署

项目内置了 Astro 静态站（`site/` 目录），Pipeline 运行后自动 push 内容，GitHub Actions 会自动部署：

1. Fork 本仓库
2. 在 **Settings → Pages** 中启用 GitHub Pages（Source: **GitHub Actions**）
3. Pipeline push 新内容后，`.github/workflows/deploy-site.yml` 会自动构建并部署站点

## 多渠道发布

在 `.env` 中配置即自动启用：

```bash
# Slack / Discord / 飞书
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
DISCORD_WEBHOOK_URL=https://hooks.discord.com/api/webhooks/...
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/...

# 邮件
SMTP_HOST=smtp.gmail.com
SMTP_USER=your@email.com
SMTP_PASSWORD=your-app-password
NEWSLETTER_RECIPIENTS=reader1@email.com,reader2@email.com
```

## Pipeline 调参

在 `.env` 中可微调 Pipeline 行为：

```bash
MAX_ITEMS_PER_RUN=50       # 每次运行最多处理条数
MAX_ITEMS_PER_SOURCE=15    # 每个数据源最多入选条数
ARXIV_MAX_ITEMS=5          # ArXiv 单独上限（避免论文占比过高）
TOP_K_FEATURED=10          # 精选条目数量
ENABLE_REDDIT=false        # 默认关闭 Reddit；需要时改为 true
SCORING_PROFILE=tech-news  # 评分规则集名称；auto 会由 LLM 自动匹配
SCORING_BATCH_SIZE=10      # 每次评分的资讯条数
SCORING_MAX_ITEMS=20       # 通过阈值和分类配额后的总上限
MIN_ITEMS_TO_WRITE=5       # 至少入选 5 条才进入撰稿
SCORING_RELAX_STEP=0.5     # 不足最低条数时，每轮降低阈值 0.5 分
SCORING_RELAX_FLOOR=5.0    # 放宽阈值的下限
GITHUB_TRENDING_MAX_ITEMS=3  # GitHub 开源推荐上限
REPORT_MODE=weekly         # 周三/周日双周刊；daily 仍可手动运行
LOG_LEVEL=INFO             # DEBUG 可看到详细采集日志
```

`weekly` 按北京时间每周三、周日 20:00 运行，窗口首尾衔接且不重复：

- 周三刊：上周日 20:00 之后至本周三 20:00
- 周日刊：本周三 20:00 之后至本周日 20:00

产出文件在 `output/`：

- `ai-daily-YYYY-MM-DD.md`：英文专业版
- `ai-daily-YYYY-MM-DD-zh.md`：中文专业版（翻译失败时可能缺这一份）
- `ai-daily-YYYY-MM-DD-dev.md`：中文开发落地版，每条含【事实】（只复述候选信息）和【落地参考】（条件句建议）
- 周报对应使用 `ai-weekly-YYYY-MM-DD*.md` 文件名

### 自定义评分 Profile

每套规则位于 `profiles/<name>/`，包含：

- `profile.toml`：阈值、最终条数、`category_groups` 上限、`category_minimums` 保底
- `analysis.md`：0-10 分标尺与结构化输出 Prompt
- `match.md`：`SCORING_PROFILE=auto` 时使用的自动匹配 Prompt

### 评分标准与信息依据

内置 `tech-news` 面向调用模型、设计 Harness、交付业务 Agent 的开发者，重点是可复用的方法、已发布的模型能力与一线工程经验。评分由 [Scorer](src/agents/scorer.py) 执行，规则见 [analysis.md](profiles/tech-news/analysis.md)，阈值和配额见 [profile.toml](profiles/tech-news/profile.toml)。

模型综合阅读官方摘要、正文摘要、社区讨论、来源和互动背景，判断内容是否相关、能否改变实际工程做法、证据是否充分。**没有固定权重求和公式；热度、点赞和 Star 仅作背景，不机械加分，也不只按标题打分。**

| `ai_score` | 含义 | 典型内容 |
|---|---|---|
| 9–10 分 | 突破性价值 | 强证据支持的重大模型能力变化、Agent 构建/评测范式或能改变工程实践的一手经验。 |
| 7–8 分 | 高价值 | 可复用 Harness 方法、可用评测基础设施、官方开发者更新，或有实现深度的相关项目。 |
| 5–6 分 | 值得阅读 | 增量 API/工具更新、扎实教程、二手整理，或尚未交付可复用做法的预印本。 |
| 3–4 分 | 低优先级 | 通用 AI 产品、演示项目等；训练研究还须遵守下面的 3 分上限。 |
| 0–2 分 | 噪声 | 广告、公关稿、无关内容、训练配方、个人聊天机器人或薄封装 demo。 |

提示词额外要求：

- 预训练、后训练、RLHF、训练配方、纯训练架构等内容，即使出自头部实验室也只给 0–3 分；介绍模型的实际使用能力不属于此类。
- arXiv 论文达到 7 分及以上，须提供足够具体、可重实现的做法、已发布代码或可迁移的失败教训；只提出方法并在自建基准上报告提升、没有可复用过程的，最高 6 分。
- GitHub 项目达到 7 分及以上，须与 Agent/模型开发直接相关、超出单个 demo 且有实现深度；Star 和 Trending 排名不等于质量。
- 一线经验优先看具体主张、实现、证据及对工程的影响，不能只凭作者单位给高分。

这些内容约束由模型提示词执行；本地代码校验数值范围和输出字段，不会重新判断语义分数是否符合上述上限。

### 分数字段与输出校验

| 字段 | 用途 |
|---|---|
| `quality_score` | Cleaner 计算的 0–1 预处理质量分，用于清洗阶段排序；不是最终 AI 评分。 |
| `platform_score` | 来源平台的原始热度等信号，供评分参考。 |
| `ai_score` | 模型输出的 0–10 价值分，用于后续筛选和排序。 |
| `importance_score` | 评分后设为 `max(1, ai_score)`，兼容已有消费者，不是另一份独立评分。 |
| `ai_reason` / `summary` / `score_tags` | 分别记录评分理由、事实摘要和栏目标签；提示词要求标签中包含一个允许的栏目。 |

默认每批评分 10 条、最多并发 3 批。模型通过输入 `index` 回填已有条目；本地校验 `ai_score` 在 0–10 内、理由和摘要非空、标签为列表。API 重试仍失败、JSON 无效或条目字段不合格时，将对应条目置为 0 分，避免将失败结果当作合格资讯。

### 栏目上限、保底与最终筛选

内置栏目配置如下；保底只从达到**当轮有效阈值**且通过其他限制的候选中选择，没有符合条件的内容时保留空缺：

| 栏目 | 重点 | 每期上限 | 优先保底 |
|---|---|---|---|
| Harness Methodology | 工具、编排、上下文、记忆、评测、可观测性、安全、sandbox、故障恢复等可复用方法。 | 7 | 2 |
| Model Capabilities | 已发布模型/API 在工具调用、编码、多模态、延迟、成本等方面的实际能力。 | 6 | 1 |
| AI Insights | 一线团队关于 Agent、评测、产品使用与部署的工程经验。 | 4 | 1 |
| Open Source | 直接可复用且有实现深度的 GitHub Trending 项目。 | 3 | 无 |
| Other | 仍有阅读价值、但不属于上述重点的内容。 | 1 | 无 |

[筛选代码](src/agents/scorer.py) 按以下顺序执行：

1. 按 `ai_score` 降序排列，默认有效阈值为 **7.0 分**。
2. 优先满足栏目保底，再按分数填充剩余名额；每次加入都检查有效阈值、栏目上限、Profile 上限、全局上限及重复内容。
3. `tech-news` 最多 **15 条**，同时受 `SCORING_MAX_ITEMS`（默认 20）的全局上限约束；只使用内置 Profile 时最多仍为 15 条。
4. GitHub 来源最多 **3 条**，与其他来源共用有效阈值和 Profile 总名额；`Open Source` 栏目只接受 GitHub 来源。
5. 相同非空 URL，或标题/摘要规则相似度达到 **0.78** 的候选不重复加入。规则相似度取标题字符相似度与“标题 + 摘要”词集合 Jaccard 相似度中的较大值；后续 Reviewer 再处理同事件合并。

### 条目不足时的阈值放宽

如果按 7 分筛选后不足 `MIN_ITEMS_TO_WRITE`（默认 **5 条**），Scorer 会以 **0.5 分**为步长重新筛选：`7.0 → 6.5 → 6.0 → 5.5 → 5.0`。达到最低条数即停止；栏目配额、GitHub 上限、去重和总数限制始终生效。

放宽后达到最低条数时，低于原始 7 分阈值的补位条目会加上 `below-bar` 标签。最低放宽到 5 分后仍不足 5 条，则 [条件路由](src/graph/conditions.py) 跳过撰稿；不会继续纳入更低分内容。日报和周报都使用这个最低条数条件。

未配置 LLM 时是单独的降级路径：保留提取阶段的 `importance_score` 作为 `ai_score`，标记降级理由和 `Other` 栏目，并跳过 Profile 阈值/配额筛选；这不代表模型评分已经执行。

### “本期必读”的独立挑选

写稿阶段由 [must_read.py](src/agents/must_read.py) 在同一上下文中比较候选，单独挑选一条必读，而不是直接取分批评分的最高分。优先级依次是：**这周能用上 → 影响面 → 已发布/验证的确定性 → 新颖度**。

必读应对应本期事件；只有热榜仓库简介而无本期变化的条目受提示词限制，且代码直接排除已标记 `is_established` 的 GitHub 热榜项目。返回的 ID 必须属于可选候选，标题和理由须非空；挑选失败时不阻断报告生成。

落地版头条与英文专业版对齐，且不得把模型发布当成训练论文删掉。

## 技术栈

| 层次 | 技术 |
|------|------|
| Agent 框架 | LangGraph (StateGraph) |
| LLM | OpenAI / Kimi / DeepSeek（兼容 API） |
| Embedding | text-embedding-3-small + pgvector |
| 数据库 | PostgreSQL + pgvector（Neon 免费层） |
| 静态站 | Astro + TailwindCSS |
| CI/CD | GitHub Actions + GitHub Pages |

## License

MIT
