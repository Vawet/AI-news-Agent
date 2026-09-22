"""Long-running SAE service: health, schedule, and Feishu triggers."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request, Response

from src.config import settings
from src.integrations.feishu_bot import FeishuBot, FeishuMessage
from src.integrations.feishu_http import FeishuHTTPEventDispatcher
from src.runtime.coordinator import RunCoordinator, RunResult, TriggerRequest
from src.runtime.pipeline import CloudPipelineRunner
from src.runtime.scheduler import SCHEDULE_TIMEZONE, build_schedule_trigger
from src.storage.oss import OSSStorage

logger = logging.getLogger(__name__)


def _build_storage() -> OSSStorage:
    required = {
        "OSS_ENDPOINT": settings.oss_endpoint,
        "OSS_RESOURCE_BUCKET": settings.oss_resource_bucket,
        "OSS_ACCESS_KEY_ID": settings.oss_access_key_id,
        "OSS_ACCESS_KEY_SECRET": settings.oss_access_key_secret,
        "OSS_CUSTOM_DOMAIN": settings.oss_custom_domain,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"Missing cloud storage settings: {', '.join(missing)}")
    return OSSStorage(
        endpoint=settings.oss_endpoint,
        bucket_name=settings.oss_resource_bucket,
        access_key_id=settings.oss_access_key_id,
        access_key_secret=settings.oss_access_key_secret,
        prefix=settings.oss_prefix,
        public_base_url=(
            settings.oss_custom_domain
            if settings.oss_custom_domain.startswith(("http://", "https://"))
            else f"https://{settings.oss_custom_domain}"
        ),
    )


def _validate_runtime_settings() -> None:
    required = {
        "AI_GATEWAY_TOKEN": settings.ai_gateway_token,
        "AI_GATEWAY_BASE_URL": settings.ai_gateway_base_url,
        "FEISHU_APP_ID": settings.feishu_app_id,
        "FEISHU_APP_SECRET": settings.feishu_app_secret,
        "FEISHU_VERIFICATION_TOKEN": settings.feishu_verification_token,
        "FEISHU_ENCRYPT_KEY": settings.feishu_encrypt_key,
        "FEISHU_ALLOWED_CHAT_IDS": settings.feishu_allowed_chats,
        "FEISHU_TARGET_CHAT_ID": settings.feishu_target_chat_id,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"Missing cloud runtime settings: {', '.join(missing)}")


async def _send_terminal_message(
    bot: FeishuBot,
    chat_id: str,
    result: RunResult,
) -> None:
    if result.status == "completed":
        payload = result.payload
        count = payload.get("item_count", 0)
        summary = payload.get("summary") or "任务已完成。"
        await bot.send_result_card(
            chat_id,
            title=payload.get("title") or "AI News",
            summary=f"共整理 {count} 条资讯。\n\n{summary}",
            artifact_url=payload.get("url") or "",
        )
    elif result.status == "duplicate":
        await bot.send_text(chat_id, "这个请求已经处理过，不会重复执行。")
    elif result.status == "cooldown":
        minutes = max(1, result.retry_after_seconds // 60)
        await bot.send_text(chat_id, f"触发过于频繁，请约 {minutes} 分钟后再试。")
    elif result.status == "busy":
        await bot.send_text(chat_id, "已有一项资讯任务正在执行，请稍后再试。")
    else:
        await bot.send_text(chat_id, "资讯任务执行失败，已停止且不会自动重试。")


def create_app() -> FastAPI:
    state: dict = {
        "ready": False,
        "scheduler": None,
        "bot": None,
        "event_dispatcher": None,
    }

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        import asyncio

        _validate_runtime_settings()
        storage = _build_storage()
        coordinator = RunCoordinator(
            run_pipeline=CloudPipelineRunner(storage),
            claims=storage,
            cooldown_seconds=settings.feishu_trigger_cooldown_seconds,
        )
        event_loop = asyncio.get_running_loop()

        bot: FeishuBot

        async def handle_feishu(message: FeishuMessage) -> None:
            await bot.send_text(message.chat_id, "已开始整理 AI 资讯，完成后会发回本群。")
            result = await coordinator.run(
                TriggerRequest(
                    trigger_id=f"feishu:{message.event_id}",
                    source="feishu",
                    chat_id=message.chat_id,
                )
            )
            await _send_terminal_message(bot, message.chat_id, result)

        bot = FeishuBot(
            app_id=settings.feishu_app_id,
            app_secret=settings.feishu_app_secret,
            allowed_chat_ids=settings.feishu_allowed_chats,
            on_trigger=handle_feishu,
            event_loop=event_loop,
        )
        bot.initialize()
        event_dispatcher = FeishuHTTPEventDispatcher(
            encrypt_key=settings.feishu_encrypt_key,
            verification_token=settings.feishu_verification_token,
            message_handler=bot.handle_event,
        )

        async def run_scheduled() -> None:
            now = datetime.now(ZoneInfo(SCHEDULE_TIMEZONE))
            trigger = TriggerRequest(
                trigger_id=f"schedule:{now:%Y-%m-%d}",
                source="schedule",
                chat_id=settings.feishu_target_chat_id,
            )
            result = await coordinator.run(trigger)
            if settings.feishu_target_chat_id:
                await _send_terminal_message(
                    bot,
                    settings.feishu_target_chat_id,
                    result,
                )

        scheduler = AsyncIOScheduler(timezone=SCHEDULE_TIMEZONE)
        scheduler.add_job(
            run_scheduled,
            build_schedule_trigger(),
            id="wed_sun_ai_news",
            name="Wednesday and Sunday AI news",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )
        scheduler.start()
        state.update(
            {
                "ready": True,
                "scheduler": scheduler,
                "bot": bot,
                "event_dispatcher": event_dispatcher,
            }
        )
        logger.info("Cloud runtime ready; schedule=%s", build_schedule_trigger())
        try:
            yield
        finally:
            state["ready"] = False
            scheduler.shutdown(wait=False)

    app = FastAPI(title="AI News Agent", lifespan=lifespan)

    @app.post("/feishu/events")
    async def receive_feishu_event(request: Request) -> Response:
        dispatcher = state["event_dispatcher"]
        if dispatcher is None:
            return Response(
                content=b'{"msg":"service not ready"}',
                status_code=503,
                media_type="application/json",
            )
        result = dispatcher.dispatch(
            uri=request.url.path,
            headers=request.headers,
            body=await request.body(),
        )
        return Response(
            content=result.content,
            status_code=result.status_code,
            headers=result.headers,
        )

    @app.get("/health")
    async def health() -> dict:
        return {
            "ok": state["ready"],
            "schedule_timezone": SCHEDULE_TIMEZONE,
            "feishu_configured": bool(state["bot"] and state["bot"].configured),
        }

    return app
