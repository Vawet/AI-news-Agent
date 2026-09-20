"""Cloud pipeline artifact upload tests."""

from pathlib import Path

import pytest

from src.models import GeneratedArticle
from src.runtime.coordinator import TriggerRequest
from src.runtime.pipeline import CloudPipelineRunner


class FakeStorage:
    def __init__(self) -> None:
        self.uploaded: list[str] = []

    async def upload_file(self, path: Path) -> str:
        self.uploaded.append(path.name)
        return f"https://cdn.example/{path.name}"


TRIGGER = TriggerRequest(trigger_id="feishu:event-1", source="feishu", chat_id="oc_a")


@pytest.mark.asyncio
async def test_chinese_report_is_the_delivered_link(tmp_path):
    article = GeneratedArticle(
        title="AI 日报 — 2026-09-20",
        date="2026-09-20",
        description="English summary",
        description_zh="中文摘要",
        item_count=12,
    )
    english = tmp_path / "ai-daily-2026-09-20.md"
    chinese = tmp_path / "ai-daily-2026-09-20-zh.md"
    english.write_text("en", encoding="utf-8")
    chinese.write_text("zh", encoding="utf-8")

    storage = FakeStorage()
    runner = CloudPipelineRunner(
        storage,
        pipeline=lambda: _pipeline_result(article, [english, chinese]),
    )

    payload = await runner(TRIGGER)

    assert payload["url"] == "https://cdn.example/ai-daily-2026-09-20-zh.md"
    assert payload["summary"] == "中文摘要"
    assert payload["item_count"] == 12
    assert sorted(storage.uploaded) == [
        "ai-daily-2026-09-20-zh.md",
        "ai-daily-2026-09-20.md",
    ]


@pytest.mark.asyncio
async def test_no_article_uploads_nothing():
    storage = FakeStorage()
    runner = CloudPipelineRunner(storage, pipeline=lambda: _pipeline_result(None, []))

    payload = await runner(TRIGGER)

    assert payload["url"] == ""
    assert payload["item_count"] == 0
    assert storage.uploaded == []


async def _pipeline_result(article, paths) -> dict:
    return {
        "article": article,
        "artifact_paths": [str(path) for path in paths],
    }
