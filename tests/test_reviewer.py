"""Reviewer Agent tests."""

from src.agents.reviewer import _merge_items, _parse_merge_groups
from src.models import ExtractedItem, SourceType


def _item(item_id: str, score: float) -> ExtractedItem:
    return ExtractedItem(
        id=item_id,
        source_type=SourceType.HACKERNEWS,
        title=f"News {item_id}",
        content="content",
        url=f"https://example.com/{item_id}",
        importance_score=score,
        ai_score=score,
        ai_reason="reason",
        scoring_profile="tech-news",
    )


def test_parse_merge_groups_object():
    raw = '{"groups":[{"group":[0,1],"keep":0,"reason":"same event"}]}'
    assert _parse_merge_groups(raw)[0]["group"] == [0, 1]


def test_parse_invalid_merge_groups_returns_empty():
    assert _parse_merge_groups("not json") == []


def test_merge_always_keeps_highest_profile_score():
    items = [_item("low", 7.2), _item("high", 9.1), _item("other", 8.0)]
    groups = [{"group": [0, 1], "keep": 0, "reason": "same event"}]

    merged = _merge_items(items, groups)

    assert [item.id for item in merged] == ["high", "other"]
