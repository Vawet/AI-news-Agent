"""Pipeline 入口脚本 - 运行一次完整的新闻采集→清洗→提取→撰稿流程"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# 确保 src 可被 import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import settings
from src.graph.workflow import compile_graph
from src.reporting import twice_weekly_window


def _default_sources() -> list[str]:
    """根据配置动态决定启用哪些数据源"""
    sources = [
        "hackernews",
        "github",
        "huggingface",
        "huggingface_spaces",
        "arxiv",
        "rss",
        "anthropic",
    ]
    if settings.enable_reddit:
        sources.insert(0, "reddit")
    # Twitter / Product Hunt 成本高，默认不启用；需要时命令行传入 twitter / producthunt
    return sources


def setup_logging():
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # 降低第三方库日志
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


async def main(
    sources: list[str] | None = None,
    report_mode: str | None = None,
    window_start: str = "",
    window_end: str = "",
):
    setup_logging()
    logger = logging.getLogger("pipeline")

    logger.info("=" * 60)
    logger.info("AI News Agent Pipeline - v0.1")
    logger.info("=" * 60)

    graph = compile_graph()
    mode = report_mode or settings.report_mode
    if mode == "weekly" and not window_start:
        window = twice_weekly_window()
        window_start = window.start.isoformat()
        window_end = window.end.isoformat()

    # 初始状态
    initial_state = {
        "raw_items": [],
        "cleaned_items": [],
        "deduped_items": [],
        "extracted_items": [],
        "article": None,
        "run_id": "",
        "run_started_at": "",
        "sources_config": sources or _default_sources(),
        "report_mode": mode,
        "window_start": window_start,
        "window_end": window_end,
        "errors": [],
        "messages": [],
    }

    # 运行 pipeline
    result = await graph.ainvoke(initial_state)

    # 输出结果
    article = result.get("article")
    if article:
        logger.info(f"✅ Article generated: {article.title}")
        logger.info(f"   Contains {article.item_count} news items")
        logger.info(f"   Output dir: {settings.output_path}")
    else:
        extracted = result.get("extracted_items", [])
        logger.info(f"⏸️  No article generated (only {len(extracted)} items)")

    errors = result.get("errors", [])
    if errors:
        logger.warning(f"⚠️  {len(errors)} errors during run:")
        for err in errors:
            logger.warning(f"   - {err}")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the AI news pipeline")
    parser.add_argument("sources", nargs="*", help="Data source IDs (empty = defaults)")
    parser.add_argument("--report-mode", choices=["daily", "weekly"], default=None)
    parser.add_argument("--window-start", default="", help="ISO 8601 exclusive lower bound")
    parser.add_argument("--window-end", default="", help="ISO 8601 inclusive upper bound")
    args = parser.parse_args()
    asyncio.run(
        main(
            sources=args.sources or None,
            report_mode=args.report_mode,
            window_start=args.window_start,
            window_end=args.window_end,
        )
    )
