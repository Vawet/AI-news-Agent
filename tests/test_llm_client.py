"""Shared AI Gateway client configuration tests."""

from src.config import settings
from src.llm.client import build_chat_model


def test_gateway_configuration_takes_precedence(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "personal-key")
    monkeypatch.setattr(settings, "openai_base_url", "https://api.openai.com/v1")
    monkeypatch.setattr(settings, "openai_model", "gpt-test")
    monkeypatch.setattr(settings, "ai_gateway_token", "gateway-token")
    monkeypatch.setattr(
        settings,
        "ai_gateway_base_url",
        "https://gateway.example",
    )
    monkeypatch.setattr(settings, "ai_gateway_bizid", "hunter")
    monkeypatch.setattr(
        settings,
        "ai_gateway_ability_key",
        "gcp-claude-sonnet-4-6",
    )

    model = build_chat_model(max_tokens=1024)

    assert model.model_name == "gcp-claude-sonnet-4-6"
    assert str(model.openai_api_base).rstrip("/") == "https://gateway.example/v1"
    assert model.default_headers == {
        "X-Biz-ID": "hunter",
        "X-Ability-Key": "gcp-claude-sonnet-4-6",
    }
