# 流水线早期踩坑记录

- **日期**：2026-09-20
- **状态**：留档参考
- **范围**：整理自项目早期开发阶段（2026-02-18 ~ 2026-03-02）的提交记录。那段提交历史已压缩为单个 initial commit，其中的排错结论在此留档，避免后续把已经填好的坑再踩一遍。

每条都标注了当前代码位置。**看到这些"看起来多余"的写法时，先读本文再改。**

---

## 1. LLM 调用参数

### max_tokens 不能用 max_completion_tokens

早期用 `max_completion_tokens`，部分模型/网关不认这个参数，报错或静默失败。统一改回 `max_tokens`。

### 推理模型的 token 预算被思考过程吃掉

`gpt-5-nano` 这类推理模型，reasoning tokens 也算在 `max_tokens` 里。预算给小了会出现"返回空字符串"或 JSON 截断——现象不是报错，是解析失败。这个值被连续上调过两轮（1024 → 4096 → 16384）才稳定。

当前各处取值：

| 位置 | max_tokens |
|------|-----------|
| `src/agents/extractor.py` | 16384 |
| `src/agents/reviewer.py` | 16384 |
| `src/agents/scorer.py` | 16384 |
| `src/agents/trend_analyzer.py` | 16384 |
| `src/tools/ai_filter.py` | 16384 |
| `src/agents/translator.py` | 32768 |
| `src/agents/writer.py` | 32768 |

**不要为了省钱往下调**，省下的钱会以整条流水线跑空的形式还回来。

### 需要 JSON 的地方强制 response_format

`extractor` / `reviewer` / `scorer` 都带了 `model_kwargs={"response_format": {"type": "json_object"}}`。加之前 LLM 经常在 JSON 外面裹一层 ` ```json ` 或说明文字。

注意：开启 json_object 后 prompt 里必须要求返回 **JSON 对象**而非数组。`reviewer` 的合并分组因此从 `[...]` 改成了 `{"groups": [...]}`，解析函数 `_parse_merge_groups()` 两种格式都兼容，是为了这次改动留的后路。

---

## 2. LLM 输出解析容错

`src/agents/extractor.py` 的 `_parse_extraction()` 有一段"看起来没必要"的清洗：

```python
cleaned = re.sub(r'//[^\n]*', '', chunk)          # 去 // 注释
cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)  # 去尾部逗号
```

这是实测出来的：模型会在 JSON 里写 `//` 注释和尾随逗号，标准 `json.loads` 直接失败。解析顺序是「直接解析 → 截取首尾大括号 → 清洗后重试」，别简化。

另外 `src/tools/ai_filter.py` 的 `BATCH_SIZE = 25`：一批超过 25 条标题，prompt 过长会导致 LLM 返回空响应。这个数字是试出来的上限。

---

## 3. 数据库连接（Neon / 云 Postgres）

`src/storage/postgres.py` 里这几个参数都有具体来由：

- **`keepalives` 四件套**：Neon 这类云库在长时间空闲后会断掉 SSL 连接。流水线跑一轮要几十分钟，中间大段时间不碰数据库，不加 keepalive 就会在末尾写入时报 SSL 错误。
- **`min_size=1, max_size=5`**：从 2/10 降下来的，云库连接数有限。
- **`reconnect_timeout=30`**：断线重连窗口。
- **`get_postgres()` 里调 `init_tables()`**：保证表结构存在，省掉手工初始化步骤。

配套的坑在 `src/agents/memory_updater.py`：它跑在流水线最末尾，此时流水线开头建立的连接单例很可能已经超时。所以那里故意重置单例后重建连接：

```python
_pg_mod._pg = None
pg = await _pg_mod.get_postgres()
```

这不是写错了，是有意为之。

---

## 4. Twitter / Nitter 采集

这是改动最反复的模块，`src/sources/twitter_firecrawl.py`。

### 分页停止条件（改过三轮）

最终逻辑：`_parse_nitter_markdown()` 返回**当页最新推文时间** `newest_time`，只有当页最新的推文都超出 24 小时窗口时才停止翻页。

演进过程：最初用「当页最旧推文」判断，但被置顶推文和转推的旧时间戳干扰，会提前停止；中间改成「无论是否被过滤都更新 oldest_time」仍不对；最后才确定用 newest_time。**改成 oldest 看起来更直觉，但是错的。**

### Nitter 的相对时间戳

Nitter 对近期推文显示 `3m` / `2h` / `1d` 这种相对时间，不是 `Feb 14, 2026 · 4:23 PM UTC`。`_parse_nitter_date()` 两种格式都要处理，否则最新的推文全部解析失败，直接影响上面的分页判断。

### 引用推文的互动数据归因

引用推文里嵌着被引原推的锚点，直接解析会把原推的点赞转发数算到引用者头上（也就是把别人的爆款数据算成自己的）。区分方法是看头像 URL：

```
引用推文中嵌入的原推 → profile_images/..._mini（非链接）
转推 / 原推          → profile_images/..._bigger（链接）
```

对应 `_parse_nitter_markdown()` 里那段 `_mini` 正则检测。

### 跨页去重取最高分

同一条推文在不同页可能抓到不同的互动数（翻页有时间差），`best_items[tid]` 按 score 取最大值，即最接近实时的那次。

### 调试导出

`_dump_page()` / `_dump_parsed_items()` 会把每页原始 markdown 和解析结果写到 `output/twitter_debug/`。Nitter 镜像页面结构变化频繁，解析出问题时先看这里的 dump，比盯日志快。

### 已经试过并放弃的方案

高分推文（互动数 ≥ 10k）跳过 LLM 过滤直接保留——试过，结果是政治、体育类爆款推文混进日报。现在所有推文一律过 AI filter，再按 score 取 top 20。

---

## 5. 数据源配额与筛选

- **ArXiv 单独限额**：`src/config.py` 的 `arxiv_max_items: int = 5`。论文数量大、score 偏高，不单独设上限会挤占其他源的名额。`src/agents/collector.py` 的 `_smart_select()` 用「每源保底配额 + 剩余进竞争池」的结构，ArXiv 在两个阶段都走单独上限。
- **AI filter 的排除项**：prompt 里显式排除政治/军事内容，是因为这类内容互动数天然高，容易挤进榜单。
- **Reddit 接入方式反复过**：JSON API（hot 排序 + upvotes 作分数）→ 最终改回 RSS。当前是 `src/sources/reddit.py` 的 `hot.rss`。JSON API 对非浏览器 UA 的限制是主要原因。
- **降级策略**：`ai_filter` 在 LLM 不可用时退化为关键词匹配，不要删掉这条兜底路径。

---

## 6. 成本与并发

- `src/tools/ai_filter.py` 的 `MAX_CONCURRENT = 8`：批次并行执行，信号量限流。串行跑太慢，全并发会触发限流。
- `src/agents/writer.py` 的 `_items_to_json(items, brief=True)`：Quick Bites 部分只传 title / source / url 三个字段。全字段传给 LLM 会显著推高 token 成本，而这部分输出根本用不到 summary 和 topics。

---

## 7. 双语与站点

- **流水线是 English-first**：英文生成 → 翻译成中文，主文件是英文，中文是 `-zh.md`。这个方向早期是反的（中文生成 → 译英），翻转过一次，改动涉及 extractor / writer / translator / publisher / 站点同步脚本一整条链路。想改回来的话要整条链一起改。
- **`extractor` 用 `temperature=0`**：为了打分稳定可复现。
- **翻译容易漏掉的地方**：Top Stories 下 `### 1. Some Title` 这种带编号的标题，模型会当成结构而不是文本，整段不翻译。`src/agents/translator.py` 的 prompt 里专门有一条规则点名这个格式，别当成冗余删掉。
- **frontmatter 的 `lang` / `pairSlug`**：站点靠这两个字段区分语言版本、实现文章页双语互跳。中英两个版本都要写，英文版还要回写 `pairSlug` 指向中文版。
- **Astro base path**：配了自定义域名后 base 是根路径；早期用子路径时踩过「缺少结尾斜杠导致语言切换链接出现双斜杠」的问题。改 `site/astro.config.mjs` 的 base 时，`nav-menu.ts`、`site.ts`、`globals.css` 里的路径要一起改。
- **封面图**：从推文提取封面图的功能做过又删了，原因是 frontmatter 和正文里各渲染一次，站点上重复显示。

---

## 8. 部署与运维

- **部署方式从 GitHub Actions 换成了服务器上的 Docker**，入口是 `scripts/run_and_push.sh`。Actions 的问题是密钥项多、超时限制、以及调试时看不到中间状态。
- **`run_and_push.sh` 的几处防御**：自动探测项目目录、自动 `source .env`、自动激活 venv 并回退到 `python3`、push 前先 `git pull --rebase`。最后一条是为了避免服务器和本地同时提交产出文件时冲突。
- **UTC 跨天问题**：流水线在 UTC 午夜后运行，日报日期和提交信息都要用**前一天**的日期，否则文件名和内容对不上。`src/agents/writer.py` 和 `run_and_push.sh` 里都做了这个偏移。
- **日志统一用英文**：早期中文日志在服务器终端上有编码问题，全量翻译过一次。

---

## 附：完整历史的查阅方式

上游历史保留在本地分支 `backup/old-history`（不在远程）。需要看某个文件的完整演变时：

```bash
git log backup/old-history                            # 完整提交历史
git log -p --follow backup/old-history -- src/xxx.py  # 单文件演变
```

该分支一旦删除并执行 `git gc --prune=now`，这些记录将不可恢复。
