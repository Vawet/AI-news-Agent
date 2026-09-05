"""Profile-based LLM scoring and post-score selection."""

import asyncio
import json
import logging
import re
from difflib import SequenceMatcher

from langchain_openai import ChatOpenAI

from src.config import settings
from src.graph.state import PipelineState
from src.models import ExtractedItem
from src.scoring.profiles import ScoringProfile, get_profile, load_profiles

logger = logging.getLogger(__name__)

_ENGAGEMENT_KEYS = (
    "score", "points", "upvote_ratio", "num_comments", "comment_count",
    "comments", "likes", "retweets", "replies", "upvotes", "stars",
    "stars_today", "feed_rank", "language",
)

_CONTENT_LIMIT = 2500
_SUMMARY_LIMIT = 2000
_COMMUNITY_LIMIT = 1800


def _build_llm() -> ChatOpenAI:
    kwargs = {
        "model": settings.openai_model,
        "max_tokens": 16384,
        "temperature": 0,
        "model_kwargs": {"response_format": {"type": "json_object"}},
    }
    if settings.openai_api_key:
        kwargs["api_key"] = settings.openai_api_key
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    return ChatOpenAI(**kwargs)


def _item_payload(index: int, item: ExtractedItem) -> dict:
    metadata = item.metadata or {}
    engagement = {
        key: metadata[key]
        for key in _ENGAGEMENT_KEYS
        if key in metadata and metadata[key] not in (None, "")
    }
    engagement["platform_score"] = item.platform_score
    official_summary = str(
        metadata.get("official_summary") or item.summary or ""
    )[:_SUMMARY_LIMIT]
    community = str(metadata.get("community_summary") or "")[:_COMMUNITY_LIMIT]
    body = str(metadata.get("full_content") or item.content or "")
    return {
        "index": index,
        "title": item.title,
        "summary": item.summary,
        "official_summary": official_summary,
        "content_brief": body[:_CONTENT_LIMIT],
        "community": community,
        "source": item.source_type.value,
        "source_authority": item.source_type.value,
        "authors": metadata.get("authors") or item.author,
        "links": {
            "url": (metadata.get("original_url") or item.url),
            "arxiv_url": metadata.get("arxiv_url"),
            "github_repo": metadata.get("github_repo"),
            "project_page": metadata.get("project_page"),
            "hf_url": metadata.get("hf_url"),
            "hn_url": metadata.get("hn_url"),
        },
        "engagement_context": engagement,
    }


def _parse_json_object(raw: str) -> dict | None:
    """Strict JSON parsing; malformed model output must not pass scoring."""
    text = (raw or "").strip()
    if text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


async def _invoke_with_retry(llm: ChatOpenAI, prompt: str):
    """Retry API failures three times with exponential backoff."""
    attempts = settings.scoring_max_retries + 1
    for attempt in range(attempts):
        try:
            return await llm.ainvoke(prompt)
        except Exception:
            if attempt == attempts - 1:
                raise
            delay = 2 ** attempt
            logger.warning(
                "Scoring API call failed (attempt %s/%s), retrying in %ss",
                attempt + 1,
                attempts,
                delay,
            )
            await asyncio.sleep(delay)


async def _match_profiles(
    llm: ChatOpenAI,
    items: list[ExtractedItem],
    profiles: dict[str, ScoringProfile],
) -> list[str]:
    """Assign each item to one profile. First matching profile wins."""
    names = list(profiles)
    if len(names) == 1:
        return [names[0]] * len(items)

    assigned: list[str | None] = [None] * len(items)
    remaining = set(range(len(items)))
    payloads = [_item_payload(i, item) for i, item in enumerate(items)]

    for profile in profiles.values():
        if not remaining:
            break
        prompt = profile.match_prompt.format(
            profile_name=profile.name,
            profile_description=profile.description,
            items=json.dumps(
                [payloads[i] for i in sorted(remaining)],
                ensure_ascii=False,
            ),
        )
        try:
            response = await _invoke_with_retry(llm, prompt)
            parsed = _parse_json_object(response.content)
            indexes = parsed.get("indexes", []) if parsed else []
            for index in indexes:
                if isinstance(index, int) and index in remaining:
                    assigned[index] = profile.name
                    remaining.remove(index)
        except Exception as exc:
            logger.warning("Profile matching failed for %s: %s", profile.name, exc)

    fallback = "tech-news" if "tech-news" in profiles else names[0]
    return [name or fallback for name in assigned]


def _zero_score(item: ExtractedItem, profile_name: str, reason: str) -> None:
    item.ai_score = 0.0
    item.importance_score = 1.0
    item.ai_reason = reason
    item.scoring_profile = profile_name
    item.score_tags = []


async def _score_batch(
    llm: ChatOpenAI,
    indexed_items: list[tuple[int, ExtractedItem]],
    profile: ScoringProfile,
) -> None:
    payload = [_item_payload(index, item) for index, item in indexed_items]
    prompt = profile.analysis_prompt.format(
        categories=", ".join(profile.category_groups),
        items=json.dumps(payload, ensure_ascii=False),
    )

    try:
        response = await _invoke_with_retry(llm, prompt)
    except Exception as exc:
        logger.error("Scoring failed after retries [%s]: %s", profile.name, exc)
        for _, item in indexed_items:
            _zero_score(item, profile.name, "AI scoring call failed")
        return

    parsed = _parse_json_object(response.content)
    results = parsed.get("items") if parsed else None
    if not isinstance(results, list):
        logger.warning("Invalid scoring JSON for profile %s; dropping batch", profile.name)
        for _, item in indexed_items:
            _zero_score(item, profile.name, "Invalid AI scoring JSON")
        return

    by_index = {
        result.get("index"): result
        for result in results
        if isinstance(result, dict) and isinstance(result.get("index"), int)
    }
    for index, item in indexed_items:
        result = by_index.get(index)
        try:
            score = float(result["ai_score"])
            if not 0 <= score <= 10:
                raise ValueError("score out of range")
            reason = str(result["ai_reason"]).strip()
            summary = str(result["summary"]).strip()
            tags = result["tags"]
            if not reason or not summary or not isinstance(tags, list):
                raise ValueError("missing fixed scoring fields")
        except (KeyError, TypeError, ValueError):
            _zero_score(item, profile.name, "Invalid AI scoring item")
            continue

        item.ai_score = score
        item.importance_score = max(1.0, score)  # compatibility with existing consumers
        item.ai_reason = reason
        item.scoring_profile = profile.name
        item.score_tags = [str(tag) for tag in tags if str(tag).strip()]
        item.summary = summary


def _category_for(item: ExtractedItem, profile: ScoringProfile) -> str:
    for category in profile.category_groups:
        if category in item.score_tags:
            return category
    return "Other" if "Other" in profile.category_groups else next(iter(profile.category_groups))


def _topic_similarity(left: ExtractedItem, right: ExtractedItem) -> float:
    left_text = f"{left.title} {left.summary}".lower()
    right_text = f"{right.title} {right.summary}".lower()
    left_words = set(re.findall(r"[a-z0-9\u4e00-\u9fff]+", left_text))
    right_words = set(re.findall(r"[a-z0-9\u4e00-\u9fff]+", right_text))
    jaccard = len(left_words & right_words) / max(1, len(left_words | right_words))
    title_ratio = SequenceMatcher(None, left.title.lower(), right.title.lower()).ratio()
    return max(jaccard, title_ratio)


def _select_items(
    items: list[ExtractedItem],
    profiles: dict[str, ScoringProfile],
) -> list[ExtractedItem]:
    """Threshold, category caps, topic deduplication, then global max_items."""
    selected: list[ExtractedItem] = []
    category_counts: dict[tuple[str, str], int] = {}

    for item in sorted(items, key=lambda candidate: candidate.ai_score, reverse=True):
        profile = profiles[item.scoring_profile]
        if item.ai_score < profile.threshold:
            continue
        category = _category_for(item, profile)
        count_key = (profile.name, category)
        if category_counts.get(count_key, 0) >= profile.category_groups[category]:
            continue
        if sum(existing.scoring_profile == profile.name for existing in selected) >= profile.max_items:
            continue
        if any(
            item.url and item.url == existing.url
            or _topic_similarity(item, existing) >= 0.78
            for existing in selected
        ):
            continue
        category_counts[count_key] = category_counts.get(count_key, 0) + 1
        selected.append(item)

    return selected[: settings.scoring_max_items]


async def scorer_node(state: PipelineState) -> dict:
    """Score extracted items with profiles and keep only briefing candidates."""
    items = state.get("extracted_items", [])
    if not items:
        return {"extracted_items": []}

    profiles = load_profiles()
    configured_profile = settings.scoring_profile.strip()

    if not settings.openai_api_key:
        logger.warning("LLM not configured; preserving extraction scores without profile filtering")
        fallback = get_profile(
            "tech-news" if "tech-news" in profiles else next(iter(profiles)),
            profiles,
        )
        for item in items:
            item.ai_score = item.importance_score
            item.ai_reason = "Fallback score: LLM scoring is not configured"
            item.scoring_profile = fallback.name
            item.score_tags = ["Other"]
        return {"extracted_items": sorted(items, key=lambda item: item.ai_score, reverse=True)}

    llm = _build_llm()
    if configured_profile == "auto":
        assignments = await _match_profiles(llm, items, profiles)
    else:
        profile = get_profile(configured_profile, profiles)
        assignments = [profile.name] * len(items)

    grouped: dict[str, list[tuple[int, ExtractedItem]]] = {}
    for index, (item, profile_name) in enumerate(zip(items, assignments)):
        grouped.setdefault(profile_name, []).append((index, item))

    semaphore = asyncio.Semaphore(settings.scoring_max_concurrent)

    async def score_limited(
        batch: list[tuple[int, ExtractedItem]],
        profile: ScoringProfile,
    ) -> None:
        async with semaphore:
            await _score_batch(llm, batch, profile)

    tasks = []
    batch_size = max(1, settings.scoring_batch_size)
    for profile_name, indexed_items in grouped.items():
        profile = profiles[profile_name]
        for start in range(0, len(indexed_items), batch_size):
            tasks.append(score_limited(indexed_items[start:start + batch_size], profile))
    await asyncio.gather(*tasks)

    selected = _select_items(items, profiles)
    logger.info(
        "Profile scoring: %s candidates → %s selected (profile=%s)",
        len(items),
        len(selected),
        configured_profile,
    )
    return {"extracted_items": selected}
