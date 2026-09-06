"""Anthropic News 数据源适配器 - 无 RSS，解析 sitemap 或新闻列表页"""

import logging
import re
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

import httpx

from src.models import RawItem, SourceType
from src.sources.base import BaseSource

logger = logging.getLogger(__name__)

USER_AGENT = "AI-News-Agent/1.0"
SITEMAP_URL = "https://www.anthropic.com/sitemap.xml"
NEWS_LIST_URL = "https://www.anthropic.com/news"
NEWS_PATH_RE = re.compile(r"https?://(?:www\.)?anthropic\.com/news/([^/?#]+)", re.I)
HTML_HREF_RE = re.compile(
    r'href=["\'](?:https?://(?:www\.)?anthropic\.com)?/news/([^/"\'?#]+)["\']',
    re.I,
)


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _title_from_slug(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").strip() or slug


def _parse_lastmod(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(value[:19] if "T" in value else value[:10], fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_sitemap_news(xml_text: str) -> list[tuple[str, datetime | None, str]]:
    """从 sitemap XML 提取 /news/{slug} 条目，返回 (url, lastmod, title)。"""
    if not xml_text or not xml_text.strip():
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    found: dict[str, tuple[str, datetime | None, str]] = {}
    for node in root.iter():
        if _local_tag(node.tag) != "url":
            continue
        loc = ""
        lastmod: datetime | None = None
        for child in list(node):
            name = _local_tag(child.tag)
            text = (child.text or "").strip()
            if name == "loc":
                loc = text
            elif name == "lastmod":
                lastmod = _parse_lastmod(text)
        match = NEWS_PATH_RE.search(loc)
        if not match:
            continue
        slug = match.group(1)
        if slug.lower() in {"", "index"}:
            continue
        url = loc.split("?")[0].rstrip("/")
        title = _title_from_slug(slug)
        found[url] = (url, lastmod, title)

    return list(found.values())


def parse_news_list_html(html: str) -> list[tuple[str, datetime | None, str]]:
    """从新闻列表 HTML 提取 /news/{slug} 链接。"""
    if not html:
        return []
    found: dict[str, tuple[str, datetime | None, str]] = {}
    for slug in HTML_HREF_RE.findall(html):
        if slug.lower() in {"", "index"}:
            continue
        url = f"https://www.anthropic.com/news/{slug}"
        found[url] = (url, None, _title_from_slug(slug))
    return list(found.values())


def entries_to_items(
    entries: list[tuple[str, datetime | None, str]],
    since: datetime | None = None,
) -> list[RawItem]:
    items: list[RawItem] = []
    for url, published, title in entries:
        if since and published and published <= since:
            continue
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        items.append(
            RawItem(
                source_type=SourceType.ANTHROPIC,
                source_id=slug,
                title=title,
                content="",
                url=url,
                author="Anthropic",
                published_at=published,
                metadata={"feed_name": "anthropic_news"},
            )
        )
    items.sort(key=lambda x: x.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return items


class AnthropicNewsSource(BaseSource):
    """采集 Anthropic News：优先 sitemap，失败则解析列表页。正文交给 enricher。"""

    def __init__(self, max_results: int = 20):
        self.max_results = max_results

    @property
    def source_id(self) -> str:
        return "anthropic"

    @property
    def default_interval(self) -> int:
        return 3600

    async def fetch(self, since: datetime | None = None) -> list[RawItem]:
        logger.info("Fetching Anthropic News ...")
        try:
            async with httpx.AsyncClient(
                timeout=30,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            ) as client:
                entries = await self._fetch_entries(client)
        except Exception as e:
            logger.error("Fetch Anthropic News failed: %s", e)
            return []

        items = entries_to_items(entries, since=since)
        if self.max_results > 0:
            items = items[: self.max_results]
        logger.info("Anthropic News: fetched %s items", len(items))
        return items

    async def _fetch_entries(self, client: httpx.AsyncClient) -> list[tuple[str, datetime | None, str]]:
        try:
            resp = await client.get(SITEMAP_URL)
            resp.raise_for_status()
            entries = parse_sitemap_news(resp.text)
            if entries:
                return entries
            logger.warning("Anthropic sitemap had no /news/ URLs, falling back to list page")
        except Exception as e:
            logger.warning("Anthropic sitemap failed (%s), falling back to list page", e)

        resp = await client.get(NEWS_LIST_URL)
        resp.raise_for_status()
        return parse_news_list_html(resp.text)
