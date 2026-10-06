import asyncio
import inspect
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from astrbot_plugin_ganzhi.calendar_core import BEIJING
from astrbot_plugin_ganzhi.main import GanzhiPlugin, capture
from astrbot_plugin_ganzhi.renderer import compact_text
from conftest import Context, Event


async def command(plugin, event, text):
    return [item async for item in plugin.ganzhi_command(event, text)]


async def test_binding_persists_and_temporary_input_does_not_overwrite():
    ctx, e = Context(), Event()
    plugin = GanzhiPlugin(ctx, {})
    result = await command(plugin, e, "绑定 20010319")
    assert "辛巳" in result[0] and e.stopped
    assert (await plugin._report(capture(e)))["personal"]["master"] == "辛"
    assert (await plugin._report(capture(e), "甲子"))["personal"]["master"] == "甲"
    reloaded = GanzhiPlugin(Context(ctx.db), {})
    assert (await reloaded._profile(capture(e))).day_pillar == "辛巳"
    assert "删除" in (await command(reloaded, e, "解绑"))[0]
    assert await reloaded._profile(capture(e)) is None


async def test_profile_isolation_across_users_and_platform_instances():
    p = GanzhiPlugin(Context(), {})
    await p._bind(capture(Event()), "辛巳")
    assert await p._profile(capture(Event(user="other"))) is None
    assert await p._profile(capture(Event(platform="other-bot"))) is None
    assert (await p._profile(capture(Event(group="other-group")))).day_pillar == "辛巳"


@pytest.mark.parametrize(
    "role,admin,expected",
    [
        ("member", False, False),
        ("owner", False, True),
        ("admin", False, True),
        ("member", True, True),
    ],
)
async def test_daily_permission(role, admin, expected):
    p, e = GanzhiPlugin(Context(), {}), Event(role=role, admin=admin)
    assert not (await p.scheduler.status(e.unified_msg_origin)).get("enabled", False)
    reply = await p._daily_switch(capture(e), "开")
    assert (await p.scheduler.status(e.unified_msg_origin)).get("enabled", False) == expected
    assert ("已开" in reply) == expected


async def test_daily_scope_and_private_chat():
    p = GanzhiPlugin(Context(), {})
    await p._daily_switch(capture(Event(role="owner")), "开")
    other = capture(Event(group="other"))
    assert "关" in await p._daily_switch(other, "状态")
    assert "群内" in await p._daily_switch(capture(Event(group="", admin=True)), "开")


async def test_unique_session_mode_still_has_one_group_switch():
    p = GanzhiPlugin(Context(), {})
    owner = Event(role="owner")
    owner.unified_msg_origin = "qq-one:GroupMessage:10001_20001"
    await p._daily_switch(capture(owner), "开")
    another_admin = Event(user="10002", role="admin")
    another_admin.unified_msg_origin = "qq-one:GroupMessage:10002_20001"
    assert "：开" in await p._daily_switch(capture(another_admin), "状态")
    await p._daily_switch(capture(another_admin), "关")
    assert "：关" in await p._daily_switch(capture(owner), "状态")
    assert list(p.db["daily_subscriptions_v1"]) == ["qq-one:GroupMessage:20001"]


async def test_missing_role_onebot_lookup_and_freeze():
    e = Event(role="")

    async def lookup(**kwargs):
        assert kwargs["group_id"] == 20001
        assert kwargs["user_id"] == 10001
        assert kwargs["no_cache"] is True
        e.user = "hijacked"
        return {"data": {"role": "admin"}}

    e.bot = SimpleNamespace(call_action=lookup)
    scope = capture(e)
    p = GanzhiPlugin(Context(), {})
    assert "已开" in await p._daily_switch(scope, "开")
    assert scope.user_id == "10001"


async def test_image_command_and_invalid_input():
    p, e = GanzhiPlugin(Context(), {}), Event()
    result = await command(p, e, "")
    assert result[0][0].type == "image"
    assert result[0][0].data.startswith(b"\x89PNG")
    assert "阳历" in (await command(p, e, "help"))[0]
    assert "六十甲子" in (await command(p, e, "甲丑"))[0]
    p.renderer = None
    assert (await command(p, e, "辛巳"))[0][0].type == "plain"


async def test_llm_payload_binding_and_original_route():
    ctx, e = Context(), Event()
    p = GanzhiPlugin(ctx, {})
    await p._bind(capture(e), "20010319")
    original = e.unified_msg_origin
    get = p.get_kv_data

    async def mutate_event(key, default=None):
        e.unified_msg_origin = "other:GroupMessage:hijacked"
        e.user = "changed"
        return await get(key, default)

    p.get_kv_data = mutate_event
    payload = await p.analyze_tool(e)
    report = json.loads(payload.split("\n", 1)[1])
    assert report["calculated"]["personal"]["day_pillar"] == "辛巳"
    assert "2001-03-19" not in payload
    assert ctx.sent[0][0] == original
    assert "reference_document" in report


async def test_profile_tool_only_current_sender():
    p, e = GanzhiPlugin(Context(), {}), Event()
    assert "已绑定" in await p.profile_tool(e, "bind", "壬寅")
    assert "壬寅" in await p.profile_tool(e)
    assert "尚未" in await p.profile_tool(Event(user="stranger"))
    assert "删除" in await p.profile_tool(e, "unbind")


@pytest.mark.parametrize("ai_failure", [None, RuntimeError("unavailable"), asyncio.TimeoutError()])
async def test_daily_contains_ten_masters_and_model_failure_fallback(ai_failure):
    ctx = Context()
    ctx.failure = ai_failure
    p = GanzhiPlugin(ctx, {"daily_append_text": True})
    # Include a binding to make sure group broadcasts never consult it.
    await p._bind(capture(Event()), "20010319")

    async def guard(send):
        await send()

    await p._publish_daily(
        "qq-one:GroupMessage:20001", datetime(2026, 9, 24, 8, tzinfo=BEIJING), guard
    )
    assert len(ctx.sent) == 1
    assert ctx.sent[0][1].chain[0].type == "image"
    assert "2001-03-19" not in ctx.prompts[0]["prompt"]
    if ai_failure:
        text = ctx.sent[0][1].chain[-1].text
        assert all(stem in text for stem in "甲乙丙丁戊己庚辛壬癸")
    else:
        assert "AI 日报" in ctx.sent[0][1].chain[-1].text


@pytest.mark.parametrize("config", [{}, {"daily_use_ai": True}, {"daily_use_ai": False}])
async def test_daily_defaults_and_legacy_configs_send_only_image(config):
    ctx = Context()
    p = GanzhiPlugin(ctx, config)
    await p._bind(capture(Event()), "20010319")
    reports = []
    render = p.renderer.render

    def record(report):
        reports.append(report)
        return render(report)

    p.renderer.render = record

    async def guard(send):
        return await send()

    await p._publish_daily(
        "qq-one:GroupMessage:20001", datetime(2026, 10, 6, 8, tzinfo=BEIJING), guard
    )
    assert len(ctx.sent) == 1
    umo, message = ctx.sent[0]
    assert umo == "qq-one:GroupMessage:20001"
    assert [item.type for item in message.chain] == ["image"]
    assert message.chain[0].data.startswith(b"\x89PNG")
    assert ctx.prompts == []
    assert reports[0]["personal"] is None
    assert [row["master"] for row in reports[0]["ten_masters"]] == list("甲乙丙丁戊己庚辛壬癸")


async def test_schema_defaults_send_only_image():
    schema = json.loads((Path(__file__).parents[1] / "_conf_schema.json").read_text("utf-8"))
    defaults = {key: row["default"] for key, row in schema.items()}
    assert defaults["daily_append_text"] is False
    await test_daily_defaults_and_legacy_configs_send_only_image(defaults)


async def test_opt_in_rule_text_does_not_call_model():
    ctx = Context()
    p = GanzhiPlugin(ctx, {"daily_append_text": True, "daily_use_ai": False})
    instant = datetime(2026, 10, 6, 8, tzinfo=BEIJING)

    async def guard(send):
        return await send()

    await p._publish_daily("qq-one:GroupMessage:20001", instant, guard)
    chain = ctx.sent[0][1].chain
    assert [item.type for item in chain] == ["image", "plain"]
    report = await p._report(capture(Event()), instant=instant)
    assert compact_text(report).splitlines()[1] in chain[1].text
    assert all(stem in chain[1].text for stem in "甲乙丙丁戊己庚辛壬癸")
    assert ctx.prompts == []


@pytest.mark.parametrize("broken_render", [False, True])
async def test_daily_render_failure_sends_nothing_and_retries(monkeypatch, broken_render):
    from astrbot_plugin_ganzhi import scheduler as scheduler_module

    ctx = Context()
    p = GanzhiPlugin(ctx, {"daily_append_text": True})
    working_renderer = p.renderer
    clock = [datetime(2026, 10, 6, 8, tzinfo=BEIJING)]
    monkeypatch.setattr(scheduler_module, "now_beijing", lambda: clock[0])
    umo = "qq-one:GroupMessage:20001"

    def fail(report):
        raise OSError("render unavailable")

    p.renderer = SimpleNamespace(render=fail) if broken_render else None
    await p.scheduler.set_enabled(umo, True)
    await p.scheduler.tick()
    state = await p.scheduler.status(umo)
    assert state["attempts"] == 1 and not state.get("sent_date")
    assert ctx.sent == [] and ctx.prompts == []
    await p.scheduler.tick()
    assert (await p.scheduler.status(umo))["attempts"] == 1
    p.renderer = working_renderer
    p.config["daily_append_text"] = False
    clock[0] += timedelta(minutes=5)
    await p.scheduler.tick()
    assert len(ctx.sent) == 1
    assert [item.type for item in ctx.sent[0][1].chain] == ["image"]
    state = await p.scheduler.status(umo)
    assert state["attempts"] == 2 and state["sent_date"] == "2026-10-06"


def test_aliases_and_tool_arg_contract():
    assert GanzhiPlugin.ganzhi_command.command_meta["alias"] == {"干支纪年法", "干支纪时法"}
    for fn in (GanzhiPlugin.analyze_tool, GanzhiPlugin.profile_tool):
        params = set(inspect.signature(fn).parameters) - {"self", "event"}
        docs = set(re.findall(r"^\s+(\w+)\((?:string|boolean)\):", inspect.getdoc(fn), re.M))
        assert params == docs


async def test_scheduler_lifecycle_cleans_task():
    p = GanzhiPlugin(Context(), {})
    await p.initialize()
    task = p.scheduler.task
    assert task is not None
    await p.initialize()
    assert p.scheduler.task is task
    await p.terminate()
    assert task.done() and p.scheduler.task is None
