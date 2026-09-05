"""Enrich selected items with full content, repo metadata, and community notes."""

import asyncio
import logging
import re

import httpx

from src.graph.state import PipelineState
from src.models import RawItem, SourceType
from src.tools.content import USER_AGENT, fetch_page_text, html_to_text

logger = logging.getLogger(__name__)

_HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{id}.json"
_GITHUB_REPO_URL = "https://api.github.com/repos/{full_name}"
_MAX_COMMENTS = 8
_MAX_COMMENT_CHARS = 400
_ENRICH_CONCURRENCY = 6


async def _hn_top_comments(client: httpx.AsyncClient, story_id: str) -> list[dict]:
    if not story_id.isdigit():
        return []
    try:
        story = (await client.get(_HN_ITEM_URL.format(id=story_id))).json() or {}
    except Exception:
        return []
    kids = (story.get("kids") or [])[:12]
    comments: list[dict] = []
    for kid in kids:
        try:
            node = (await client.get(_HN_ITEM_URL.format(id=kid))).json() or {}
        except Exception:
            continue
        if node.get("dead") or node.get("deleted") or not node.get("text"):
            continue
        comments.append(
            {
                "author": node.get("by", ""),
                "score": int(node.get("score") or 0),
                "text": html_to_text(node.get("text", ""))[:_MAX_COMMENT_CHARS],
            }
        )
        if len(comments) >= _MAX_COMMENTS:
            break
    return comments


def _community_summary(comments: list[dict], num_comments: int) -> str:
    if not comments:
        return f"{num_comments} comments; no high-signal comments retrieved."
    lines = [
        f"HN discussion: {num_comments} comments. Top-ranked excerpts (HN child order):"
    ]
    for comment in comments:
        prefix = f"+{comment['score']} " if comment["score"] else ""
        lines.append(f"{prefix}{comment['author']}: {comment['text']}")
    return "\n".join(lines)


async def _enrich_hackernews(client: httpx.AsyncClient, item: RawItem) -> None:
    meta = item.metadata
    article_url = meta.get("original_url") or item.url
    hn_id = str(item.source_id)
    article, comments = await asyncio.gather(
        fetch_page_text(client, article_url),
        _hn_top_comments(client, hn_id),
    )
    if article:
        item.content = article
        meta["official_summary"] = article[:1500]
        meta["full_content"] = article
    meta["top_comments"] = comments
    meta["community_summary"] = _community_summary(comments, int(meta.get("num_comments") or 0))


def _github_full_name(item: RawItem) -> str:
    match = re.search(r"github\.com/([^/]+/[^/]+)", item.url)
    if match:
        return match.group(1)
    if item.source_id.startswith("github:"):
        return item.source_id.split(":", 1)[1]
    return item.title


async def _enrich_github(client: httpx.AsyncClient, item: RawItem) -> None:
    full_name = _github_full_name(item)
    meta = item.metadata
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    try:
        repo = (await client.get(_GITHUB_REPO_URL.format(full_name=full_name), headers=headers)).json()
        if isinstance(repo, dict) and repo.get("full_name"):
            meta["stars"] = repo.get("stargazers_count", 0)
            meta["language"] = repo.get("language") or ""
            meta["repo_description"] = repo.get("description") or ""
            if not item.score:
                item.score = int(meta["stars"] or 0)
    except Exception as exc:
        logger.debug("GitHub repo lookup failed [%s]: %s", full_name, exc)
    readme = await fetch_page_text(client, item.url)
    if readme:
        item.content = readme
        meta["official_summary"] = (meta.get("repo_description") or "") + "\n" + readme[:1500]
        meta["full_content"] = readme


async def _enrich_huggingface(client: httpx.AsyncClient, item: RawItem) -> None:
    meta = item.metadata
    abstract = item.content
    meta["official_summary"] = abstract
    repo = meta.get("github_repo")
    if repo and "/" in str(repo):
        url = repo if str(repo).startswith("http") else f"https://github.com/{repo}"
        readme = await fetch_page_text(client, url)
        if readme:
            meta["code_readme_excerpt"] = readme[:2000]
            item.content = f"{abstract}\n\nCode README excerpt:\n{readme[:4000]}"


async def _enrich_one(client: httpx.AsyncClient, item: RawItem, semaphore: asyncio.Semaphore) -> None:
    async with semaphore:
        try:
            if item.source_type == SourceType.HACKERNEWS:
                await _enrich_hackernews(client, item)
            elif item.source_type == SourceType.GITHUB:
                await _enrich_github(client, item)
            elif item.source_type == SourceType.HUGGINGFACE:
                await _enrich_huggingface(client, item)
        except Exception as exc:
            logger.warning("Enrichment failed [%s]: %s", item.source_id, exc)


async def enricher_node(state: PipelineState) -> dict:
    """After quota selection, fetch article/README/comments for scoring."""
    items: list[RawItem] = state.get("raw_items", [])
    if not items:
        return {}

    semaphore = asyncio.Semaphore(_ENRICH_CONCURRENCY)
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        await asyncio.gather(*[_enrich_one(client, item, semaphore) for item in items])

    logger.info("Enrichment done for %s selected items", len(items))
    return {"raw_items": items}
