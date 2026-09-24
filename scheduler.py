"""Small persistent per-session scheduler, driven by the plugin lifecycle."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

from .calendar_core import BEIJING, now_beijing


class DailyScheduler:
    def __init__(self, get, put, publish, *, at="08:00", grace=30, log=None):
        self.get, self.put, self.publish = get, put, publish
        hour, minute = map(int, at.split(":"))
        if not 0 <= hour < 24 or not 0 <= minute < 60:
            raise ValueError("日报时间须为 HH:MM。")
        self.hour, self.minute = hour, minute
        self.grace = timedelta(minutes=grace)
        self.log = log or (lambda _: None)
        self.lock = asyncio.Lock()
        self.tick_lock = asyncio.Lock()
        self.task = None

    async def status(self, umo):
        rows = await self.get("daily_subscriptions_v1", {})
        return dict(rows.get(umo, {}))

    async def set_enabled(self, umo, enabled):
        async with self.lock:
            rows = dict(await self.get("daily_subscriptions_v1", {}))
            row = dict(rows.get(umo, {}))
            row.update(enabled=enabled, revision=uuid4().hex)
            # Preserve the sent marker and attempts across off/on toggles.
            rows[umo] = row
            await self.put("daily_subscriptions_v1", rows)

    def due(self, row, instant):
        local = instant.astimezone(BEIJING)
        target = local.replace(hour=self.hour, minute=self.minute, second=0, microsecond=0)
        if not row.get("enabled") or not target <= local < target + self.grace:
            return False
        date_key = local.date().isoformat()
        if row.get("sent_date") == date_key:
            return False
        if row.get("attempt_date") == date_key:
            if row.get("attempts", 0) >= 3:
                return False
            retry = row.get("retry_at")
            if retry and local < datetime.fromisoformat(retry):
                return False
        return True

    async def tick(self, instant=None):
        async with self.tick_lock:
            instant = instant or now_beijing()
            rows = await self.get("daily_subscriptions_v1", {})
            # Sequential send avoids bursts and unbounded model concurrency.
            for umo, row in list(rows.items()):
                if self.due(row, instant):
                    try:
                        await self._publish_one(umo, row, instant)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        self.log(f"ganzhi 日报失败：{type(exc).__name__}")

    async def _publish_one(self, umo, scheduled_row, instant):
        date_key = instant.astimezone(BEIJING).date().isoformat()
        revision = scheduled_row.get("revision")
        async with self.lock:
            rows = dict(await self.get("daily_subscriptions_v1", {}))
            row = dict(rows.get(umo, {}))
            if row.get("revision") != revision or not self.due(row, instant):
                return
            attempts = row.get("attempts", 0) if row.get("attempt_date") == date_key else 0
            row.update(
                attempt_date=date_key,
                attempts=attempts + 1,
                retry_at=(instant + timedelta(minutes=5)).isoformat(),
            )
            rows[umo] = row
            await self.put("daily_subscriptions_v1", rows)

        async def guarded_send(send):
            # Recheck after the slow model call; an administrator may have disabled
            # the group or the date/window may have changed in the meantime.
            async with self.lock:
                latest = dict(await self.get("daily_subscriptions_v1", {}))
                current = dict(latest.get(umo, {}))
                current_time = now_beijing()
                target = current_time.replace(
                    hour=self.hour, minute=self.minute, second=0, microsecond=0
                )
                if (
                    not current.get("enabled")
                    or current.get("revision") != revision
                    or current.get("sent_date") == date_key
                    or current_time.date().isoformat() != date_key
                    or not target <= current_time < target + self.grace
                ):
                    return False
                result = await asyncio.wait_for(send(), timeout=30)
                if result is False:
                    raise RuntimeError("平台未接受日报消息")
                current.update(sent_date=date_key, retry_at="")
                latest[umo] = current
                await self.put("daily_subscriptions_v1", latest)
                return True

        await self.publish(umo, instant, guarded_send)

    def start(self):
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._loop(), name="ganzhi-daily")

    async def _loop(self):
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.log(f"ganzhi 日报调度异常：{type(exc).__name__}")
            await asyncio.sleep(30)

    async def close(self):
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
