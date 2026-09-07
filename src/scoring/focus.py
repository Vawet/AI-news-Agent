"""Editorial focus for filtering, cleaning, and scoring.

Audience: people building production / business AI agents.

Keep:
1. Model capabilities as a product (what you can call, how well it tools/codes)
2. Harness methodology
3. GitHub Trending AI OSS (hard cap of 2)
4. Official frontier-lab cognition useful to agent builders

Drop deep pre-training / post-training / architecture research.
"""

from __future__ import annotations

import re
from typing import Any

OFFICIAL_FEEDS = frozenset({"openai_blog", "deepmind_blog"})

OFFICIAL_SOURCE_TYPES = frozenset({"anthropic"})

OFFICIAL_HOST_MARKERS = (
    "openai.com",
    "anthropic.com",
    "deepmind.google",
    "ai.google.dev",
    "research.google",
    "ai.meta.com",
    "ai.facebook.com",
    "llama.meta.com",
    "x.ai",
    "mistral.ai",
    "huggingface.co/blog",
)

CAPABILITY_TERMS = (
    "model", "llm", "gpt", "claude", "gemini", "llama", "qwen", "deepseek",
    "mistral", "benchmark", "eval", "capability", "reasoning",
    "multimodal", "context window", "tool calling", "function calling",
    "computer use", "coding agent", "api",
)

HARNESS_TERMS = (
    "harness", "agent", "tool use", "tool-use", "scaffolding", "orchestration",
    "eval harness", "swe-bench", "terminal-bench", "coding agent",
    "computer use", "environment", "trajectory", "mcp", "skills",
)

# Deep training research that business agent builders do not need.
# Short acronyms are matched as words to avoid "opportunity" ~ ppo.
_TRAINING_TITLE_RE = re.compile(
    r"pre-?train|post-?train|posttraining|rlhf|\bgrpo\b|\bdpo\b|\bkto\b|\brlvr\b|"
    r"scaling law|moe training|continued pretraining|mid-training|"
    r"from[- ]scratch|training recipe|training loss|\boptimizer\b|"
    r"gradient descent|distillation recipe|sft recipe|"
    r"token corpus|trillion tokens",
    re.I,
)

GITHUB_TRENDING_MAX_ITEMS = 2


def _text_blob(item: Any) -> str:
    meta = getattr(item, "metadata", None) or {}
    parts = [
        getattr(item, "title", "") or "",
        getattr(item, "content", "") or "",
        getattr(item, "url", "") or "",
        str(meta.get("feed_name") or ""),
        str(meta.get("repo_description") or ""),
        str(meta.get("official_summary") or ""),
    ]
    return " ".join(parts).lower()


def is_official_source(item: Any) -> bool:
    source_type = getattr(item, "source_type", None)
    source_value = source_type.value if hasattr(source_type, "value") else str(source_type or "")
    if source_value in OFFICIAL_SOURCE_TYPES:
        return True
    meta = getattr(item, "metadata", None) or {}
    if str(meta.get("feed_name") or "") in OFFICIAL_FEEDS:
        return True
    url = (getattr(item, "url", "") or "") + " " + str(meta.get("original_url") or "")
    url = url.lower()
    return any(marker in url for marker in OFFICIAL_HOST_MARKERS)


def is_training_research(item: Any) -> bool:
    """True for pretrain/post-train/RL internals that agent builders can skip.

    Title matches are enough. Body matches only count on paper-like sources so a
    model-release post that mentions token counts in passing is not dropped.
    """
    title = (getattr(item, "title", "") or "").lower()
    if _TRAINING_TITLE_RE.search(title):
        return True
    source_type = getattr(item, "source_type", None)
    source_value = source_type.value if hasattr(source_type, "value") else str(source_type or "")
    if source_value in {"arxiv", "huggingface"}:
        blob = _text_blob(item)
        return bool(_TRAINING_TITLE_RE.search(blob))
    return False


def focus_hints(item: Any) -> list[str]:
    hints: list[str] = []
    if is_training_research(item):
        return hints
    if is_official_source(item):
        hints.append("AI Insights")
    blob = _text_blob(item)
    if any(term in blob for term in HARNESS_TERMS):
        hints.append("Harness Methodology")
    if any(term in blob for term in CAPABILITY_TERMS):
        hints.append("Model Capabilities")
    source_type = getattr(item, "source_type", None)
    source_value = source_type.value if hasattr(source_type, "value") else str(source_type or "")
    if source_value == "github":
        hints.append("Open Source")
    return hints


def annotate_focus(metadata: dict, item: Any) -> dict:
    tagged = dict(metadata or {})
    tagged["is_official"] = is_official_source(item)
    tagged["is_training_research"] = is_training_research(item)
    tagged["focus_hints"] = focus_hints(item)
    return tagged
