"""Writer Agent tests."""

from src.agents.writer import _annotate_items, _origin_url
from src.models import ExtractedItem, SourceType


def _item(url: str, metadata: dict | None = None) -> ExtractedItem:
    return ExtractedItem(
        id="1",
        source_type=SourceType.REDDIT,
        title="Agent framework release",
        content="body",
        url=url,
        summary="A new agent framework",
        ai_score=8.4,
        ai_reason="Useful to agent developers",
        scoring_profile="tech-news",
        metadata=metadata or {},
    )


def test_origin_url_prefers_external_link():
    item = _item(
        "https://www.reddit.com/r/x/comments/1/",
        {"original_url": "https://example.com/post"},
    )
    assert _origin_url(item) == "https://example.com/post"


def test_origin_url_falls_back_to_item_url():
    assert _origin_url(_item("https://example.com/a")) == "https://example.com/a"


def test_annotate_adds_score_and_visible_url():
    item = _item("https://example.com/a")
    markdown = "- **Agent framework release** — summary [Source-reddit](https://example.com/a)"

    result = _annotate_items(markdown, [item])

    assert "**AI Score: 8.4/10**" in result
    assert result.endswith("— https://example.com/a")


def test_annotate_does_not_duplicate_existing_annotations():
    item = _item("https://example.com/a")
    markdown = (
        "- **Agent framework release** — summary **AI Score: 8.4/10** "
        "[Source-reddit](https://example.com/a) — https://example.com/a"
    )

    assert _annotate_items(markdown, [item]) == markdown


def test_annotate_matches_line_by_origin_url():
    item = _item(
        "https://www.reddit.com/r/x/comments/1/",
        {"original_url": "https://example.com/post"},
    )
    markdown = "- **Agent framework release** — summary [Source-reddit](https://example.com/post)"

    result = _annotate_items(markdown, [item])

    assert result.endswith("— https://example.com/post")
    assert "**AI Score: 8.4/10**" in result


def test_fallback_dev_markdown_contains_required_sections():
    from src.agents.writer import _build_fallback_dev_markdown

    items = [
        ExtractedItem(
            id="1",
            source_type=SourceType.GITHUB,
            title="Claude Code config",
            content="body",
            url="https://github.com/example/cc",
            summary="A config repo",
            ai_score=8.0,
            ai_reason="Useful for agent orchestration",
            scoring_profile="tech-news",
        ),
        ExtractedItem(
            id="2",
            source_type=SourceType.ARXIV,
            title="BCIT post-training experience transfer",
            content="body",
            url="https://arxiv.org/abs/123",
            summary="Post-training experience replay for LLM",
            ai_score=7.8,
            ai_reason="About LLM post-training",
            scoring_profile="tech-news",
        ),
    ]
    result = _build_fallback_dev_markdown(items, "2026-09-05")

    assert "【人话版】" in result
    assert "【开发能用上】" in result
    assert "## 开发趋势总结" in result
    assert "## 已筛除条目说明" in result
    assert "BCIT post-training experience transfer" not in result
    assert "1 条" in result
