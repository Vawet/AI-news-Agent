"""数据源适配器测试 - 覆盖所有数据源"""

import pytest

from src.sources.base import BaseSource
from src.sources.reddit import RedditRSSSource
from src.sources.hackernews import HackerNewsSource
from src.sources.arxiv import ArxivSource
from src.sources.github import GitHubTrendingSource
from src.sources.rss_generic import AI_BLOG_FEEDS, GenericRSSSource, get_ai_blog_sources
from src.sources.twitter import TwitterSource


class TestRedditSource:
    def test_init(self):
        source = RedditRSSSource("LocalLLaMA")
        assert source.source_id == "reddit:LocalLLaMA"
        assert "LocalLLaMA" in source.url
        assert isinstance(source, BaseSource)

    def test_default_interval(self):
        source = RedditRSSSource("test")
        assert source.default_interval == 900


class TestHackerNewsSource:
    def test_init(self):
        source = HackerNewsSource(min_score=100)
        assert source.source_id == "hackernews"
        assert "100" in source.url

    def test_url_has_query(self):
        source = HackerNewsSource()
        assert "q=" in source.url

    def test_default_interval(self):
        source = HackerNewsSource()
        assert source.default_interval == 1800



class TestArxivSource:
    def test_init(self):
        source = ArxivSource(categories=["cs.AI", "cs.CL"])
        assert source.source_id == "arxiv"
        assert len(source.urls) == 2

    def test_default_categories(self):
        source = ArxivSource()
        assert "cs.AI" in source.categories

    def test_extract_arxiv_id(self):
        assert ArxivSource._extract_arxiv_id("http://arxiv.org/abs/2401.12345") == "2401.12345"

    def test_clean_title(self):
        assert ArxivSource._clean_title("  Hello   World  ") == "Hello World"



class TestGitHubSource:
    def test_init(self):
        source = GitHubTrendingSource()
        assert source.source_id == "github_trending"
        assert source.default_interval == 14400



class TestGenericRSSSource:
    def test_init(self):
        source = GenericRSSSource("test_blog", "https://example.com/feed.xml")
        assert source.source_id == "rss:test_blog"
        assert source.default_interval == 3600

    def test_ai_blog_sources(self):
        sources = get_ai_blog_sources()
        ids = [s.source_id for s in sources]
        assert "rss:openai_blog" in ids
        assert "rss:ollama_blog" not in ids
        assert all(isinstance(s, GenericRSSSource) for s in sources)

    def test_builtin_feed_list(self):
        assert AI_BLOG_FEEDS["openai_blog"] == "https://openai.com/news/rss.xml"
        for name in (
            "aws_blog",
            "devto_ai",
            "towards_data_science",
            "infoq_cn",
            "juejin",
            "bytebytego",
            "developers_digest",
            "kenashe",
        ):
            assert name in AI_BLOG_FEEDS
        assert "anthropic" not in AI_BLOG_FEEDS
        assert "ollama_blog" not in AI_BLOG_FEEDS


class TestHuggingFaceSpacesSource:
    def test_init(self):
        from src.sources.huggingface_spaces import HuggingFaceSpacesSource

        source = HuggingFaceSpacesSource(limit=30)
        assert source.source_id == "huggingface_spaces"
        assert source.default_interval == 3600

    def test_parse_spaces_json(self):
        from src.models import SourceType
        from src.sources.huggingface_spaces import parse_spaces_json

        payload = [
            {
                "id": "user/demo-space",
                "author": "user",
                "likes": 42,
                "trendingScore": 88,
                "sdk": "gradio",
                "lastModified": "2026-09-01T12:00:00.000Z",
                "cardData": {
                    "title": "Demo Space",
                    "short_description": "A demo app",
                },
            },
            {"likes": 1},
        ]
        items = parse_spaces_json(payload)
        assert len(items) == 1
        item = items[0]
        assert item.source_type == SourceType.HUGGINGFACE_SPACES
        assert item.source_id == "user/demo-space"
        assert item.title == "Demo Space"
        assert item.url == "https://huggingface.co/spaces/user/demo-space"
        assert item.score == 88
        assert item.metadata["sdk"] == "gradio"
        assert "A demo app" in item.content

    def test_parse_spaces_json_invalid(self):
        from src.sources.huggingface_spaces import parse_spaces_json

        assert parse_spaces_json({"error": "nope"}) == []
        assert parse_spaces_json([]) == []


class TestAnthropicNewsSource:
    def test_init(self):
        from src.sources.anthropic import AnthropicNewsSource

        source = AnthropicNewsSource()
        assert source.source_id == "anthropic"
        assert source.default_interval == 3600

    def test_parse_sitemap_news(self):
        from src.sources.anthropic import parse_sitemap_news

        xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://www.anthropic.com/news</loc>
    <lastmod>2026-09-01</lastmod>
  </url>
  <url>
    <loc>https://www.anthropic.com/news/claude-opus-release</loc>
    <lastmod>2026-09-02T10:00:00Z</lastmod>
  </url>
  <url>
    <loc>https://www.anthropic.com/research/foo</loc>
  </url>
</urlset>
"""
        entries = parse_sitemap_news(xml)
        assert len(entries) == 1
        url, lastmod, title = entries[0]
        assert url.endswith("/news/claude-opus-release")
        assert lastmod is not None
        assert "claude opus release" in title.lower()

    def test_parse_news_list_html(self):
        from src.sources.anthropic import parse_news_list_html

        html = """
        <html><body>
          <a href="/news/introducing-claude">Introducing Claude</a>
          <a href="https://www.anthropic.com/news/safety-update">Safety</a>
          <a href="/news">All news</a>
          <a href="/research/x">Research</a>
        </body></html>
        """
        entries = parse_news_list_html(html)
        urls = {e[0] for e in entries}
        assert "https://www.anthropic.com/news/introducing-claude" in urls
        assert "https://www.anthropic.com/news/safety-update" in urls
        assert "https://www.anthropic.com/news" not in urls


class TestTwitterSource:
    def test_init(self):
        source = TwitterSource(api_key="test_key")
        assert source.source_id == "twitter"
        assert len(source.kol_usernames) > 0

    def test_no_api_key(self):
        source = TwitterSource(api_key="")
        assert source.default_interval == 900

    @pytest.mark.asyncio
    async def test_fetch_no_key(self):
        source = TwitterSource(api_key="")
        items = await source.fetch()
        assert items == []

    def test_parse_twitter_time(self):
        result = TwitterSource._parse_twitter_time("Wed Feb 12 10:30:00 +0000 2025")
        assert result is not None
        assert result.year == 2025

    def test_parse_twitter_time_empty(self):
        assert TwitterSource._parse_twitter_time("") is None
