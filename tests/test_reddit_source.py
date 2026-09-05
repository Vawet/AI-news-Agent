"""Reddit source tests."""

from src.sources.reddit import _extract_external_url


def test_extracts_external_article_link():
    summary = (
        '<a href="https://www.reddit.com/r/x/comments/1/">[comments]</a>'
        '<a href="https://example.com/article?a=1&amp;b=2">[link]</a>'
    )
    assert _extract_external_url(summary) == "https://example.com/article?a=1&b=2"


def test_self_post_has_no_external_link():
    summary = '<a href="https://www.reddit.com/r/x/comments/1/">[comments]</a>'
    assert _extract_external_url(summary) == ""
