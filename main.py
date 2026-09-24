"""AstrBot adapter. Only dedicated commands and explicit LLM tools are registered."""

import asyncio
import hashlib
import re
from dataclasses import dataclass

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import Image, Plain
from astrbot.api.star import Context, Star, register
from astrbot.core.star.filter.command import GreedyStr

from .calendar_core import now_beijing, parse_profile, snapshot
from .engine import agent_payload, build_report
from .renderer import Renderer, compact_text
from .scheduler import DailyScheduler

HELP_TEXT = """ganzhi · 干支纪时与日主日运
/干支：返回当前年、月、日、时四柱图片；已绑定则附日运和当前时辰宜忌。
/干支 辛巳：临时按日柱分析。
/干支 辛：也可只指定十天干日主。
/干支 20010319：临时按阳历生日分析（也支持 2001-03-19）。
/干支 绑定 20010319 或 /干支 绑定 辛巳：保存自己的资料。
/干支 解绑：删除自己的绑定。
/干支 我的：查看自己的绑定类型与日柱。
/干支 help：帮助。

/干支日报 开|关|状态（也支持 /干支 日报 开|关|状态）
日报按当前群单独设置，默认关闭，每天北京时间 {daily_time} 播报。
群主、群管理员、AstrBot 管理员可开关；包含五行流通与十天干日主简览。

别名 /干支纪年法、/干支纪时法 与 /干支 完全等效，后面同样可带生日、日柱和子命令。
生日默认且只接受阳历，不接受农历；临时分析不覆盖绑定。
默认北京时间、立春换年、节气换月、零点换日；当前配置：{boundary}。
精确到小时并标注两小时一个的时辰；缺少出生时刻时不补造出生时柱。
宜忌来自内置参考文档的简化建议；请 AI 分析时，工具会返回完整参考。
绑定按平台实例与用户保存；群内图片显示日柱，不显示生日原日期。"""


def field(obj, name, default=None):
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


@dataclass(frozen=True)
class Scope:
    umo: str
    platform_id: str
    platform_name: str
    user_id: str
    group_id: str
    admin: bool
    role: str
    bot: object

    @property
    def profile_key(self):
        raw = f"{self.platform_id}\0{self.user_id}"
        return "profile_v1_" + hashlib.sha256(raw.encode()).hexdigest()

    @property
    def group_umo(self):
        # OneBot's unique-session mode may append a user dimension to umo.
        # Public daily subscriptions always belong to the group itself.
        return f"{self.platform_id}:GroupMessage:{self.group_id}"


def capture(event):
    """Freeze all routing, identity and permission facts before the first await."""
    umo = str(event.unified_msg_origin)
    raw = field(event.message_obj, "raw_message")
    sender = field(raw, "sender")
    return Scope(
        umo=umo,
        platform_id=str(event.get_platform_id()),
        platform_name=str(event.get_platform_name()),
        user_id=str(event.get_sender_id()),
        group_id=str(event.get_group_id() or ""),
        admin=bool(event.is_admin()),
        role=str(field(sender, "role", "") or "").lower(),
        bot=getattr(event, "bot", None),
    )


@register("astrbot_plugin_ganzhi", "Rio", "干支纪时、日主日运与群日报", "0.2.4")
class GanzhiPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.config = config
        self.boundary = str(config.get("day_boundary", "midnight"))
        if self.boundary not in {"midnight", "zi"}:
            raise ValueError("day_boundary 只能为 midnight 或 zi")
        at = str(config.get("daily_time", "08:00"))
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", at):
            raise ValueError("daily_time 须为有效的 HH:MM")
        self.daily_time = at
        self.timeout = max(5, min(120, int(config.get("ai_timeout_seconds", 45))))
        self.render_gate = asyncio.Semaphore(2)
        self.profile_lock = asyncio.Lock()
        try:
            self.renderer = Renderer(str(config.get("chart_font_path", "") or ""))
        except (OSError, ValueError) as exc:
            self.renderer = None
            logger.warning(f"ganzhi 中文字体不可用，将返回文字：{type(exc).__name__}")
        self.scheduler = DailyScheduler(
            self.get_kv_data,
            self.put_kv_data,
            self._publish_daily,
            at=at,
            grace=max(1, min(180, int(config.get("daily_grace_minutes", 30)))),
            log=logger.warning,
        )

    async def initialize(self):
        self.scheduler.start()

    async def terminate(self):
        await self.scheduler.close()

    def help_text(self):
        return HELP_TEXT.format(
            daily_time=self.daily_time,
            boundary="零点换日" if self.boundary == "midnight" else "子初换日",
        )

    async def _profile(self, scope):
        stored = await self.get_kv_data(scope.profile_key, None)
        if stored is None:
            return None
        try:
            return parse_profile(stored["value"])
        except (ValueError, KeyError, TypeError):
            raise ValueError(
                "已保存的日主资料无法读取，请使用 /干支 绑定 重新录入，或 /干支 解绑。"
            ) from None

    async def _bind(self, scope, content):
        profile = parse_profile(content)
        if not scope.user_id:
            raise ValueError("无法识别当前用户。")
        async with self.profile_lock:
            await self.put_kv_data(scope.profile_key, profile.to_dict())
        return f"已绑定你的{'阳历生日' if profile.source == 'birthday' else '日主资料'}，日柱/日主为 {profile.day_pillar}。以后直接 /干支 即可分析。"

    async def _unbind(self, scope):
        async with self.profile_lock:
            await self.delete_kv_data(scope.profile_key)
        return "已删除你的日主绑定。"

    async def _can_manage(self, scope):
        if scope.admin:
            return True
        if scope.platform_name != "aiocqhttp":
            return False
        if scope.role:
            return scope.role in {"owner", "admin"}
        lookup = getattr(scope.bot, "call_action", None)
        if not lookup:
            return False
        try:
            response = await asyncio.wait_for(
                lookup(
                    action="get_group_member_info",
                    group_id=int(scope.group_id),
                    user_id=int(scope.user_id),
                    no_cache=True,
                ),
                timeout=8,
            )
            member = field(response, "data", response)
            return field(member, "role", "") in {"owner", "admin"}
        except Exception:
            return False

    async def _daily_switch(self, scope, action):
        if not scope.group_id:
            return "请在需要播报的群内使用 /干支日报 开|关|状态。"
        if action in {"", "状态"}:
            row = await self.scheduler.status(scope.group_umo)
            return f"本群干支日报：{'开' if row.get('enabled') else '关'}；北京时间 {self.daily_time}。"
        if action not in {"开", "关"}:
            return "格式：/干支日报 开|关|状态。"
        if not await self._can_manage(scope):
            return "仅群主、群管理员或 AstrBot 管理员可以设置本群日报。"
        await self.scheduler.set_enabled(scope.group_umo, action == "开")
        return f"本群干支日报已{action}。" + (
            f"每天北京时间 {self.daily_time} 播报五行流通和十天干日主简览。"
            if action == "开"
            else ""
        )

    async def _report(self, scope, content="", instant=None):
        instant = instant or now_beijing()
        profile = parse_profile(content) if content else await self._profile(scope)
        return build_report(snapshot(instant, self.boundary), profile)

    async def _components(self, report):
        if self.renderer is not None:
            try:
                async with self.render_gate:
                    png = await asyncio.to_thread(self.renderer.render, report)
                return [Image.fromBytes(png)]
            except Exception as exc:
                logger.warning(f"ganzhi 图片生成失败：{type(exc).__name__}")
        return [Plain("图片暂不可用，以下为文字内容：\n" + compact_text(report))]

    @filter.command("干支", alias={"干支纪年法", "干支纪时法"})
    async def ganzhi_command(self, event: AstrMessageEvent, content: GreedyStr):
        """当前干支图片、阳历生日或日柱分析；help 查看绑定和日报指令。"""
        scope, instant = capture(event), now_beijing()
        text = str(content or "").strip()
        event.stop_event()
        try:
            if text.lower() in {"help", "帮助"}:
                yield event.plain_result(self.help_text())
            elif text == "解绑":
                yield event.plain_result(await self._unbind(scope))
            elif text == "我的":
                p = await self._profile(scope)
                yield event.plain_result(
                    f"已绑定日柱/日主：{p.day_pillar}（{'阳历生日换算' if p.source == 'birthday' else '直接指定'}）。"
                    if p
                    else "尚未绑定。用 /干支 绑定 20010319 或 /干支 绑定 辛巳。"
                )
            else:
                parts = text.split(maxsplit=1)
                if parts and parts[0] == "绑定":
                    yield event.plain_result(
                        await self._bind(scope, parts[1] if len(parts) > 1 else "")
                    )
                elif parts and parts[0] == "日报":
                    yield event.plain_result(
                        await self._daily_switch(scope, parts[1] if len(parts) > 1 else "状态")
                    )
                else:
                    report = await self._report(scope, text, instant)
                    yield event.chain_result(await self._components(report))
        except ValueError as exc:
            yield event.plain_result(str(exc))
        except Exception as exc:
            logger.error(f"ganzhi 指令处理失败：{type(exc).__name__}")
            yield event.plain_result("干支处理暂时失败，请稍后重试；管理员可查看插件日志。")

    @filter.command("干支日报", alias={"干支纪年法日报", "干支纪时法日报"})
    async def daily_command(self, event: AstrMessageEvent, content: GreedyStr):
        """群主、群管理员或 AstrBot 管理员设置本群干支日报开关。"""
        scope = capture(event)
        action = str(content or "").strip()
        event.stop_event()
        try:
            yield event.plain_result(await self._daily_switch(scope, action))
        except Exception as exc:
            logger.error(f"ganzhi 日报设置失败：{type(exc).__name__}")
            yield event.plain_result("日报设置暂时失败，请稍后重试。")

    @filter.llm_tool(name="ganzhi_analyze")
    async def analyze_tool(
        self, event: AstrMessageEvent, profile: str = "", send_image: bool = True
    ) -> str:
        """查询当前干支、今日五行和日主日运，返回计算事实与完整参考文档供解读。生日默认且只接受阳历。未给资料时优先使用当前发送人的绑定；没有绑定则只分析公共环境。此工具不会写入绑定。

        Args:
            profile(string): 可留空，或阳历生日如 20010319、日柱如 辛巳、日主如 辛。用户说农历时先让其换成阳历，不得当作阳历。
            send_image(boolean): 是否同时向当前会话发送简明干支图片，默认 true。
        """
        scope, instant = capture(event), now_beijing()
        supplied = str(profile or "").strip()
        try:
            report = await self._report(scope, supplied, instant)
            status = "未请求发送图片"
            if send_image:
                try:
                    sent = await asyncio.wait_for(
                        self.context.send_message(
                            scope.umo, MessageChain(await self._components(report))
                        ),
                        timeout=30,
                    )
                    status = (
                        "简明卡片已发送"
                        if sent is not False
                        else "平台未接受卡片，仍可按以下数据解读"
                    )
                except Exception:
                    status = "卡片发送失败，仍可按以下数据解读"
            return status + "\n" + agent_payload(report)
        except ValueError as exc:
            return str(exc)
        except Exception as exc:
            logger.error(f"ganzhi 工具失败：{type(exc).__name__}")
            return "干支查询暂时失败，请稍后重试；不要自行猜测计算结果。"

    @filter.llm_tool(name="ganzhi_profile")
    async def profile_tool(
        self, event: AstrMessageEvent, action: str = "view", profile: str = ""
    ) -> str:
        """管理当前发送人自己的生日/日柱。只有用户明确要求记住、绑定、修改或删除时才用 bind/unbind；临时分析请调用 ganzhi_analyze。

        Args:
            action(string): view 查看自己的日柱，bind 绑定或覆盖自己的资料，unbind 删除自己的资料。
            profile(string): bind 时必填；仅阳历生日如 20010319、日柱如 辛巳 或日主如 辛。默认阳历，不接受农历。
        """
        scope = capture(event)
        try:
            if action == "bind":
                return await self._bind(scope, profile)
            if action == "unbind":
                return await self._unbind(scope)
            if action == "view":
                p = await self._profile(scope)
                return f"已绑定日柱/日主：{p.day_pillar}。" if p else "尚未绑定日主资料。"
            return "action 只能是 view、bind 或 unbind。"
        except ValueError as exc:
            return str(exc)
        except Exception as exc:
            logger.error(f"ganzhi 资料管理失败：{type(exc).__name__}")
            return "资料处理暂时失败，请稍后重试。"

    async def _publish_daily(self, umo, instant, guarded_send):
        report = build_report(snapshot(instant, self.boundary), daily=True)
        narration = ""
        if self.config.get("daily_use_ai", True):
            try:

                async def generate():
                    provider_id = str(self.config.get("daily_provider_id", "") or "")
                    if not provider_id:
                        provider_id = await self.context.get_current_chat_provider_id(umo=umo)
                    if not provider_id:
                        raise ValueError("无可用日报模型")
                    return await self.context.llm_generate(
                        chat_provider_id=provider_id,
                        prompt="请写简短群公共干支日报，控制在250–400字。先用一句话报当日干支与五行流通，"
                        "然后逐个覆盖甲乙丙丁戊己庚辛壬癸十个日主，每个只写一行短建议。"
                        "图片已有宜忌表，不要重复整表，不写长篇原理、百分比、免责声明和结尾总结。"
                        "不针对群成员，不编造完整命局，不改写工具历法结果。"
                        "候选通关、制约和合化须保留条件语气，不能说成已经成功。依据：\n"
                        + agent_payload(report),
                    )

                response = await asyncio.wait_for(generate(), timeout=self.timeout)
                narration = str(response.completion_text or "").strip()
                if not narration or len(narration) > 3500:
                    raise ValueError("日报模型输出为空或过长")
            except Exception as exc:
                narration = ""
                logger.warning(f"ganzhi 日报使用规则简报：{type(exc).__name__}")
        # The deterministic card includes all ten stems even if the model omits one.
        components = await self._components(report)
        if narration:
            components.append(Plain("AI 日报解读\n" + narration))
        elif self.config.get("daily_use_ai", True):
            components.append(Plain("本次 AI 解读暂不可用，已附完整规则简报。"))
        await guarded_send(lambda: self.context.send_message(umo, MessageChain(components)))
