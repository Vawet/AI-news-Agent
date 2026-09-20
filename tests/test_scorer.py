from src.agents.scorer import _item_payload, _parse_json_object, _select_items
from src.models import ExtractedItem, SourceType
from src.scoring.profiles import ScoringProfile, load_profiles


def _item(
    item_id: str,
    score: float,
    category: str,
    title: str,
    url: str,
) -> ExtractedItem:
    return ExtractedItem(
        id=item_id,
        source_type=SourceType.HACKERNEWS,
        title=title,
        content="body",
        url=url,
        summary=f"Summary for {title}",
        importance_score=max(1, score),
        ai_score=score,
        ai_reason="Useful to agent developers",
        scoring_profile="test",
        score_tags=[category],
    )


def test_builtin_tech_news_profile_loads():
    profile = load_profiles()["tech-news"]
    assert profile.threshold == 7.0
    assert profile.category_groups["Model Capabilities"] == 6
    assert profile.category_groups["Harness Methodology"] == 7
    assert profile.category_groups["AI Insights"] == 4
    assert profile.category_groups["Open Source"] == 3
    assert profile.category_minimums["Harness Methodology"] == 2
    assert profile.category_minimums["Model Capabilities"] == 1
    assert profile.category_minimums["AI Insights"] == 1
    assert "business ai agent" in profile.analysis_prompt.lower()
    assert "pre-training" in profile.analysis_prompt.lower()
    assert "Harness Methodology" in profile.analysis_prompt


def test_payload_uses_structured_briefs_not_raw_800_cut():
    item = _item("1", 8, "Agents", "Title", "https://example.com/1")
    item.content = "x" * 5000
    item.platform_score = 123
    item.metadata = {
        "num_comments": 5,
        "upvote_ratio": 0.9,
        "official_summary": "Official abstract " * 40,
        "full_content": "BODY" * 2000,
        "community_summary": "Top comments agree this matters for agents.",
        "github_repo": "org/repo",
    }

    payload = _item_payload(0, item)

    assert "content" not in payload
    assert payload["content_brief"].startswith("BODY")
    assert len(payload["content_brief"]) == 2500
    assert payload["official_summary"].startswith("Official abstract")
    assert payload["community"].startswith("Top comments")
    assert payload["engagement_context"]["platform_score"] == 123
    assert payload["links"]["github_repo"] == "org/repo"
    assert payload["is_official"] is False
    assert payload["is_training_research"] is False
    assert payload["focus_hints"] == []


def test_invalid_json_is_not_salvaged():
    assert _parse_json_object('analysis first {"items": []}') is None


def test_selection_applies_threshold_category_cap_and_score_order():
    profile = ScoringProfile(
        name="test",
        description="test",
        threshold=7.0,
        max_items=3,
        category_groups={"Agents": 1, "Other": 1},
        analysis_prompt="",
        match_prompt="",
    )
    items = [
        _item("1", 9, "Agents", "Agent framework alpha", "https://example.com/1"),
        _item("2", 8, "Agents", "Different agent benchmark", "https://example.com/2"),
        _item("3", 7.5, "Other", "Model serving release", "https://example.com/3"),
        _item("4", 6.9, "Other", "Below threshold", "https://example.com/4"),
    ]

    selected = _select_items(items, {"test": profile})

    assert [item.id for item in selected] == ["1", "3"]


def test_selection_caps_github_items_at_three():
    profile = ScoringProfile(
        name="test",
        description="test",
        threshold=7.0,
        max_items=10,
        category_groups={"Open Source": 5, "Other": 5},
        analysis_prompt="",
        match_prompt="",
    )
    titles = [
        "vLLM ships new paged attention kernel",
        "Hermes agent harness adds persistent memory",
        "llama.cpp Vulkan backend rewrite",
        "SGLang speculative decoding for MoE",
    ]
    items = []
    for idx, title in enumerate(titles):
        item = _item(
            str(idx),
            9 - idx * 0.1,
            "Open Source",
            title,
            f"https://github.com/org/repo-{idx}",
        )
        item.source_type = SourceType.GITHUB
        items.append(item)

    selected = _select_items(items, {"test": profile})

    assert len(selected) == 3
    assert [item.id for item in selected] == ["0", "1", "2"]


def test_selection_reserves_qualified_pillar_coverage():
    profile = ScoringProfile(
        name="test",
        description="test",
        threshold=7.0,
        max_items=4,
        category_groups={
            "Harness Methodology": 4,
            "Model Capabilities": 4,
            "AI Insights": 4,
            "Other": 4,
        },
        category_minimums={
            "Harness Methodology": 2,
            "Model Capabilities": 1,
            "AI Insights": 1,
        },
        analysis_prompt="",
        match_prompt="",
    )
    items = [
        _item("other-1", 9.9, "Other", "Popular general AI story", "https://example.com/o1"),
        _item("other-2", 9.8, "Other", "Another popular AI story", "https://example.com/o2"),
        _item("h1", 8.4, "Harness Methodology", "Agent context architecture", "https://example.com/h1"),
        _item("h2", 8.1, "Harness Methodology", "Tool recovery patterns", "https://example.com/h2"),
        _item("m1", 7.9, "Model Capabilities", "New coding model API", "https://example.com/m1"),
        _item("i1", 7.7, "AI Insights", "Lab lessons from agent deployment", "https://example.com/i1"),
    ]

    selected = _select_items(items, {"test": profile})

    assert {item.id for item in selected} == {"h1", "h2", "m1", "i1"}


def test_open_source_category_requires_github_source():
    profile = ScoringProfile(
        name="test",
        description="test",
        threshold=7.0,
        max_items=3,
        category_groups={"Open Source": 3, "Other": 3},
        analysis_prompt="",
        match_prompt="",
    )
    paper = _item(
        "paper",
        9.0,
        "Open Source",
        "Paper with accompanying code",
        "https://arxiv.org/abs/2609.00001",
    )
    repo = _item(
        "repo",
        8.0,
        "Open Source",
        "Reusable agent runtime",
        "https://github.com/org/runtime",
    )
    repo.source_type = SourceType.GITHUB

    selected = _select_items([paper, repo], {"test": profile})

    assert [item.id for item in selected] == ["repo"]
