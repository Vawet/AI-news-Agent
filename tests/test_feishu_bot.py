"""Feishu mention parsing and authorization tests."""

from src.integrations.feishu_bot import FeishuMessage, should_trigger


def test_group_mention_from_allowed_chat_triggers():
    message = FeishuMessage(
        event_id="event-1",
        chat_id="oc_allowed",
        chat_type="group",
        message_type="text",
        text="@AI News 生成本期资讯",
        mentions=("@AI News",),
    )

    assert should_trigger(message, {"oc_allowed"}) is True


def test_message_without_mention_does_not_trigger():
    message = FeishuMessage(
        event_id="event-1",
        chat_id="oc_allowed",
        chat_type="group",
        message_type="text",
        text="生成本期资讯",
        mentions=(),
    )

    assert should_trigger(message, {"oc_allowed"}) is False


def test_unlisted_chat_does_not_trigger():
    message = FeishuMessage(
        event_id="event-1",
        chat_id="oc_other",
        chat_type="group",
        message_type="text",
        text="@AI News 生成本期资讯",
        mentions=("@AI News",),
    )

    assert should_trigger(message, {"oc_allowed"}) is False


def test_direct_message_does_not_trigger():
    message = FeishuMessage(
        event_id="event-1",
        chat_id="oc_allowed",
        chat_type="p2p",
        message_type="text",
        text="@AI News 生成本期资讯",
        mentions=("@AI News",),
    )

    assert should_trigger(message, {"oc_allowed"}) is False
