"""Enrichment and content-normalization tests."""

from src.agents.enricher import _community_summary
from src.sources.github import GitHubTrendingSource
from src.tools.content import html_to_text


def test_html_to_text_strips_markup():
    html = "<html><script>x</script><p>Hello <b>world</b></p>"
    assert html_to_text(html) == "Hello world"


def test_github_parse_stars_today():
    html = '<span>1,234 stars today</span>'
    assert GitHubTrendingSource._parse_stars_today(html) == 1234


def test_community_summary_lists_top_comments():
    text = _community_summary(
        [{"author": "alice", "score": 0, "text": "This changes agent evals."}],
        42,
    )
    assert "42 comments" in text
    assert "alice: This changes agent evals." in text
