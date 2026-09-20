"""数据源采集器测试"""

import pytest

from src.agents.collector import SOURCE_REGISTRY, _smart_select
from src.models import RawItem, SourceType
from src.sources.reddit import RedditRSSSource
from src.sources.hackernews import HackerNewsSource
from src.sources.arxiv import ArxivSource


def test_reddit_source_init():
    source = RedditRSSSource("LocalLLaMA")
    assert source.source_id == "reddit:LocalLLaMA"
    assert "LocalLLaMA" in source.url


def test_hn_source_init():
    source = HackerNewsSource(min_score=100)
    assert source.source_id == "hackernews"
    assert "100" in source.url


def test_arxiv_source_init():
    source = ArxivSource(categories=["cs.AI"])
    assert source.source_id == "arxiv"
    assert len(source.urls) == 1


@pytest.mark.asyncio
async def test_reddit_fetch_live():
    """集成测试：实际从 Reddit 拉取数据（需要网络）"""
    source = RedditRSSSource("LocalLLaMA")
    items = await source.fetch()
    # RSS 应该返回一些条目（除非网络不通）
    # 这里只验证不会崩溃
    assert isinstance(items, list)
    if items:
        assert items[0].source_type.value == "reddit"
        assert items[0].title


def test_registry_includes_new_sources():
    assert "huggingface_spaces" in SOURCE_REGISTRY
    assert "anthropic" in SOURCE_REGISTRY
    spaces = SOURCE_REGISTRY["huggingface_spaces"]()
    anth = SOURCE_REGISTRY["anthropic"]()
    assert spaces[0].source_id == "huggingface_spaces"
    assert anth[0].source_id == "anthropic"


def _rss_item(feed: str, title: str, score: int) -> RawItem:
    return RawItem(
        source_type=SourceType.RSS,
        source_id=f"{feed}-{title}",
        title=title,
        score=score,
        metadata={"feed_name": feed},
    )


def test_smart_select_rss_per_feed_floor():
    items_by_source = {
        "rss:openai_blog": [_rss_item("openai_blog", f"o{i}", 10 - i) for i in range(5)],
        "rss:kenashe": [_rss_item("kenashe", f"k{i}", 1) for i in range(5)],
    }
    selected = _smart_select(items_by_source)
    feeds = {item.metadata["feed_name"] for item in selected}
    assert "openai_blog" in feeds
    assert "kenashe" in feeds
    kenashe_count = sum(1 for i in selected if i.metadata["feed_name"] == "kenashe")
    openai_count = sum(1 for i in selected if i.metadata["feed_name"] == "openai_blog")
    assert kenashe_count >= 2
    assert openai_count >= 3
    assert openai_count <= 6


def _github_item(name: str, stars_today: int) -> RawItem:
    return RawItem(
        source_type=SourceType.GITHUB,
        source_id=f"github:{name}",
        title=name,
        score=stars_today,
        metadata={"feed_name": "unused"},
    )


def test_smart_select_caps_github_at_three():
    items_by_source = {
        "github_trending": [_github_item(f"org/repo-{i}", 100 - i) for i in range(5)],
    }
    selected = _smart_select(items_by_source)
    assert len(selected) == 3

