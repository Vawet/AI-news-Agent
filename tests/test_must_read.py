"""必读挑选的准入规则测试"""

import pytest

from src.agents.must_read import _is_stale_listing, _parse, pick_must_read
from src.models import ExtractedItem, SourceType


def _item(item_id: str, source: SourceType, **metadata) -> ExtractedItem:
    return ExtractedItem(
        id=item_id,
        source_type=source,
        title=f"title-{item_id}",
        content="body",
        url=f"https://example.com/{item_id}",
        summary="summary",
        ai_score=8.0,
        scoring_profile="tech-news",
        metadata=metadata,
    )


def test_established_trending_listing_is_stale():
    assert _is_stale_listing(_item("1", SourceType.GITHUB, is_established=True))


def test_young_trending_listing_is_not_stale():
    assert not _is_stale_listing(_item("1", SourceType.GITHUB, is_established=False))


def test_non_github_item_is_never_stale():
    assert not _is_stale_listing(_item("1", SourceType.ARXIV, is_established=True))


@pytest.mark.asyncio
async def test_pick_returns_none_when_every_candidate_is_an_established_listing():
    """claude-code 那类常驻热榜项目不该成为必读，宁可不给必读。"""
    items = [
        _item("1", SourceType.GITHUB, is_established=True),
        _item("2", SourceType.GITHUB, is_established=True),
    ]

    assert await pick_must_read(items) is None


@pytest.mark.asyncio
async def test_pick_returns_none_for_empty_input():
    assert await pick_must_read([]) is None


def test_parse_strips_code_fences():
    assert _parse('```json\n{"id": "1"}\n```') == {"id": "1"}


def test_parse_rejects_non_object_payloads():
    assert _parse("[1, 2]") is None
    assert _parse("not json") is None
