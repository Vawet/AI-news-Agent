"""Reddit 数据源适配器 - 通过 RSS feed 采集热门 AI 内容"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx

from src.models import RawItem, SourceType
from src.sources.base import BaseSource
from src.tools.ai_filter import batch_filter_ai

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)

# Reddit 按 IP 限流，多个子版块必须串行请求并留出间隔，否则整批返回 429
_REDDIT_GATE = asyncio.Semaphore(1)
_REQUEST_SPACING_SECONDS = 6.0
_MAX_ATTEMPTS = 4


def _strip_html(text: str) -> str:
    """移除 HTML 标签，保留纯文本"""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#\d+;", "", text)
    text = re.sub(r"&\w+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_comments_count(summary: str) -> int:
    """从 RSS summary 中提取评论数"""
    m = re.search(r"(\d+)\s+comments?", summary)
    return int(m.group(1)) if m else 0


def _extract_external_url(summary_html: str) -> str:
    """从 RSS summary 中取出指向站外的原文链接（自帖没有外链则为空）"""
    for href in re.findall(r'href="([^"]+)"', summary_html):
        url = href.replace("&amp;", "&")
        if url.startswith("http") and "reddit.com" not in url and "redd.it" not in url:
            return url
    return ""


class RedditRSSSource(BaseSource):
    """通过 Reddit RSS feed 采集子版块热门内容

    两级过滤：
    1. 时间过滤：只保留 since 之后的帖子
    2. LLM 批量标题分类：精准判断是否 AI 相关
    """

    def __init__(self, subreddit: str, min_score: int = 50, limit: int = 50):
        self.subreddit = subreddit
        self.min_score = min_score
        self.url = f"https://www.reddit.com/r/{subreddit}/hot.rss?limit={limit}"

    @property
    def source_id(self) -> str:
        return f"reddit:{self.subreddit}"

    async def _get_feed_text(self) -> str | None:
        """串行拉取 RSS，遇到 429 时按退避重试"""
        async with _REDDIT_GATE:
            async with httpx.AsyncClient(
                timeout=30,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            ) as client:
                for attempt in range(_MAX_ATTEMPTS):
                    resp = await client.get(self.url)
                    if resp.status_code != 429:
                        resp.raise_for_status()
                        await asyncio.sleep(_REQUEST_SPACING_SECONDS)
                        return resp.text

                    if attempt == _MAX_ATTEMPTS - 1:
                        break
                    delay = float(
                        resp.headers.get("retry-after")
                        or _REQUEST_SPACING_SECONDS * 2 ** (attempt + 1)
                    )
                    logger.info(
                        f"r/{self.subreddit}: rate limited, retrying in {delay:.0f}s "
                        f"({attempt + 1}/{_MAX_ATTEMPTS - 1})"
                    )
                    await asyncio.sleep(delay)

            logger.error(f"Fetch r/{self.subreddit} RSS failed: rate limited by Reddit")
            return None

    async def fetch(self, since: datetime | None = None) -> list[RawItem]:
        logger.info(f"Fetching Reddit r/{self.subreddit} (RSS hot) ...")
        try:
            feed_text = await self._get_feed_text()
        except Exception as e:
            logger.error(f"Fetch r/{self.subreddit} RSS failed: {e}")
            return []

        if feed_text is None:
            return []
        feed = feedparser.parse(feed_text)

        entries = feed.get("entries", [])
        if not entries:
            logger.info(f"r/{self.subreddit}: no entries in RSS")
            return []

        # 第一级过滤：时间
        candidates = []
        for entry in entries:
            # 解析发布时间
            published = None
            if entry.get("published"):
                try:
                    published = parsedate_to_datetime(entry["published"])
                    if published.tzinfo is None:
                        published = published.replace(tzinfo=timezone.utc)
                except Exception:
                    pass
            if since and published and published <= since:
                continue

            title = entry.get("title", "")
            link = entry.get("link", "")
            summary_html = entry.get("summary", "")
            content_text = _strip_html(summary_html)
            comments = _extract_comments_count(summary_html)
            author = entry.get("author", entry.get("author_detail", {}).get("name", ""))
            # 清理 author 前缀 /u/
            if author.startswith("/u/"):
                author = author[3:]

            # 从 link 中提取 post id
            post_id = ""
            id_match = re.search(r"/comments/(\w+)/", link)
            if id_match:
                post_id = id_match.group(1)

            candidates.append({
                "title": title,
                "content": content_text,
                "link": link,
                "external_url": _extract_external_url(summary_html),
                "author": author,
                "published": published,
                "comments": comments,
                "post_id": post_id,
            })

        if not candidates:
            logger.info(f"r/{self.subreddit}: no items after time filter")
            return []

        # 第二级过滤：LLM 判断是否 AI 相关
        titles = [c["title"] for c in candidates]
        descs = [c["content"][:80] for c in candidates]
        ai_indices = set(await batch_filter_ai(titles, descs))

        items: list[RawItem] = []
        for idx, c in enumerate(candidates):
            if idx not in ai_indices:
                continue
            # RSS 没有 upvote 数据，用评论数 * 10 作为粗略 score
            score = c["comments"] * 10 if c["comments"] > 0 else 1
            item = RawItem(
                source_type=SourceType.REDDIT,
                source_id=c["post_id"] or c["link"],
                title=c["title"],
                content=c["content"] or c["title"],
                url=c["link"],
                author=c["author"],
                published_at=c["published"],
                score=score,
                metadata={
                    "subreddit": self.subreddit,
                    "reddit_url": c["link"],
                    "original_url": c["external_url"] or c["link"],
                    "num_comments": c["comments"],
                },
            )
            items.append(item)

        logger.info(
            f"r/{self.subreddit}: {len(items)} AI items "
            f"(RSS, LLM filtered {len(candidates)} → {len(items)})"
        )
        return items
