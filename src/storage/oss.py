"""Alibaba Cloud OSS artifacts and durable trigger claims."""

from __future__ import annotations

import asyncio
import json
import posixpath
from pathlib import Path
from urllib.parse import quote


class OSSStorage:
    def __init__(
        self,
        *,
        endpoint: str,
        bucket_name: str,
        access_key_id: str,
        access_key_secret: str,
        prefix: str = "ai-news-agent",
        public_base_url: str = "",
    ) -> None:
        import oss2

        self._oss2 = oss2
        self._bucket = oss2.Bucket(
            oss2.Auth(access_key_id, access_key_secret),
            endpoint,
            bucket_name,
        )
        self._bucket_name = bucket_name
        self._endpoint = endpoint.rstrip("/")
        self._prefix = prefix.strip("/")
        self._public_base_url = public_base_url.rstrip("/")

    async def claim(self, trigger_id: str) -> bool:
        return await asyncio.to_thread(self._claim_sync, trigger_id)

    def _claim_sync(self, trigger_id: str) -> bool:
        key = self._key("claims", f"{quote(trigger_id, safe='')}.json")
        payload = json.dumps({"trigger_id": trigger_id, "status": "claimed"})
        try:
            self._bucket.put_object(
                key,
                payload.encode("utf-8"),
                headers={"If-None-Match": "*"},
            )
            return True
        except self._oss2.exceptions.OssError as exc:
            if getattr(exc, "status", None) in (409, 412):
                return False
            raise

    async def finish(self, trigger_id: str, status: str) -> None:
        await asyncio.to_thread(self._finish_sync, trigger_id, status)

    def _finish_sync(self, trigger_id: str, status: str) -> None:
        key = self._key("claims", f"{quote(trigger_id, safe='')}.json")
        payload = json.dumps(
            {"trigger_id": trigger_id, "status": status},
            ensure_ascii=False,
        )
        self._bucket.put_object(key, payload.encode("utf-8"))

    async def upload_file(self, path: Path) -> str:
        return await asyncio.to_thread(self._upload_file_sync, path)

    def _upload_file_sync(self, path: Path) -> str:
        key = self._key("reports", path.name)
        self._bucket.put_object_from_file(key, str(path))
        if self._public_base_url:
            return f"{self._public_base_url}/{quote(key, safe='/')}"
        return f"{self._endpoint}/{self._bucket_name}/{quote(key, safe='/')}"

    def _key(self, *parts: str) -> str:
        return posixpath.join(self._prefix, *parts)
