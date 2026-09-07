"""Cleaner Agent 测试"""

import pytest

from src.agents.cleaner import (
    _clean_one,
    _compute_quality_score,
    _normalize_whitespace,
    _simple_dedup,
    _strip_html,
)
from src.models import CleanedItem, RawItem, SourceType


def test_strip_html():
    assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"
    assert _strip_html("&amp; test &lt;") == "& test <"
    assert _strip_html("no html here") == "no html here"


def test_normalize_whitespace():
    assert _normalize_whitespace("  hello   world  ") == "hello world"
    assert _normalize_whitespace("line\n\nnew") == "line new"


def test_compute_quality_score():
    # 低质量条目
    low = RawItem(source_type=SourceType.REDDIT, source_id="1", title="Hi")
    assert _compute_quality_score(low) < 0.5

    # 长文 + 高赞仍有基本质量，但不应压过官方来源
    from datetime import datetime, timezone

    high = RawItem(
        source_type=SourceType.REDDIT,
        source_id="2",
        title="A comprehensive guide to fine-tuning LLMs",
        content="x" * 300,
        score=600,
        published_at=datetime.now(tz=timezone.utc),
    )
    official = RawItem(
        source_type=SourceType.RSS,
        source_id="3",
        title="How we evaluate model reliability",
        content="x" * 80,
        url="https://openai.com/index/reliability",
        score=0,
        published_at=datetime.now(tz=timezone.utc),
        metadata={"feed_name": "openai_blog"},
    )
    assert _compute_quality_score(official) > _compute_quality_score(high)
    assert _compute_quality_score(high) >= 0.6


def test_training_research_is_downranked_vs_harness():
    from datetime import datetime, timezone

    now = datetime.now(tz=timezone.utc)
    training = RawItem(
        source_type=SourceType.ARXIV,
        source_id="paper-1",
        title="GRPO post-training recipe for MoE LLMs",
        content="x" * 400,
        url="https://arxiv.org/abs/2601.00001",
        published_at=now,
    )
    harness = RawItem(
        source_type=SourceType.RSS,
        source_id="blog-1",
        title="A reusable eval harness for coding agents",
        content="x" * 400,
        url="https://anthropic.com/engineering/harness",
        published_at=now,
    )
    cleaned_training = _clean_one(training)
    cleaned_harness = _clean_one(harness)
    assert cleaned_training.metadata["is_training_research"] is True
    assert cleaned_training.metadata["focus_hints"] == []
    assert cleaned_harness.quality_score > cleaned_training.quality_score


def test_clean_one():
    raw = RawItem(
        source_type=SourceType.REDDIT,
        source_id="test_123",
        title="<b>Test</b>  Title",
        content="<p>Some   content</p>",
    )
    cleaned = _clean_one(raw)
    assert cleaned.title == "Test Title"
    assert cleaned.content == "Some content"
    assert cleaned.id  # 应该生成了 ID


def test_clean_one_tags_official_focus():
    raw = RawItem(
        source_type=SourceType.ANTHROPIC,
        source_id="news-1",
        title="Anthropic on measuring agentic evals",
        content="A research note on harness design.",
        url="https://www.anthropic.com/news/evals",
    )
    cleaned = _clean_one(raw)
    assert cleaned.metadata["is_official"] is True
    assert "AI Insights" in cleaned.metadata["focus_hints"]
    assert "Harness Methodology" in cleaned.metadata["focus_hints"]


def test_simple_dedup():
    items = [
        CleanedItem(id="a", source_type=SourceType.REDDIT, title="Same Title", content="c1"),
        CleanedItem(id="b", source_type=SourceType.REDDIT, title="Same Title", content="c2"),
        CleanedItem(id="c", source_type=SourceType.REDDIT, title="Different Title", content="c3"),
    ]
    result = _simple_dedup(items)
    dupes = [i for i in result if i.is_duplicate]
    assert len(dupes) == 1
    assert dupes[0].id == "b"
