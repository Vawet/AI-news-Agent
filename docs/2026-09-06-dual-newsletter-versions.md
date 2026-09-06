# 双版本日报：专业版 + 开发落地版

- **日期**：2026-09-06
- **状态**：方案已定，待实施
- **范围**：在保留现有专业简报的同时，新增中文「开发落地版」并单独落盘

---

## 1. 决策

- **专业版**：保持现状——英文 `WRITER_PROMPT` 产出 + 现有中文翻译。
- **落地版**：用「人话 + 怎么做」风格，**直接用中文生成**（不先英后译），语气口语、有技术点、每条带可操作场景。
- 每次流水线**默认两版都出**；落地版失败不影响专业版发布。

---

## 2. 现状

```mermaid
flowchart LR
  reviewer --> writer
  writer -->|"markdown_content EN"| translator
  translator -->|"markdown_content_zh"| publisher
  publisher --> outEn["output/ai-daily-DATE.md"]
  publisher --> outZh["output/ai-daily-DATE-zh.md"]
```

写稿入口在 [`src/agents/writer.py`](../src/agents/writer.py)；模型字段在 [`src/models.py`](../src/models.py) 的 `GeneratedArticle`；落盘在 [`src/publishers/markdown.py`](../src/publishers/markdown.py)。

---

## 3. 目标产出

| 文件 | 内容 |
|------|------|
| `output/ai-daily-YYYY-MM-DD.md` | 专业英文版（不变） |
| `output/ai-daily-YYYY-MM-DD-zh.md` | 专业中文翻译（不变） |
| `output/ai-daily-YYYY-MM-DD-dev.md` | **新**：中文开发落地版 |

落地版条目结构（每条约 3–4 行）：

1. **标题**（保留模型/产品名原文）
2. **【人话版】** 大白话 + 比喻
3. **【开发能用上】** `如果你的 Agent/项目中遇到[XX]，可以用这个办法[YYY]`
4. 保留 `AI 评分` + 原文 URL
5. 文末 **开发趋势总结** 1–2 句

---

## 4. 实现步骤

### 4.1 扩展文章模型

在 [`src/models.py`](../src/models.py) 的 `GeneratedArticle` 增加：

- `markdown_content_dev: str = ""`
- `description_dev: str = ""`（可选，给站点列表用）

### 4.2 Writer 增加第二路生成

在 [`src/agents/writer.py`](../src/agents/writer.py)：

- 新增 `DEV_WRITER_PROMPT`（中文），固化要求：人话、可操作场景、轻松语气、每条短、文末趋势总结；输入仍用已评分的 `ExtractedItem` JSON（title/summary/ai_score/ai_reason/url/source）。
- 在 `writer_node` 里：专业版写完后，再调一次 LLM 生成落地版；失败只打 warning，专业版照常返回。
- 降级模板 `_build_fallback_dev_markdown`：无 LLM 时用 `summary + ai_reason` 拼出简版落地稿，保证文件仍产出。

### 4.3 Publisher 落盘落地版

在 [`src/publishers/markdown.py`](../src/publishers/markdown.py) 的 `publish_node`：若有 `markdown_content_dev`，写：

`ai-daily-{date}-dev.md`

frontmatter 示例：`lang: zh-dev`、`title`、`description`。邮件/Webhook **仍只推专业英文版**（避免渠道刷屏）；落地版仅本地/站点文件。

### 4.4 工作流

不必改图拓扑：落地版挂在现有 `writer` 节点内完成即可（translator 不碰落地版）。

```mermaid
flowchart LR
  reviewer --> writer
  writer -->|"EN 专业版"| translator
  writer -->|"ZH 落地版"| publisher
  translator -->|"ZH 专业版"| publisher
```

### 4.5 测试

- 单测：落地版 prompt 模板字段齐全；fallback 含「人话」「开发能用上」「趋势总结」。
- 不强制跑完整 LLM 流水线。

---

## 5. 关键文件

- [`src/models.py`](../src/models.py)
- [`src/agents/writer.py`](../src/agents/writer.py)
- [`src/publishers/markdown.py`](../src/publishers/markdown.py)
- `tests/test_writer.py`（补充落地版 fallback 断言）
