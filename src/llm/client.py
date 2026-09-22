"""Build LLM clients consistently for OpenAI-compatible providers and AI Gateway."""

from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI

from src.config import settings


def build_chat_model(**overrides: Any) -> ChatOpenAI:
    """Create a ChatOpenAI client without exposing provider credentials."""
    using_gateway = bool(settings.ai_gateway_token)
    api_key = settings.ai_gateway_token or settings.openai_api_key
    base_url = settings.llm_base_url
    model = (
        settings.ai_gateway_ability_key
        if using_gateway
        else settings.openai_model
    )

    kwargs: dict[str, Any] = {
        "model": model,
        **overrides,
    }
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url.rstrip("/")
    if using_gateway:
        kwargs["default_headers"] = {
            "X-Biz-ID": settings.ai_gateway_bizid,
            "X-Ability-Key": settings.ai_gateway_ability_key,
        }
    return ChatOpenAI(**kwargs)
