"""Cleaner Agent - 将原始数据标准化为统一格式，并按编辑焦点排序"""

import hashlib
import logging
import re
from html import unescape

from src.graph.state import PipelineState
from src.models import CleanedItem, RawItem
from src.scoring.focus import (
    annotate_focus,
    focus_hints,
    is_official_source,
    is_training_research,
)

logger = logging.getLogger(__name__)


def _strip_html(text: str) -> str:
    """移除 HTML 标签"""
    text = unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def _normalize_whitespace(text: str) -> str:
    """规范化空白字符"""
    return re.sub(r"\s+", " ", text).strip()


def _compute_quality_score(item: RawItem) -> float:
    """质量分：官方来源与内容完整度优先，平台热度只作弱信号。"""
    score = 0.25

    if 10 < len(item.title) < 200:
        score += 0.1

    content_len = len(item.content)
    if content_len > 50:
        score += 0.1
    if content_len > 200:
        score += 0.1

    if is_training_research(item):
        score -= 0.2
    elif is_official_source(item):
        score += 0.3
    elif item.source_type.value == "github":
        score += 0.15

    hints = focus_hints(item)
    if "Model Capabilities" in hints or "Harness Methodology" in hints:
        score += 0.1

    # 热度上限压低，避免高赞闲聊压过官方博客
    if item.score > 50:
        score += 0.05
    if item.score > 200:
        score += 0.05

    if item.published_at:
        score += 0.05

    return max(0.0, min(score, 1.0))


def _make_id(item: RawItem) -> str:
    """生成全局唯一 ID"""
    raw = f"{item.source_type.value}:{item.source_id}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _clean_one(item: RawItem) -> CleanedItem:
    """清洗单条原始数据"""
    title = _normalize_whitespace(_strip_html(item.title))
    content = _normalize_whitespace(_strip_html(item.content))
    metadata = annotate_focus(item.metadata, item)

    return CleanedItem(
        id=_make_id(item),
        source_type=item.source_type,
        title=title,
        content=content,
        url=item.url,
        author=item.author,
        published_at=item.published_at,
        language="en",  # v0.1 暂不做语言检测
        quality_score=_compute_quality_score(item),
        platform_score=item.score,
        metadata=metadata,
    )


def _simple_dedup(items: list[CleanedItem]) -> list[CleanedItem]:
    """基于标题相似度的简单去重"""
    seen_titles: dict[str, str] = {}  # normalized_title -> id
    result: list[CleanedItem] = []

    for item in items:
        # 标题标准化用于比较
        norm_title = item.title.lower().strip()
        if norm_title in seen_titles:
            item.is_duplicate = True
            item.duplicate_of = seen_titles[norm_title]
            logger.debug(f"Duplicate title: {item.title[:50]}...")
        else:
            seen_titles[norm_title] = item.id
        result.append(item)

    return result


async def cleaner_node(state: PipelineState) -> dict:
    """Cleaner 节点：批量清洗原始数据"""
    raw_items = state.get("raw_items", [])
    if not raw_items:
        logger.warning("No raw items to clean")
        return {"cleaned_items": []}

    logger.info(f"Cleaning {len(raw_items)} raw items ...")

    # 清洗
    cleaned = [_clean_one(item) for item in raw_items]

    # 按质量分排序（官方 / 焦点内容优先进入后续 LLM 阶段）
    cleaned.sort(key=lambda x: x.quality_score, reverse=True)

    # 简单去重
    cleaned = _simple_dedup(cleaned)

    valid_count = sum(1 for c in cleaned if not c.is_duplicate)
    logger.info(f"Cleaning done: {len(cleaned)} items, {valid_count} valid, {len(cleaned) - valid_count} duplicates")

    return {"cleaned_items": cleaned}
