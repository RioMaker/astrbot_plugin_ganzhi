import asyncio
import copy
from datetime import datetime, timedelta

import pytest
from astrbot_plugin_ganzhi import scheduler as module
from astrbot_plugin_ganzhi.calendar_core import BEIJING
from astrbot_plugin_ganzhi.scheduler import DailyScheduler


@pytest.fixture
def setup(monkeypatch):
    db, sent = {}, []
    clock = [datetime(2026, 9, 24, 8, tzinfo=BEIJING)]
    monkeypatch.setattr(module, "now_beijing", lambda: clock[0])

    async def get(key, default=None):
        return copy.deepcopy(db.get(key, default))

    async def put(key, value):
        db[key] = copy.deepcopy(value)

    async def publish(umo, instant, guard):
        async def send():
            sent.append(umo)
            return True

        await guard(send)

    scheduler = DailyScheduler(get, put, publish)
    return scheduler, clock, sent


async def test_default_off_due_once_reload_and_next_day(setup):
    s, clock, sent = setup
    await s.tick()
    assert sent == []
    await s.set_enabled("a", True)
    await asyncio.gather(s.tick(), s.tick())
    assert sent == ["a"]
    restarted = DailyScheduler(s.get, s.put, s.publish)
    await restarted.tick()
    assert sent == ["a"]
    await restarted.set_enabled("a", False)
    await restarted.set_enabled("a", True)
    await restarted.tick()
    assert sent == ["a"]
    clock[0] += timedelta(days=1)
    await restarted.tick()
    assert sent == ["a", "a"]


@pytest.mark.parametrize(
    "minute,send", [(-1, False), (0, True), (29, True), (30, False), (60, False)]
)
async def test_daily_window(setup, minute, send):
    s, clock, sent = setup
    await s.set_enabled("a", True)
    clock[0] += timedelta(minutes=minute)
    await s.tick()
    assert bool(sent) == send


async def test_disabled_during_generation_cannot_send(setup):
    s, _, sent = setup
    original = s.publish

    async def disable_before_send(umo, instant, guard):
        await s.set_enabled(umo, False)
        await original(umo, instant, guard)

    s.publish = disable_before_send
    await s.set_enabled("a", True)
    await s.tick()
    assert not sent


async def test_date_changes_during_generation_no_stale_report(setup):
    s, clock, sent = setup
    original = s.publish

    async def change_date(umo, instant, guard):
        clock[0] += timedelta(days=1)
        await original(umo, instant, guard)

    s.publish = change_date
    await s.set_enabled("a", True)
    await s.tick()
    assert not sent


async def test_failed_destination_retries_and_does_not_block_other_groups(setup):
    s, clock, sent = setup
    original = s.publish

    async def fail_a(umo, instant, guard):
        if umo == "a":

            async def reject():
                return False

            await guard(reject)
        else:
            await original(umo, instant, guard)

    s.publish = fail_a
    await s.set_enabled("a", True)
    await s.set_enabled("b", True)
    await s.tick()
    assert sent == ["b"]
    assert not (await s.status("a")).get("sent_date")
    await s.tick()
    assert (await s.status("a"))["attempts"] == 1
    clock[0] += timedelta(minutes=5)
    await s.tick()
    assert (await s.status("a"))["attempts"] == 2
    clock[0] += timedelta(minutes=5)
    await s.tick()
    clock[0] += timedelta(minutes=5)
    await s.tick()
    assert (await s.status("a"))["attempts"] == 3
    assert sent == ["b"]


async def test_concurrent_switches_do_not_lose_groups(setup):
    s, _, _ = setup
    await asyncio.gather(s.set_enabled("a", True), s.set_enabled("b", True))
    assert (await s.status("a"))["enabled"]
    assert (await s.status("b"))["enabled"]
