"""Official Feishu HTTP event dispatcher adapter."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class HTTPEventResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes


class FeishuHTTPEventDispatcher:
    """Verify, decrypt, and dispatch Feishu application events."""

    _LARK_HEADERS: ClassVar[dict[str, str]] = {
        "x-lark-request-timestamp": "X-Lark-Request-Timestamp",
        "x-lark-request-nonce": "X-Lark-Request-Nonce",
        "x-lark-signature": "X-Lark-Signature",
        "x-request-id": "X-Request-Id",
    }

    def __init__(
        self,
        *,
        encrypt_key: str,
        verification_token: str,
        message_handler,
    ) -> None:
        import lark_oapi as lark

        self._encrypt_key = encrypt_key
        self._dispatcher = (
            lark.EventDispatcherHandler.builder(
                encrypt_key,
                verification_token,
                lark.LogLevel.INFO,
            )
            .register_p2_im_message_receive_v1(message_handler)
            .build()
        )

    def dispatch(
        self,
        *,
        uri: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> HTTPEventResponse:
        from lark_oapi.core.model import RawRequest

        canonical_headers = self._canonical_headers(headers)
        authentication_error = self._verify_signature(canonical_headers, body)
        if authentication_error is not None:
            return authentication_error

        raw_request = RawRequest()
        raw_request.uri = uri
        raw_request.headers = canonical_headers
        raw_request.body = body

        raw_response = self._dispatcher.do(raw_request)
        content = raw_response.content or b""
        status_code = raw_response.status_code or 500
        if status_code >= 500 and b"invalid verification_token" in content:
            status_code = 401
        return HTTPEventResponse(
            status_code=status_code,
            headers=dict(raw_response.headers),
            content=content,
        )

    @classmethod
    def _canonical_headers(cls, headers: Mapping[str, str]) -> dict[str, str]:
        canonical: dict[str, str] = {}
        for name, value in headers.items():
            lower_name = name.lower()
            canonical[cls._LARK_HEADERS.get(lower_name, name)] = value
        return canonical

    def _verify_signature(
        self,
        headers: Mapping[str, str],
        body: bytes,
    ) -> HTTPEventResponse | None:
        """Reject malformed signed requests before the SDK maps them to 500."""
        if not self._encrypt_key:
            return None
        signature = headers.get("X-Lark-Signature")
        if not signature:
            # URL-verification requests are not signed. Encrypted challenge
            # bodies cannot be classified until the SDK decrypts them.
            try:
                payload = json.loads(body)
            except (TypeError, json.JSONDecodeError):
                payload = {}
            if payload.get("type") == "url_verification" or "encrypt" in payload:
                return None
            return HTTPEventResponse(
                status_code=401,
                headers={"content-type": "application/json; charset=utf-8"},
                content=b'{"msg":"missing Feishu signature"}',
            )
        timestamp = headers.get("X-Lark-Request-Timestamp")
        nonce = headers.get("X-Lark-Request-Nonce")
        if not timestamp or not nonce:
            return HTTPEventResponse(
                status_code=401,
                headers={"content-type": "application/json; charset=utf-8"},
                content=b'{"msg":"missing Feishu signature headers"}',
            )
        payload = (timestamp + nonce + self._encrypt_key).encode("utf-8") + body
        expected = hashlib.sha256(payload).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return HTTPEventResponse(
                status_code=401,
                headers={"content-type": "application/json; charset=utf-8"},
                content=b'{"msg":"invalid Feishu signature"}',
            )
        return None
