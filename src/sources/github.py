"""GitHub Trending 数据源适配器 - RSS 采集 + LLM AI 过滤 + 上榜台账去重

Trending RSS 只给仓库描述和排名，既没有日期也没有 star 数，所以"是不是最近的、
涨得快不快"必须由本模块自己建立：台账记录每个仓库首次上榜日期与历次 star 快照，
再配合 GitHub API 的 created_at / stargazers_count 算出相对增速。
"""

import json
import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser
import httpx

from src.config import settings
from src.models import RawItem, SourceType
from src.sources.base import BaseSource
from src.tools.ai_filter import batch_filter_ai
from src.tools.content import html_to_text

logger = logging.getLogger(__name__)

USER_AGENT = "AI-News-Agent/1.0 (RSS Reader)"

# 上榜台账文件路径
TRENDING_CACHE_FILE = ".github_trending_cache.json"

# GitHub Trending RSS (社区维护，按语言/周期分类)
TRENDING_RSS_BASE = "https://mshibanami.github.io/GitHubTrendingRSS"

GITHUB_API_BASE = "https://api.github.com/repos"

# 超过这个年龄的仓库算"成名已久"，不能当本期必读；它们上榜是存量热度而非新事件。
ESTABLISHED_AGE_DAYS = 180


class GitHubTrendingSource(BaseSource):
    """通过 RSS 采集 GitHub Trending AI 项目

    功能：
    1. 从社区维护的 GitHub Trending RSS 源获取热门仓库
    2. LLM 批量标题+描述分类：自动判断项目是否 AI 相关
    3. 上榜台账去重：近 N 天出现过的仓库不再重复推荐
    4. 相对增速排序：新兴项目优先于常年霸榜的巨无霸
    """

    def __init__(self, language: str = "", since_period: str = "daily"):
        self.language = language
        self.since_period = since_period
        # RSS URL: /daily/all.xml 或 /daily/python.xml
        lang_path = language.lower() if language else "all"
        self.rss_url = f"{TRENDING_RSS_BASE}/{since_period}/{lang_path}.xml"

    @property
    def source_id(self) -> str:
        return "github_trending"

    @property
    def default_interval(self) -> int:
        return 14400  # 4 hours

    @staticmethod
    def _load_ledger() -> dict:
        """加载上榜台账，并把旧版 {date: [repo]} 格式迁移过来。"""
        empty: dict = {"version": 2, "seen": {}, "repos": {}}
        cache_path = Path(settings.output_dir) / TRENDING_CACHE_FILE
        if not cache_path.exists():
            return empty
        try:
            data = json.loads(cache_path.read_text())
        except (json.JSONDecodeError, OSError):
            return empty
        if not isinstance(data, dict):
            return empty
        if data.get("version") == 2:
            data.setdefault("seen", {})
            data.setdefault("repos", {})
            return data

        # 旧格式：顶层就是 {date: [repo, ...]}
        seen = {k: v for k, v in data.items() if isinstance(v, list)}
        repos: dict = {}
        for date_str in sorted(seen):
            for name in seen[date_str]:
                repos.setdefault(name, {"first_seen": date_str, "stars": {}})
        return {"version": 2, "seen": seen, "repos": repos}

    @staticmethod
    def _save_ledger(ledger: dict):
        """保存台账，丢弃超出保留窗口的记录。"""
        cache_path = Path(settings.output_dir) / TRENDING_CACHE_FILE
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        cutoff = (
            datetime.now(tz=timezone.utc)
            - timedelta(days=settings.github_trending_dedup_days)
        ).strftime("%Y-%m-%d")
        seen = {k: v for k, v in ledger.get("seen", {}).items() if k >= cutoff}
        live = {name for names in seen.values() for name in names}
        repos = {k: v for k, v in ledger.get("repos", {}).items() if k in live}

        cache_path.write_text(
            json.dumps(
                {"version": 2, "seen": seen, "repos": repos},
                ensure_ascii=False,
                indent=2,
            )
        )

    @staticmethod
    def _extract_full_name(link: str) -> str:
        """从 GitHub URL 提取 owner/repo"""
        match = re.search(r"github\.com/([^/]+/[^/]+)", link)
        return match.group(1) if match else ""

    @staticmethod
    async def _fetch_repo_stats(full_names: list[str]) -> dict[str, dict]:
        """取仓库的 star 数与创建时间；失败的仓库直接缺席，不阻断采集。"""
        stats: dict[str, dict] = {}
        if not full_names:
            return stats
        async with httpx.AsyncClient(
            timeout=20,
            headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
            follow_redirects=True,
        ) as client:
            for name in full_names:
                try:
                    resp = await client.get(f"{GITHUB_API_BASE}/{name}")
                    resp.raise_for_status()
                    data = resp.json()
                except (httpx.HTTPError, ValueError) as exc:
                    logger.warning("GitHub API lookup failed for %s: %s", name, exc)
                    continue
                stats[name] = {
                    "stars": int(data.get("stargazers_count") or 0),
                    "created_at": str(data.get("created_at") or ""),
                    "pushed_at": str(data.get("pushed_at") or ""),
                }
        return stats

    @staticmethod
    def _age_days(created_at: str, now: datetime) -> int:
        if not created_at:
            return 0
        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            return 0
        return max(0, (now - created).days)

    @staticmethod
    def _measure_growth(snapshots: dict, stars: int, today: str) -> int | None:
        """对比更早日期的快照得到真实涨幅；无更早快照返回 None 表示未知。

        基线必须来自比 today 更早的日期：同一天重跑时刚写入的快照只差几分钟，
        拿它当基线会得到纯噪声的"涨幅"并污染排序。
        """
        prior = [date for date in snapshots if date < today]
        if stars <= 0 or not prior:
            return None
        return max(0, stars - int(snapshots[min(prior)]))

    @staticmethod
    def _relative_velocity(stars: int, gained: int | None) -> float:
        """相对增速：本期涨幅占存量的比例，越高说明越处在爆发期。

        Trending 榜按绝对涨星排序，巨无霸天然靠前。用比例可以让 1k→3k 的新项目
        压过 147k→148k 的常驻项目。

        首次上榜时台账里没有基线快照，此时**无从得知**增速，返回 0 表示未知，
        交给 feed_rank 兜底——不要用 stars/age 之类的生命周期均值假装有数据，
        那个式子代进来 stars 会被约掉，退化成纯粹的"年龄倒数"。
        """
        if stars <= 0 or gained is None:
            return 0.0
        return gained / stars

    @classmethod
    def _select_trending(cls, items: list[RawItem], max_items: int) -> list[RawItem]:
        """新兴项目优先，其次看实测增速，最后用 Trending 榜排名兜底。

        feed_rank 本身就是 GitHub 按本周涨星排出来的，所以在没有实测增速时它是
        最可靠的增长信号。
        """
        def sort_key(item: RawItem) -> tuple:
            meta = item.metadata or {}
            return (
                bool(meta.get("is_established")),  # 年轻项目排前面
                -float(meta.get("relative_velocity") or 0.0),
                int(meta.get("feed_rank") or 999),
            )

        return sorted(items, key=sort_key)[: max(0, max_items)]

    async def fetch(self, since: datetime | None = None) -> list[RawItem]:
        logger.info(f"Fetching GitHub Trending (RSS: {self.rss_url}) ...")

        try:
            async with httpx.AsyncClient(
                timeout=30,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            ) as client:
                resp = await client.get(self.rss_url)
                resp.raise_for_status()
            feed = feedparser.parse(resp.text)
        except Exception as e:
            logger.error(f"Fetch GitHub Trending RSS failed: {e}")
            return []

        entries = feed.entries[:50]
        if not entries:
            logger.info("GitHub Trending: no RSS entries")
            return []

        # 构建候选列表；RSS 顺序即当日 Trending 排名
        candidates: list[dict] = []
        for rank, entry in enumerate(entries, start=1):
            link = entry.get("link", "")
            full_name = self._extract_full_name(link)
            if not full_name:
                continue
            title = entry.get("title", full_name)
            raw_desc = entry.get("summary", "") or ""
            desc = html_to_text(raw_desc)
            candidates.append({
                "full_name": full_name,
                "title": title,
                "description": desc,
                "link": link,
                "rank": rank,
            })

        if not candidates:
            logger.info("GitHub Trending: no valid repo entries")
            return []

        # LLM 批量判断项目是否 AI 相关
        titles = [c["full_name"] for c in candidates]
        descs = [c["description"][:80] for c in candidates]
        ai_indices = set(await batch_filter_ai(titles, descs))

        ledger = self._load_ledger()
        repos_ledger: dict = ledger.setdefault("repos", {})
        now = datetime.now(tz=timezone.utc)
        today = now.strftime("%Y-%m-%d")
        today_ai_repos: list[str] = []

        skip_dedup = settings.github_trending_skip_dedup
        historical_repos: set[str] = set()
        if not skip_dedup:
            for date_str, repo_list in ledger.get("seen", {}).items():
                if date_str != today:
                    historical_repos.update(repo_list)

        fresh: list[dict] = []
        deduped_count = 0
        for idx, c in enumerate(candidates):
            if idx not in ai_indices:
                continue
            today_ai_repos.append(c["full_name"])
            if c["full_name"] in historical_repos:
                deduped_count += 1
                continue
            fresh.append(c)

        # 只给去重后的存活项目查 API，控制匿名额度消耗（60 次/小时）
        stats = await self._fetch_repo_stats([c["full_name"] for c in fresh])

        items: list[RawItem] = []
        for c in fresh:
            full_name = c["full_name"]
            rank = c["rank"]
            record = repos_ledger.setdefault(
                full_name, {"first_seen": today, "stars": {}}
            )
            first_seen = str(record.get("first_seen") or today)
            snapshots: dict = record.setdefault("stars", {})

            stat = stats.get(full_name, {})
            stars = int(stat.get("stars") or 0)
            age_days = self._age_days(stat.get("created_at", ""), now)

            gained = self._measure_growth(snapshots, stars, today)
            if stars:
                snapshots[today] = stars

            velocity = self._relative_velocity(stars, gained)
            established = age_days > ESTABLISHED_AGE_DAYS

            item = RawItem(
                source_type=SourceType.GITHUB,
                source_id=f"github:{full_name}",
                title=full_name,
                content=c["description"],
                url=c["link"],
                author=full_name.split("/")[0],
                # 榜单条目没有发布时间，用首次上榜日期代替，避免伪造成"此刻"
                published_at=datetime.fromisoformat(f"{first_seen}T00:00:00+00:00"),
                score=max(1, 80 - rank),
                metadata={
                    "original_url": c["link"],
                    "feed_rank": rank,
                    "repo_description": c["description"][:500],
                    "stars": stars,
                    "stars_gained": gained,
                    "repo_age_days": age_days,
                    "relative_velocity": round(velocity, 6),
                    "first_seen": first_seen,
                    "is_established": established,
                },
            )
            items.append(item)

        items = self._select_trending(items, settings.github_trending_max_items)

        ledger.setdefault("seen", {})[today] = today_ai_repos
        self._save_ledger(ledger)

        dedup_note = (
            "cross-day dedup: skipped"
            if skip_dedup
            else f"cross-day dedup: {deduped_count} repeated"
        )
        logger.info(
            f"GitHub Trending: {len(items)} AI projects "
            f"(LLM filtered {len(candidates)} → {len(ai_indices)} AI, "
            f"{dedup_note}, "
            f"capped at {settings.github_trending_max_items})"
        )
        for item in items:
            meta = item.metadata or {}
            logger.info(
                "  %s: %s stars, age %sd, rel-velocity %.4f%s",
                item.title,
                meta.get("stars"),
                meta.get("repo_age_days"),
                meta.get("relative_velocity") or 0.0,
                " [established]" if meta.get("is_established") else "",
            )
        return items
