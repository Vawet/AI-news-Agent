"""Feishu HTTP event authentication and dispatch tests."""

import hashlib
import json

from src.integrations.feishu_http import FeishuHTTPEventDispatcher

ENCRYPT_KEY = "encrypt-key"
VERIFICATION_TOKEN = "verification-token"


def _signed_headers(body: bytes) -> dict[str, str]:
    timestamp = "1789960000"
    nonce = "nonce-1"
    signature = hashlib.sha256(
        (timestamp + nonce + ENCRYPT_KEY).encode() + body
    ).hexdigest()
    return {
        "x-lark-request-timestamp": timestamp,
        "x-lark-request-nonce": nonce,
        "x-lark-signature": signature,
    }


def _message_event(*, token: str = VERIFICATION_TOKEN) -> bytes:
    return json.dumps(
        {
            "schema": "2.0",
            "header": {
                "event_id": "event-1",
                "event_type": "im.message.receive_v1",
                "create_time": "1789960000",
                "token": token,
                "app_id": "cli_test",
                "tenant_key": "tenant",
            },
            "event": {
                "sender": {
                    "sender_id": {"open_id": "ou_sender"},
                    "sender_type": "user",
                    "tenant_key": "tenant",
                },
                "message": {
                    "message_id": "om_message",
                    "create_time": "1789960000",
                    "chat_id": "oc_allowed",
                    "chat_type": "group",
                    "message_type": "text",
                    "content": json.dumps({"text": "@AI News 生成资讯"}),
                    "mentions": [
                        {
                            "key": "@_user_1",
                            "id": {"open_id": "ou_bot"},
                            "name": "AI News",
                            "tenant_key": "tenant",
                        }
                    ],
                },
            },
        }
    ).encode()


def test_url_verification_returns_challenge() -> None:
    dispatcher = FeishuHTTPEventDispatcher(
        encrypt_key=ENCRYPT_KEY,
        verification_token=VERIFICATION_TOKEN,
        message_handler=lambda _: None,
    )
    body = json.dumps(
        {
            "type": "url_verification",
            "token": VERIFICATION_TOKEN,
            "challenge": "challenge-code",
        }
    ).encode()

    response = dispatcher.dispatch(uri="/feishu/events", headers={}, body=body)

    assert response.status_code == 200
    assert json.loads(response.content) == {"challenge": "challenge-code"}


def test_signed_message_event_is_dispatched() -> None:
    received = []
    dispatcher = FeishuHTTPEventDispatcher(
        encrypt_key=ENCRYPT_KEY,
        verification_token=VERIFICATION_TOKEN,
        message_handler=received.append,
    )
    body = _message_event()

    response = dispatcher.dispatch(
        uri="/feishu/events",
        headers=_signed_headers(body),
        body=body,
    )

    assert response.status_code == 200
    assert json.loads(response.content) == {"msg": "success"}
    assert len(received) == 1
    assert received[0].header.event_id == "event-1"


def test_invalid_signature_is_rejected() -> None:
    dispatcher = FeishuHTTPEventDispatcher(
        encrypt_key=ENCRYPT_KEY,
        verification_token=VERIFICATION_TOKEN,
        message_handler=lambda _: None,
    )
    body = _message_event()
    headers = _signed_headers(body)
    headers["x-lark-signature"] = "invalid"

    response = dispatcher.dispatch(
        uri="/feishu/events",
        headers=headers,
        body=body,
    )

    assert response.status_code == 401


def test_invalid_verification_token_is_rejected() -> None:
    dispatcher = FeishuHTTPEventDispatcher(
        encrypt_key=ENCRYPT_KEY,
        verification_token=VERIFICATION_TOKEN,
        message_handler=lambda _: None,
    )
    body = _message_event(token="wrong-token")

    response = dispatcher.dispatch(
        uri="/feishu/events",
        headers=_signed_headers(body),
        body=body,
    )

    assert response.status_code == 401
