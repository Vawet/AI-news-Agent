"""Run the existing LangGraph pipeline and persist its generated artifacts."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from src.runtime.coordinator import TriggerRequest
from src.storage.oss import OSSStorage

PipelineEntry = Callable[[], Awaitable[dict[str, Any]]]


async def _run_default_pipeline() -> dict[str, Any]:
    from scripts.run_pipeline import main as run_pipeline

    return await run_pipeline()


class CloudPipelineRunner:
    def __init__(
        self,
        storage: OSSStorage,
        pipeline: PipelineEntry = _run_default_pipeline,
    ) -> None:
        self._storage = storage
        self._pipeline = pipeline

    async def __call__(self, trigger: TriggerRequest) -> dict[str, Any]:
        result = await self._pipeline()
        article = result.get("article")

        if article is None:
            return {
                "title": "AI News：本次没有生成报告",
                "summary": "有效资讯不足，已结束本次任务。",
                "url": "",
                "item_count": 0,
                "trigger_id": trigger.trigger_id,
                "artifacts": {},
            }

        urls: dict[str, str] = {}
        for value in result.get("artifact_paths", []):
            path = Path(value)
            if path.is_file():
                urls[path.name] = await self._storage.upload_file(path)

        # 中文版是群内交付首选，英文版只作为兜底链接。
        preferred_names = (
            f"ai-daily-{article.date}-zh.md",
            f"ai-daily-{article.date}.md",
        )
        return {
            "title": article.title,
            "summary": article.description_zh or article.description,
            "url": next((urls[name] for name in preferred_names if name in urls), ""),
            "item_count": article.item_count,
            "trigger_id": trigger.trigger_id,
            "artifacts": urls,
        }
