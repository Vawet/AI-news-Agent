"""Feishu group mention handling through the official long-connection SDK."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeishuMessage:
    event_id: str
    chat_id: str
    chat_type: str
    message_type: str
    text: str
    mentions: tuple[str, ...]


def should_trigger(message: FeishuMessage, allowed_chat_ids: set[str]) -> bool:
    """Accept explicit group mentions from configured chats only."""
    return (
        message.chat_type == "group"
        and message.message_type == "text"
        and bool(message.mentions)
        and message.chat_id in allowed_chat_ids
        and bool(message.event_id)
    )


def _event_to_message(event_data) -> FeishuMessage:
    event = event_data.event
    message = event.message
    header = event_data.header
    text = ""
    try:
        text = json.loads(message.content or "{}").get("text", "")
    except (TypeError, json.JSONDecodeError):
        logger.warning("Ignoring malformed Feishu text payload")

    mention_names = tuple(
        mention.name or mention.key or ""
        for mention in (message.mentions or [])
    )
    return FeishuMessage(
        event_id=header.event_id or message.message_id or "",
        chat_id=message.chat_id or "",
        chat_type=message.chat_type or "",
        message_type=message.message_type or "",
        text=text,
        mentions=mention_names,
    )


class FeishuBot:
    """Receive @mentions and send acknowledgements/results to the same group."""

    def __init__(
        self,
        *,
        app_id: str,
        app_secret: str,
        allowed_chat_ids: set[str],
        on_trigger: Callable[[FeishuMessage], Awaitable[None]],
        event_loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._allowed_chat_ids = allowed_chat_ids
        self._on_trigger = on_trigger
        self._event_loop = event_loop
        self._thread: threading.Thread | None = None
        self._api_client = None

    @property
    def configured(self) -> bool:
        return bool(
            self._app_id
            and self._app_secret
            and self._allowed_chat_ids
        )

    def start(self) -> None:
        if not self.configured:
            logger.warning("Feishu bot is disabled: missing app credentials or chat allowlist")
            return
        if self._thread and self._thread.is_alive():
            return

        import lark_oapi as lark
        from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

        self._api_client = (
            lark.Client.builder()
            .app_id(self._app_id)
            .app_secret(self._app_secret)
            .build()
        )

        def handle_message(data: P2ImMessageReceiveV1) -> None:
            message = _event_to_message(data)
            if not should_trigger(message, self._allowed_chat_ids):
                return
            future = asyncio.run_coroutine_threadsafe(
                self._on_trigger(message),
                self._event_loop,
            )
            future.add_done_callback(self._log_handler_error)

        dispatcher = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(handle_message)
            .build()
        )
        ws_client = lark.ws.Client(
            self._app_id,
            self._app_secret,
            event_handler=dispatcher,
            log_level=lark.LogLevel.INFO,
        )
        self._thread = threading.Thread(
            target=ws_client.start,
            name="feishu-long-connection",
            daemon=True,
        )
        self._thread.start()
        logger.info("Feishu long connection started")

    @staticmethod
    def _log_handler_error(future) -> None:
        try:
            future.result()
        except Exception:
            logger.exception("Feishu trigger handler failed")

    async def send_text(self, chat_id: str, text: str) -> None:
        await asyncio.to_thread(self._send_message, chat_id, "text", {"text": text})

    async def send_result_card(
        self,
        chat_id: str,
        *,
        title: str,
        summary: str,
        artifact_url: str,
    ) -> None:
        elements: list[dict] = [
            {
                "tag": "markdown",
                "content": summary[:20_000],
            }
        ]
        if artifact_url:
            elements.append(
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "查看完整报告"},
                            "type": "primary",
                            "url": artifact_url,
                        }
                    ],
                }
            )
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": title[:100]},
            },
            "elements": elements,
        }
        await asyncio.to_thread(
            self._send_message,
            chat_id,
            "interactive",
            card,
        )

    def _send_message(self, chat_id: str, message_type: str, content: dict) -> None:
        if self._api_client is None:
            raise RuntimeError("Feishu API client is not started")

        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type(message_type)
                .content(json.dumps(content, ensure_ascii=False))
                .build()
            )
            .build()
        )
        response = self._api_client.im.v1.message.create(request)
        if not response.success():
            raise RuntimeError(
                f"Feishu message failed: code={response.code}, msg={response.msg}"
            )
