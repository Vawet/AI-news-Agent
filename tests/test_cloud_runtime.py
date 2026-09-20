"""Cloud runtime scheduling and trigger coordination tests."""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.runtime.coordinator import (
    InMemoryClaimStore,
    RunCoordinator,
    TriggerRequest,
)
from src.runtime.scheduler import build_schedule_trigger


def test_schedule_runs_wednesday_and_sunday_at_10_shanghai():
    trigger = build_schedule_trigger()
    start = datetime(2026, 9, 20, 10, 1, tzinfo=ZoneInfo("Asia/Shanghai"))

    first = trigger.get_next_fire_time(None, start)
    second = trigger.get_next_fire_time(first, first)

    assert first == datetime(2026, 9, 23, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert second == datetime(2026, 9, 27, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


@pytest.mark.asyncio
async def test_duplicate_trigger_id_only_runs_pipeline_once():
    runs: list[str] = []

    async def run_pipeline(trigger: TriggerRequest):
        runs.append(trigger.trigger_id)
        return {"title": "AI News", "url": "https://cdn.example/report.md"}

    coordinator = RunCoordinator(
        run_pipeline=run_pipeline,
        claims=InMemoryClaimStore(),
        cooldown_seconds=0,
    )
    trigger = TriggerRequest(
        trigger_id="event-1",
        source="feishu",
        chat_id="oc_allowed",
    )

    first = await coordinator.run(trigger)
    second = await coordinator.run(trigger)

    assert first.status == "completed"
    assert second.status == "duplicate"
    assert runs == ["event-1"]


@pytest.mark.asyncio
async def test_manual_trigger_cooldown_is_per_chat():
    now = [1_000.0]

    async def run_pipeline(_: TriggerRequest):
        return {"title": "AI News"}

    coordinator = RunCoordinator(
        run_pipeline=run_pipeline,
        claims=InMemoryClaimStore(),
        cooldown_seconds=300,
        clock=lambda: now[0],
    )

    first = await coordinator.run(
        TriggerRequest(trigger_id="event-1", source="feishu", chat_id="oc_a")
    )
    second = await coordinator.run(
        TriggerRequest(trigger_id="event-2", source="feishu", chat_id="oc_a")
    )
    other_chat = await coordinator.run(
        TriggerRequest(trigger_id="event-3", source="feishu", chat_id="oc_b")
    )

    assert first.status == "completed"
    assert second.status == "cooldown"
    assert other_chat.status == "completed"


@pytest.mark.asyncio
async def test_only_one_pipeline_runs_at_a_time():
    started = asyncio.Event()
    release = asyncio.Event()

    async def run_pipeline(_: TriggerRequest):
        started.set()
        await release.wait()
        return {}

    coordinator = RunCoordinator(
        run_pipeline=run_pipeline,
        claims=InMemoryClaimStore(),
        cooldown_seconds=0,
    )
    first_task = asyncio.create_task(
        coordinator.run(
            TriggerRequest(trigger_id="event-1", source="feishu", chat_id="oc_a")
        )
    )
    await started.wait()

    busy = await coordinator.run(
        TriggerRequest(trigger_id="event-2", source="feishu", chat_id="oc_b")
    )
    release.set()
    await first_task

    assert busy.status == "busy"
