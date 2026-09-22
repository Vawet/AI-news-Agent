"""必读挑选 - 独立 LLM 调用，从本期候选里重排出唯一一条"先看这个"

ai_score 由分批调用产生，跨批之间不可比，所以不能直接取最高分。
这里用一次独立调用把全部候选放在同一上下文里横向比较。
"""

import json
import logging
from dataclasses import dataclass

from src.config import settings
from src.llm.client import build_chat_model
from src.models import ExtractedItem, SourceType

logger = logging.getLogger(__name__)

MUST_READ_PROMPT = """你在给「业务 Agent 开发者」的技术周报挑选**唯一一条**必读条目。

读者是做业务 Agent 的后端工程师，不是机器学习研究员。他一周只有时间认真读一条，你要替他选。

━━━━━━ 排序标准（按优先级，前面的压倒后面的） ━━━━━━

1. **这周就能用上**：有可直接借鉴的做法、可跑的代码、可复用的架构或明确的踩坑教训。能改变他下周写代码方式的，排最前。
2. **影响面**：影响的是大多数 Agent 项目，还是只影响某个窄场景。
3. **确定性**：已发布并被验证过的东西，优先于"提出了一个方法、只在自家基准上有提升"。
4. **新颖度**：只在前三项打平时才用来破平局。

明确降权：纯学术预印本，若只提出方法、只在自建基准上报告提升、没有可复用做法或开源实现，**不应当选为必读**，除非本期实在没有别的条目。

━━━━━━ 必读必须是"本期发生的事" ━━━━━━

必读回答的是"这一期有什么新情况值得你花时间"，所以它必须对应一个**事件**（发布了什么、改了什么、测出了什么、踩了什么坑），而不是一个**状态**（某个项目很火、很好用）。

候选里 `is_trending_listing` 为 true 的条目来自 GitHub 热榜，正文往往只是仓库简介，描述的是项目长期以来就具备的能力，并非本期新变化。这类条目**不得选为必读**，除非候选文本里明确写了本期发生的新变化（如新版本、新功能上线）。同理，`is_established` 为 true 表示项目已存在半年以上，成名已久，更不该被当成本期新闻。

如果所有候选都不构成本期事件，就选其中对读者最有实操价值的那条，并在 `reason` 里如实说明它不是本期新发布。

━━━━━━ 严禁编造 ━━━━━━

下面的候选 JSON 是唯一事实来源，你没有读过原文。
- `reason` 和 `headline_zh` 只能复述候选 JSON 里出现过的内容，不许新增机制、数字、平台或功能。
- `action` 是你给出的工程建议，必须写成条件句（"如果你……可以……"），不得把建议里的细节说成是该项目已提供的能力。
- 原文没给方法细节时，`action` 就写成先读原文评估，不要硬编。

━━━━━━ 输出格式（只输出 JSON，不要代码块包裹） ━━━━━━

{{
  "id": "所选条目的 id，必须与候选 JSON 中某条完全一致",
  "headline_zh": "中文结论句标题，不超过 30 字，说清这条讲成了什么事；模型名/产品名保留原文",
  "reason": "为什么这条值得优先看，1-2 句白话，必须落到候选里的具体事实上，出现术语当场用括号讲明白",
  "action": "读完这周可以先做的一件事，一句条件句"
}}

## 候选条目（共 {total_count} 条）
{items_json}"""


@dataclass(frozen=True)
class MustRead:
    """本期必读条目及其推荐语。"""

    item: ExtractedItem
    headline_zh: str
    reason: str
    action: str


def _payload(items: list[ExtractedItem]) -> str:
    return json.dumps(
        [
            {
                "id": item.id,
                "title": item.title,
                "source": item.source_type.value,
                "summary": item.summary,
                "ai_score": item.ai_score,
                "ai_reason": item.ai_reason,
                "is_preprint": item.source_type == SourceType.ARXIV,
                "is_trending_listing": item.source_type == SourceType.GITHUB,
                "is_established": bool((item.metadata or {}).get("is_established")),
            }
            for item in items
        ],
        ensure_ascii=False,
        indent=1,
    )


def _parse(raw: str) -> dict | None:
    text = (raw or "").strip()
    if text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _is_stale_listing(item: ExtractedItem) -> bool:
    """成名已久的热榜项目描述的是状态而非本期事件，没资格当必读。"""
    return item.source_type == SourceType.GITHUB and bool(
        (item.metadata or {}).get("is_established")
    )


async def pick_must_read(items: list[ExtractedItem]) -> MustRead | None:
    """挑出本期必读；任何失败都返回 None，周报照常产出。"""
    if not items:
        return None
    if not settings.llm_configured:
        logger.info("LLM not configured, skipping must-read pick")
        return None

    # 硬拦截：提示词是软约束，这里保证常驻热榜项目绝不会成为必读
    eligible = [item for item in items if not _is_stale_listing(item)]
    if not eligible:
        logger.info("All candidates are established trending listings, no must-read")
        return None

    try:
        llm = build_chat_model(max_tokens=1024)
        prompt = MUST_READ_PROMPT.format(
            total_count=len(eligible),
            items_json=_payload(eligible),
        )
        resp = await llm.ainvoke(prompt)
    except Exception as exc:
        logger.warning("Must-read pick failed: %s", exc)
        return None

    parsed = _parse(resp.content)
    if not parsed:
        logger.warning("Must-read pick returned unparseable JSON")
        return None

    by_id = {item.id: item for item in eligible}
    chosen = by_id.get(str(parsed.get("id", "")))
    if chosen is None:
        logger.warning("Must-read pick returned unknown id %r", parsed.get("id"))
        return None

    headline = str(parsed.get("headline_zh", "")).strip()
    reason = str(parsed.get("reason", "")).strip()
    if not headline or not reason:
        logger.warning("Must-read pick missing headline or reason")
        return None

    logger.info("Must-read pick: %s (ai_score=%s)", chosen.title, chosen.ai_score)
    return MustRead(
        item=chosen,
        headline_zh=headline,
        reason=reason,
        action=str(parsed.get("action", "")).strip(),
    )
