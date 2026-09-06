"""HuggingFace Spaces 数据源适配器 - 公开 API 按热度采集"""

import logging
from datetime import datetime

import httpx

from src.models import RawItem, SourceType
from src.sources.base import BaseSource

logger = logging.getLogger(__name__)

USER_AGENT = "AI-News-Agent/1.0"
API_URL = "https://huggingface.co/api/spaces"


def parse_spaces_json(payload: object, since: datetime | None = None) -> list[RawItem]:
    """将 HF Spaces API JSON 转为 RawItem（便于单测，无需真实网络）。"""
    if not isinstance(payload, list):
        return []

    items: list[RawItem] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        space_id = str(entry.get("id") or "").strip()
        if not space_id:
            continue

        card = entry.get("cardData") if isinstance(entry.get("cardData"), dict) else {}
        title = (
            str(card.get("title") or "").strip()
            or str(entry.get("title") or "").strip()
            or space_id
        )
        author = str(entry.get("author") or "").strip()
        if not author and "/" in space_id:
            author = space_id.split("/", 1)[0]

        likes = int(entry.get("likes") or 0)
        trending = entry.get("trendingScore")
        try:
            trending_score = float(trending) if trending is not None else 0.0
        except (TypeError, ValueError):
            trending_score = 0.0
        sdk = str(entry.get("sdk") or "")
        summary = str(
            card.get("short_description")
            or card.get("description")
            or ""
        ).strip()

        published: datetime | None = None
        published_str = str(entry.get("lastModified") or entry.get("updatedAt") or "")
        if published_str:
            try:
                published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            except ValueError:
                published = None
        if since and published and published <= since:
            continue

        score = int(trending_score) if trending_score else likes
        url = f"https://huggingface.co/spaces/{space_id}"
        content = summary or title

        items.append(
            RawItem(
                source_type=SourceType.HUGGINGFACE_SPACES,
                source_id=space_id,
                title=title,
                content=content,
                url=url,
                author=author,
                published_at=published,
                score=score,
                metadata={
                    "likes": likes,
                    "trendingScore": trending_score,
                    "sdk": sdk,
                    "space_id": space_id,
                    "cardData": card,
                },
            )
        )

    items.sort(key=lambda x: x.score, reverse=True)
    return items


class HuggingFaceSpacesSource(BaseSource):
    """采集 HuggingFace 热门 Spaces（无需 token）。"""

    def __init__(self, limit: int = 30):
        self.limit = limit

    @property
    def source_id(self) -> str:
        return "huggingface_spaces"

    @property
    def default_interval(self) -> int:
        return 3600

    async def fetch(self, since: datetime | None = None) -> list[RawItem]:
        logger.info("Fetching HuggingFace Spaces (limit=%s) ...", self.limit)
        try:
            async with httpx.AsyncClient(
                timeout=30,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            ) as client:
                resp = await client.get(API_URL, params={"limit": self.limit})
                resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            logger.error("Fetch HuggingFace Spaces failed: %s", e)
            return []

        items = parse_spaces_json(payload, since=since)
        logger.info("HuggingFace Spaces: fetched %s items", len(items))
        return items
