"""Serialize paid pipeline runs and make trigger handling idempotent."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class TriggerRequest:
    trigger_id: str
    source: str
    chat_id: str = ""


@dataclass(frozen=True)
class RunResult:
    status: str
    payload: dict[str, Any] = field(default_factory=dict)
    retry_after_seconds: int = 0
    error: str = ""


class ClaimStore(Protocol):
    async def claim(self, trigger_id: str) -> bool:
        """Return true exactly once for a trigger id."""

    async def finish(self, trigger_id: str, status: str) -> None:
        """Persist the terminal status when supported."""


class InMemoryClaimStore:
    """Process-local claim store used by tests and local development."""

    def __init__(self) -> None:
        self._claimed: set[str] = set()
        self._lock = asyncio.Lock()

    async def claim(self, trigger_id: str) -> bool:
        async with self._lock:
            if trigger_id in self._claimed:
                return False
            self._claimed.add(trigger_id)
            return True

    async def finish(self, trigger_id: str, status: str) -> None:
        return None


PipelineRunner = Callable[
    [TriggerRequest],
    Awaitable[dict[str, Any]] | dict[str, Any],
]


class RunCoordinator:
    """Apply dedupe, per-chat cooldown, and single-flight execution."""

    def __init__(
        self,
        *,
        run_pipeline: PipelineRunner,
        claims: ClaimStore,
        cooldown_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._run_pipeline = run_pipeline
        self._claims = claims
        self._cooldown_seconds = max(0, cooldown_seconds)
        self._clock = clock
        self._run_lock = asyncio.Lock()
        self._chat_last_run: dict[str, float] = {}

    async def run(self, trigger: TriggerRequest) -> RunResult:
        if not trigger.trigger_id.strip():
            return RunResult(status="rejected", error="trigger_id is required")

        if not await self._claims.claim(trigger.trigger_id):
            return RunResult(status="duplicate")

        now = self._clock()
        if trigger.source == "feishu" and trigger.chat_id:
            previous = self._chat_last_run.get(trigger.chat_id)
            if previous is not None:
                retry_after = int(self._cooldown_seconds - (now - previous))
                if retry_after > 0:
                    await self._claims.finish(trigger.trigger_id, "cooldown")
                    return RunResult(
                        status="cooldown",
                        retry_after_seconds=retry_after,
                    )

        if self._run_lock.locked():
            await self._claims.finish(trigger.trigger_id, "busy")
            return RunResult(status="busy")

        async with self._run_lock:
            if trigger.source == "feishu" and trigger.chat_id:
                self._chat_last_run[trigger.chat_id] = now
            try:
                value = self._run_pipeline(trigger)
                payload = await value if inspect.isawaitable(value) else value
            except Exception as exc:  # noqa: BLE001 - isolate background run failures
                await self._claims.finish(trigger.trigger_id, "failed")
                return RunResult(
                    status="failed",
                    error=f"{type(exc).__name__}: {exc}",
                )

        await self._claims.finish(trigger.trigger_id, "completed")
        return RunResult(status="completed", payload=payload or {})
