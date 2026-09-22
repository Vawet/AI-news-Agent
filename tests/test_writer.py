"""Writer Agent tests."""

from src.agents.writer import (
    _annotate_items,
    _extract_top_story_titles,
    _normalize_dev_source_labels,
    _origin_url,
)
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

    assert "【事实】" in result
    assert "【落地参考】" in result
    assert "## 开发趋势总结" in result
    assert "## 已筛除条目说明" in result
    assert "BCIT post-training experience transfer" not in result
    assert "1 条" in result
    assert "今日速览" in result
    # 英文原标题降到来源行当链接文字，正文标题留给中文结论句
    assert (
        "`AI 8.0/10` · 来源-github · [Claude Code config](https://github.com/example/cc)"
        in result
    )


def test_extract_top_story_titles_only_reads_top_stories_section():
    markdown = "\n".join(
        [
            "# AI Daily — 2026-09-19",
            "## 🔥 Top Stories",
            "### 1. SoL-Pi Cuts Token Traffic",
            "body",
            "### 2. DeepSeek V4.1 Flash",
            "body",
            "## 📰 Featured",
            "### Model Capabilities",
            "- **Gemini 3.8 Live** — summary",
        ]
    )

    assert _extract_top_story_titles(markdown) == [
        "SoL-Pi Cuts Token Traffic",
        "DeepSeek V4.1 Flash",
    ]


def test_dev_source_label_follows_url_domain():
    markdown = (
        "`AI 8.7/10` · [来源-huggingface](https://arxiv.org/abs/2609.20519)\n"
        "`AI 7.0/10` · [来源-hackernews](https://twitter.com/trq212/status/1)\n"
        "`AI 7.8/10` · [来源-hackernews](https://alignment.openai.com/reports/x/)\n"
    )

    result = _normalize_dev_source_labels(markdown)

    assert "[来源-arxiv](https://arxiv.org/abs/2609.20519)" in result
    assert "[来源-x](https://twitter.com/trq212/status/1)" in result
    assert "[来源-rss](https://alignment.openai.com/reports/x/)" in result


def test_dev_plain_source_line_becomes_clickable_link():
    markdown = "**AI 评分：8.7/10** 来源-huggingface — https://arxiv.org/abs/2609.20519"

    result = _normalize_dev_source_labels(markdown)

    assert "[来源-arxiv](https://arxiv.org/abs/2609.20519)" in result
    assert " — https://arxiv.org" not in result


def test_dev_source_label_corrected_without_clobbering_original_title():
    markdown = (
        "`AI 8.7/10` · 来源-huggingface · "
        "[DENSE Distills Agent Trajectories](https://arxiv.org/abs/2609.21423)\n"
    )

    result = _normalize_dev_source_labels(markdown)

    assert "来源-arxiv" in result
    assert "[DENSE Distills Agent Trajectories](https://arxiv.org/abs/2609.21423)" in result


def _must_read_fixture():
    from src.agents.must_read import MustRead

    return MustRead(
        item=ExtractedItem(
            id="1",
            source_type=SourceType.RSS,
            title="Linear Reworks CI to Handle AI Coding Bottleneck",
            content="body",
            url="https://linear.app/now/ci-bottleneck-reworked",
            summary="CI rework",
            ai_score=7.8,
            scoring_profile="tech-news",
        ),
        headline_zh="Linear 重做 CI，合并等待从 6 分降到 5 分",
        reason="有具体前后数据，改法可直接照搬。",
        action="如果你的 CI 超过 5 分钟，可以先把 lint 和测试拆开计时。",
    )


def test_inject_must_read_goes_above_the_first_section():
    from src.agents.writer import _inject_must_read

    markdown = "# AI 周报（开发落地版） — 2026-09-22\n\n> 涵盖 7 条\n\n## ⚡ 本期速览\n\n- a\n"

    result = _inject_must_read(markdown, _must_read_fixture(), "本期")

    assert result.index("只看一条就看这个") < result.index("本期速览")
    assert "Linear 重做 CI，合并等待从 6 分降到 5 分" in result
    assert "**下一步：**" in result


def test_inject_must_read_is_noop_without_a_pick():
    from src.agents.writer import _inject_must_read

    markdown = "# AI 周报\n\n## ⚡ 本期速览\n"

    assert _inject_must_read(markdown, None, "本期") == markdown


def test_items_to_json_includes_content_excerpt():
    """写作模型必须拿到原文节选，只给 summary 会逼出阶段名罗列这类空话。"""
    import json

    from src.agents.writer import _items_to_json

    item = ExtractedItem(
        id="1",
        source_type=SourceType.GITHUB,
        title="Security audit skill",
        content="The skill runs a structured audit in six phases, writing architecture.md "
        "and coverage-ledger.json before dispatching isolated hunters.",
        url="https://github.com/cloudflare/security-audit-skill",
        summary="A coding-agent skill for multi-phase security audits.",
        ai_score=8.5,
        scoring_profile="tech-news",
    )

    payload = json.loads(_items_to_json([item]))

    assert "coverage-ledger.json" in payload[0]["content_excerpt"]


def test_content_excerpt_is_capped():
    from src.agents.writer import _EXCERPT_LIMIT, _content_excerpt

    item = ExtractedItem(
        id="1",
        source_type=SourceType.RSS,
        title="Long post",
        content="x" * 5000,
        url="https://example.com/1",
        summary="s",
        scoring_profile="tech-news",
    )

    assert len(_content_excerpt(item)) == _EXCERPT_LIMIT


def test_content_excerpt_prefers_enriched_full_content():
    from src.agents.writer import _content_excerpt

    item = ExtractedItem(
        id="1",
        source_type=SourceType.HACKERNEWS,
        title="Post",
        content="thin rss blurb",
        url="https://example.com/1",
        summary="s",
        scoring_profile="tech-news",
        metadata={"full_content": "the enriched article body"},
    )

    assert _content_excerpt(item) == "the enriched article body"


def test_brief_items_stay_lean():
    """简讯条目不带节选，避免为一句话的条目白烧 token。"""
    import json

    from src.agents.writer import _items_to_json

    item = ExtractedItem(
        id="1",
        source_type=SourceType.RSS,
        title="Minor update",
        content="x" * 3000,
        url="https://example.com/1",
        summary="s",
        scoring_profile="tech-news",
    )

    payload = json.loads(_items_to_json([item], brief=True))

    assert "content_excerpt" not in payload[0]
