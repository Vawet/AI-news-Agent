"""Collector Agent - 从各数据源并行采集原始数据"""

import asyncio
import logging
from datetime import datetime, timezone

from src.config import settings
from src.graph.state import PipelineState
from src.models import RawItem, SourceType
from src.sources.anthropic import AnthropicNewsSource
from src.sources.arxiv import ArxivSource
from src.sources.github import GitHubTrendingSource
from src.sources.hackernews import HackerNewsSource
from src.sources.huggingface_papers import HuggingFacePapersSource
from src.sources.huggingface_spaces import HuggingFaceSpacesSource
from src.sources.producthunt import ProductHuntSource
from src.sources.reddit import RedditRSSSource
from src.sources.rss_generic import GenericRSSSource, get_ai_blog_sources
from src.sources.twitter import TwitterSource
from src.sources.twitter_firecrawl import TwitterFirecrawlSource

logger = logging.getLogger(__name__)

# 数据源注册表
SOURCE_REGISTRY = {
    "reddit": lambda: [RedditRSSSource(sub) for sub in settings.subreddit_list],
    "hackernews": lambda: [HackerNewsSource(min_score=settings.hn_min_score)],
    "arxiv": lambda: [ArxivSource()],
    "github": lambda: [GitHubTrendingSource()],
    "huggingface": lambda: [HuggingFacePapersSource(min_upvotes=settings.hf_papers_min_upvotes)],
    "huggingface_spaces": lambda: [HuggingFaceSpacesSource()],
    "anthropic": lambda: [AnthropicNewsSource()],
    "producthunt": lambda: [ProductHuntSource(
        min_votes=settings.producthunt_min_votes,
        api_token=settings.producthunt_api_token or None,
    )],
    "rss": lambda: (
        get_ai_blog_sources()
        + [GenericRSSSource(name, url) for name, url in settings.rss_feed_list]
    ),
    "twitter": lambda: (
        # 优先使用 Firecrawl 爬取 Twitter List
        [TwitterFirecrawlSource(
            api_key=settings.firecrawl_api_key,
            list_url=settings.twitter_list_url,
        )]
        if settings.firecrawl_api_key
        else (
            [TwitterSource(
                api_key=settings.twitter_api_key,
                kol_usernames=settings.twitter_kol_list.split(",") if settings.twitter_kol_list else None,
            )]
            if settings.twitter_api_key
            else []
        )
    ),
}


def _build_sources(source_ids: list[str], report_mode: str = "daily"):
    """根据配置构建数据源实例列表"""
    sources = []
    for sid in source_ids:
        if sid == "github" and report_mode == "weekly":
            sources.append(GitHubTrendingSource(since_period="weekly"))
            continue
        factory = SOURCE_REGISTRY.get(sid)
        if factory:
            sources.extend(factory())
        else:
            logger.warning(f"Unknown source: {sid}")
    return sources


async def _fetch_one(source, since: datetime | None) -> list[RawItem]:
    """单个数据源采集，带异常捕获"""
    try:
        return await source.fetch(since=since)
    except Exception as e:
        logger.error(f"{source.source_id} fetch failed: {e}")
        return []


def _parse_boundary(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _within_window(
    item: RawItem,
    start: datetime | None,
    end: datetime | None,
) -> bool:
    """按发布时间做最终窗口约束；无发布时间的最新 feed 条目保留。"""
    if item.published_at is None:
        return True
    published = item.published_at
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return (start is None or published > start) and (end is None or published <= end)


def _quota_bucket(source_id: str) -> str:
    """RSS 子源按完整 source_id（rss:feed_name）分桶，其余按类型前缀。"""
    if source_id.startswith("rss:"):
        return source_id
    return source_id.split(":")[0]


def _quota_limits(bucket: str) -> tuple[int, int]:
    """返回 (保底条数, 上限)。"""
    min_per_src = settings.min_items_per_source
    max_per_src = settings.max_items_per_source
    if bucket in {"github", "github_trending"}:
        return 0, settings.github_trending_max_items
    if bucket == "anthropic" or bucket in {"rss:openai_blog", "rss:deepmind_blog"}:
        return max(min_per_src, 3), max(max_per_src, 6)
    if bucket == "arxiv":
        return min_per_src, settings.arxiv_max_items
    if bucket.startswith("rss:"):
        return settings.min_items_per_rss_feed, settings.max_items_per_rss_feed
    return min_per_src, max_per_src


def _item_quota_bucket(item: RawItem) -> str:
    if item.source_type == SourceType.RSS:
        feed = (item.metadata or {}).get("feed_name")
        if feed:
            return f"rss:{feed}"
    return item.source_type.value


def _smart_select(items_by_source: dict[str, list[RawItem]]) -> list[RawItem]:
    """智能选择策略：每源保底配额 + 按质量竞争剩余名额

    1. 每个源内按 score 降序排列
    2. 每个源先取 min 条（RSS 按 feed_name 保底，避免新博客被挤掉）
    3. 剩余名额从所有源的剩余条目中按 score 竞争
    4. 总数不超过 max_items_per_run
    """
    max_total = settings.max_items_per_run

    selected: list[RawItem] = []
    remaining_pool: list[RawItem] = []
    source_counts: dict[str, int] = {}

    for src_id, items in items_by_source.items():
        # 源内按 score 降序
        items.sort(key=lambda x: x.score, reverse=True)
        min_q, src_max = _quota_limits(src_id)
        # 保底配额
        guaranteed = items[: min(min_q, src_max, len(items))]
        selected.extend(guaranteed)
        source_counts[src_id] = len(guaranteed)
        # 剩余进入竞争池（受 src_max 约束）
        remaining_pool.extend(items[len(guaranteed) :])

    # 竞争剩余名额
    remaining_pool.sort(key=lambda x: x.score, reverse=True)
    for item in remaining_pool:
        if len(selected) >= max_total:
            break
        src_key = _item_quota_bucket(item)
        _, src_ceil = _quota_limits(src_key)
        if source_counts.get(src_key, 0) >= src_ceil:
            continue
        selected.append(item)
        source_counts[src_key] = source_counts.get(src_key, 0) + 1

    # 日志：各源入选数量
    for src_id, count in sorted(source_counts.items()):
        logger.info(f"  {src_id}: {count} selected")

    return selected


async def collector_node(state: PipelineState) -> dict:
    """Collector 节点：并行采集多个数据源，智能配额分配"""
    source_ids = state.get("sources_config", ["reddit"])
    sources = _build_sources(source_ids, state.get("report_mode", "daily"))

    if not sources:
        logger.warning("No data sources configured")
        return {"raw_items": [], "errors": ["No data sources configured"]}

    since = _parse_boundary(state.get("window_start"))
    until = _parse_boundary(state.get("window_end"))
    logger.info(
        f"Collecting from sources: {[s.source_id for s in sources]} "
        f"(window: {since or 'latest'} → {until or 'now'})"
    )

    # 并行采集
    tasks = [_fetch_one(s, since=since) for s in sources]
    results = await asyncio.gather(*tasks)

    # 按源分组
    items_by_source: dict[str, list[RawItem]] = {}
    total_fetched = 0
    for source, items in zip(sources, results):
        items = [item for item in items if _within_window(item, since, until)]
        src_key = _quota_bucket(source.source_id)  # "rss:openai_blog" 保持子源；"reddit:x" → "reddit"
        items_by_source.setdefault(src_key, []).extend(items)
        total_fetched += len(items)

    logger.info(f"Fetched {total_fetched} raw items from {len(items_by_source)} source types")

    # 智能选择
    selected = _smart_select(items_by_source)

    logger.info(f"Smart selection: {total_fetched} → {len(selected)} items")
    return {"raw_items": selected}
