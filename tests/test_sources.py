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

    @staticmethod
    def _repo(name: str, *, established=False, velocity=0.0, rank=999):
        from src.models import RawItem, SourceType

        return RawItem(
            source_type=SourceType.GITHUB,
            source_id=f"github:{name}",
            title=name,
            url=f"https://github.com/{name}",
            metadata={
                "is_established": established,
                "relative_velocity": velocity,
                "feed_rank": rank,
            },
        )

    def test_select_trending_puts_young_repos_before_established_giants(self):
        items = [
            # 巨无霸霸占榜首，且实测增速更高，仍要让位给新兴项目
            self._repo("org/giant", established=True, velocity=0.9, rank=1),
            self._repo("org/young", established=False, velocity=0.01, rank=9),
        ]
        selected = GitHubTrendingSource._select_trending(items, 1)
        assert [item.title for item in selected] == ["org/young"]

    def test_select_trending_uses_measured_velocity_within_same_age_group(self):
        items = [
            self._repo("org/slow", velocity=0.01, rank=1),
            self._repo("org/fast", velocity=0.90, rank=8),
        ]
        selected = GitHubTrendingSource._select_trending(items, 1)
        assert [item.title for item in selected] == ["org/fast"]

    def test_select_trending_falls_back_to_feed_rank_without_measured_growth(self):
        items = [
            self._repo("org/rank9", rank=9),
            self._repo("org/rank2", rank=2),
        ]
        selected = GitHubTrendingSource._select_trending(items, 1)
        assert [item.title for item in selected] == ["org/rank2"]

    def test_relative_velocity_ranks_young_repo_above_established_giant(self):
        # claude-code 量级：14.7 万星、周涨 1500
        giant = GitHubTrendingSource._relative_velocity(147505, 1500)
        # 新兴项目：3000 星、周涨 2000
        rising = GitHubTrendingSource._relative_velocity(3000, 2000)
        assert rising > giant

    def test_relative_velocity_is_zero_when_baseline_is_missing(self):
        """没有历史快照就是不知道增速，必须返回 0 交给 feed_rank，不能用年龄倒数假装。"""
        assert GitHubTrendingSource._relative_velocity(3000, None) == 0.0
        assert GitHubTrendingSource._relative_velocity(147505, None) == 0.0

    def test_relative_velocity_handles_zero_stars(self):
        assert GitHubTrendingSource._relative_velocity(0, 10) == 0.0

    def test_measure_growth_uses_earliest_prior_snapshot(self):
        snapshots = {"2026-09-15": 1000, "2026-09-18": 1500}
        assert (
            GitHubTrendingSource._measure_growth(snapshots, 3000, "2026-09-22") == 2000
        )

    def test_measure_growth_ignores_same_day_snapshot(self):
        """同一天重跑不能把几分钟前的快照当基线，否则排序被噪声污染。"""
        snapshots = {"2026-09-22": 2995}
        assert GitHubTrendingSource._measure_growth(snapshots, 3000, "2026-09-22") is None

    def test_measure_growth_returns_none_without_history(self):
        assert GitHubTrendingSource._measure_growth({}, 3000, "2026-09-22") is None

    def test_measure_growth_never_reports_negative(self):
        snapshots = {"2026-09-15": 5000}
        assert GitHubTrendingSource._measure_growth(snapshots, 4000, "2026-09-22") == 0

    def test_ledger_migrates_legacy_cache_format(self, tmp_path, monkeypatch):
        import json

        from src.config import settings
        from src.sources.github import TRENDING_CACHE_FILE

        monkeypatch.setattr(settings, "output_dir", str(tmp_path))
        legacy = {"2026-09-20": ["org/a"], "2026-09-21": ["org/a", "org/b"]}
        (tmp_path / TRENDING_CACHE_FILE).write_text(json.dumps(legacy))

        ledger = GitHubTrendingSource._load_ledger()

        assert ledger["version"] == 2
        assert ledger["seen"] == legacy
        # 首次上榜日期取最早出现的那天
        assert ledger["repos"]["org/a"]["first_seen"] == "2026-09-20"
        assert ledger["repos"]["org/b"]["first_seen"] == "2026-09-21"

    def test_ledger_drops_records_outside_retention_window(self, tmp_path, monkeypatch):
        import json

        from src.config import settings
        from src.sources.github import TRENDING_CACHE_FILE

        monkeypatch.setattr(settings, "output_dir", str(tmp_path))
        monkeypatch.setattr(settings, "github_trending_dedup_days", 30)
        ledger = {
            "version": 2,
            "seen": {"2020-01-01": ["org/ancient"], "2999-01-01": ["org/fresh"]},
            "repos": {
                "org/ancient": {"first_seen": "2020-01-01", "stars": {}},
                "org/fresh": {"first_seen": "2999-01-01", "stars": {}},
            },
        }
        GitHubTrendingSource._save_ledger(ledger)

        saved = json.loads((tmp_path / TRENDING_CACHE_FILE).read_text())
        assert "2020-01-01" not in saved["seen"]
        assert "org/ancient" not in saved["repos"]
        assert "org/fresh" in saved["repos"]

    def test_age_days_from_github_timestamp(self):
        from datetime import datetime, timezone

        now = datetime(2026, 9, 22, tzinfo=timezone.utc)
        assert GitHubTrendingSource._age_days("2026-09-12T00:00:00Z", now) == 10
        assert GitHubTrendingSource._age_days("", now) == 0
        assert GitHubTrendingSource._age_days("not-a-date", now) == 0



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
            "deepmind_blog",
            "huggingface_blog",
            "pytorch_blog",
            "devto_ai",
        ):
            assert name in AI_BLOG_FEEDS
        for name in (
            "aws_blog",
            "towards_data_science",
            "infoq_cn",
            "juejin",
            "bytebytego",
            "developers_digest",
            "kenashe",
            "anthropic",
            "ollama_blog",
        ):
            assert name not in AI_BLOG_FEEDS


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
