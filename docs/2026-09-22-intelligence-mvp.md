# 对外 MVP：从 AI 日报到 Marketing 情报产品

- **日期**：2026-09-22
- **状态**：待验证（第 0 步没过，后面都不做）
- **范围**：把现有流水线改成一个能卖的窄场景产品——**AI Marketing 产品与评测情报**
- **怎么读这份文档**：只看第 1、2 节。第 3 节之后是二期以后的路线图，现在不要动手。

---

## 0. 先做这件事（不写代码）

选 3 家竞品 + 1 个评测集方向，**手动**做一期，发给 5 个做 marketing 的人看。

- 竞品建议：Jasper、HubSpot Breeze、Clay
- 评测集方向：marketing 文案/活动生成类公开评测集
- 动作：翻他们的 changelog、定价页、官方博客、Hugging Face datasets，写一页纸
- 用时：2 小时

判断标准：

| 反馈 | 结论 |
|------|------|
| "这个我愿意每周看" | 进第 1 节 |
| "我自己搜也能搜到" | 停，先改选题，不要写代码 |

**这一步不做，第 1 节之后全是白干。** 现在还不知道有没有人要，就不要先做页面 Diff、Event 表和界面。

---

## 1. 本周三件事（一天的量）

不碰数据库、不碰前端、不改 `SourceType`。只让现有流水线能跑出第二种报告。

### 1.1 复制一个评分 profile（约 30 分钟）

把 `profiles/tech-news/` 整个复制成 `profiles/marketing-intel/`，然后：

- `profile.toml`：`name` 改成 `marketing-intel`，`category_groups` 换成情报分类
- `analysis.md`：选稿标准从"对业务 Agent 开发者有用"改成"对 marketing 决策有用"
- `match.md`：描述改成 marketing / 竞品 / 评测集领域

`profile.toml` 参考：

```toml
name = "marketing-intel"
description = "面向 marketing 与增长决策：竞品动态、评测集更新、定价变化优先；排除模型训练研究与纯公关稿"
threshold = 6.0
max_items = 12

[category_groups]
"评测集更新" = 4
"竞品动态" = 5
"定价与包装" = 3
"行业信号" = 2
"Other" = 1

[category_minimums]
"竞品动态" = 2
"评测集更新" = 1
```

**不需要改任何 Python。** `load_profiles()` 会自动扫 `profiles/*/profile.toml`：

```36:39:src/scoring/profiles.py
    for config_path in sorted(root.glob("*/profile.toml")):
        profile_dir = config_path.parent
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        name = str(data.get("name") or profile_dir.name)
```

切换方式是 `.env` 里 `SCORING_PROFILE=marketing-intel`。

### 1.2 加源，全走现有 RSS 通道（约 1 小时）

先不写任何新 Connector。把竞品的官方 feed 塞进 `.env`：

```bash
RSS_FEEDS=jasper=https://www.jasper.ai/blog/rss.xml,hubspot_product=https://...,clay_changelog=https://...,salesforce_news=https://...
```

规则：

- 抓得到就留，抓不到先跳过，不要为了一个源写爬虫
- 一次只加 8 个以内，先看内容质量
- 定价页、changelog 这类**没有 feed 的**先手动看，二期再做 Watch

### 1.3 加第三份 writer prompt（约 2 小时）

`src/agents/writer.py` 里已经有两份 prompt：`WRITER_PROMPT`（英文专业版）、`DEV_WRITER_PROMPT`（中文开发落地版，见第 83 行）。再加一份 `INTEL_WRITER_PROMPT`，输出**卡片**而不是新闻段落。

每条固定四栏，字段名不许改、不许增减：

```text
### Jasper 上线活动效果评测

**发生了什么**：把 campaign eval 从 beta 推到正式版
**证据**：changelog 2026-09-18 / 定价页新增 SKU — <url>
**对你意味着**：你们的回归集缺"跨渠道一致性"这类题
**还不确定**：是否支持自定义指标，文档未写
```

prompt 里必须带的硬约束（照抄 `DEV_WRITER_PROMPT` 已验证的那几条）：

- 候选 JSON 是唯一事实来源，原文没写的机制、参数、功能一律不许补
- 原文没说的写"原文未说明"，禁止"首次/唯一/领先"除非原文出现
- **对你意味着**必须是条件句："如果你在做 X，可以先验证 Y"
- 不要输出 `AI Score`。对外只写「高影响 / 值得跟踪」

落盘参考现有落地版的做法（`src/publishers/markdown.py` 第 113 行那段），新增 `markdown_content_intel` 字段和 `output/intel-<date>.md`。

### 1.4 验收

```bash
SCORING_PROFILE=marketing-intel python scripts/run_pipeline.py rss
```

产出 `output/intel-2026-09-22.md`，拿给第 0 节那 5 个人看第二期。三期之后再决定要不要做第 2 节。

---

## 2. 二期做什么（验证通过后才排期）

一期跑三期、用户愿意看，才动这两件事。**顺序不能换。**

### 2.1 Watch：页面变化检测

这是产品真正的护城河，但必须排在验证之后。

定期抓指定 URL、存快照、比 Diff。价格页从 `$99` 变成 `$149`、changelog 多了一行，RSS 型采集看不见。

第一版只盯三类页面：changelog、pricing、dataset card。每个竞品 3 个 URL，10 家也就 30 个页面，够用。

### 2.2 一页界面

不要做三页，先做一页：**本周简报**。

- 本周 3 件事（只放会改变决策的）
- 竞品对照表
- 评测集变更

对照表是这个产品最值钱的部分，因为长文说不清"谁已经上线、谁还停在宣传"：

```text
能力          Jasper   HubSpot   Clay
活动生成      已上线    已上线    部分
效果评测      新发布    未公开    —
价格动作      上调      不变     新 SKU
```

---

## 3. 附录：三期以后的路线图

以下是完整设计，**现在不要动手**，留档用于判断一期的取舍有没有堵死后路。

### 3.1 Monitor：用户填业务语言，不填数据源

用户创建监控任务时只填：监控主题、关注对象（≤10 家）、关注事件类型、频率、投递渠道。系统内部映射到 Source Pack。

侧栏按用户对象组织（`Jasper / 评测集 / 定价`），不要用 `RSS / GitHub / arXiv` 当导航。

### 3.2 Connector 分四类

`SourceType` 现在是封闭枚举（`src/models.py`），到这一步才需要改成可插拔注册：

1. **Feed**：RSS、官方 API、社交（现有源全部迁入）
2. **Search**：按关键词发现新页面、新数据集
3. **Watch**：页面快照 + Diff（第 2.1 节）
4. **Dataset**：Hugging Face、Kaggle、GitHub Releases、Papers with Code

### 3.3 两个 Source Pack

**评测集 Pack** 要抽取的字段：名称、版本、任务类型、样本量、语言、license、metrics、baseline、相对上版改了什么。

**竞品 Pack** 的源和评测集完全不同，且必须包含先行信号：

| 源 | 看什么 |
|----|--------|
| Changelog / Release notes | 功能是否真上线 |
| Pricing 页 | 价格、SKU、限免 |
| 产品/API 文档 | 能力边界 |
| LinkedIn 招聘 | 还没上线时的方向信号 |
| G2 / 商店评论 | 用户感知变化 |
| 官方博客 / 媒体 | 发布叙事与外部印证 |

### 3.4 数据层：Article 升级为 Event

`article_index` + `topic_trends` 够做新闻记忆，不够做竞品方向。需要新增：`monitors`、`organizations`、`observations`、`events`、`page_snapshots`、`claims`、`user_feedback`。

趋势不能再用"话题出现次数"当主指标，要算：某对象本周新增了什么能力、多家是否同时进入同一方向、是宣传还是已上线、相对上周的 diff。

`src/agents/trend_analyzer.py` 可继续产周报草稿，但输入要换成 events + 实体时间线。

### 3.5 可读性的完整规范

一期靠第 1.3 节那四栏就够。规模上去后补齐：

- **置信度四档**（对外不显示 0.87 这种分数）：已证实 / 方向明确细节未公开 / 仅宣传 / 来源冲突
- **证据可点开**：默认折叠原文，展开是高亮片段；卡片里的数字与摘录双向跳转
- **术语规则**：首页不许出现未解释的 MAE、pass@k、trajectory、harness；数字必须带比较对象
- **跳过理由**：低价值条目不静默消失，显示"未收录：只有新闻稿，没有产品变化"
- **生成后 gate**：第一句有主语、有"对你意味着"、至少一条证据、建议没伪装成事实、单段不超 80 字、同事件不重复。不通过就重写一次，仍失败降级为"原文摘要 + 待核"，不得进「本周 3 件事」

### 3.6 明确不做

- 任意 URL 爬取
- 全行业模板市场
- 以 `AI Score` 为卖点的长 Newsletter
- 无证据的"行业趋势展望"

---

## 4. 和现有文档的关系

- 日报双版本仍按 [2026-09-06-dual-newsletter-versions.md](./2026-09-06-dual-newsletter-versions.md) 维护，作为站点/内部产物，**一期不受影响**
- 源站可达性见 [2026-09-06-news-sources-integration.md](./2026-09-06-news-sources-integration.md)，第 1.2 节加源前先查那份实测记录
- 流水线坑见 [2026-09-20-pipeline-lessons.md](./2026-09-20-pipeline-lessons.md)。卡片输出同样不要调小 `max_tokens`，JSON 截断会直接毁掉输出
