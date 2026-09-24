"""Minimal AstrBot doubles. These tests do not claim a live QQ integration."""

import copy
import logging
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def module(name, **attrs):
    item = ModuleType(name)
    item.__dict__.update(attrs)
    sys.modules[name] = item
    return item


def decorator(kind, **metadata):
    def wrap(fn):
        setattr(fn, kind, metadata)
        return fn

    return wrap


class Star:
    def __init__(self, context):
        self.context = context
        self.db = context.db

    async def get_kv_data(self, key, default=None):
        return copy.deepcopy(self.db.get(key, default))

    async def put_kv_data(self, key, value):
        self.db[key] = copy.deepcopy(value)

    async def delete_kv_data(self, key):
        self.db.pop(key, None)


class MessageChain:
    def __init__(self, chain):
        self.chain = chain


class Image:
    @staticmethod
    def fromBytes(data):
        return SimpleNamespace(type="image", data=data)


class Plain:
    def __init__(self, text):
        self.type, self.text = "plain", text


class GreedyStr(str):
    pass


module("astrbot")
module("astrbot.api", AstrBotConfig=dict, logger=logging.getLogger("ganzhi-test"))
module(
    "astrbot.api.event",
    AstrMessageEvent=object,
    MessageChain=MessageChain,
    filter=SimpleNamespace(
        command=lambda name, **kw: decorator("command_meta", name=name, **kw),
        llm_tool=lambda **kw: decorator("tool_meta", **kw),
    ),
)
module("astrbot.api.message_components", Image=Image, Plain=Plain)
module("astrbot.api.star", Star=Star, Context=object, register=lambda *a: lambda cls: cls)
module("astrbot.core")
module("astrbot.core.star")
module("astrbot.core.star.filter")
module("astrbot.core.star.filter.command", GreedyStr=GreedyStr)


class Context:
    def __init__(self, db=None):
        self.db = {} if db is None else db
        self.sent = []
        self.prompts = []
        self.answer = "甲乙丙丁戊己庚辛壬癸：按规则安排当日事项。"
        self.failure = None

    async def send_message(self, umo, chain):
        self.sent.append((umo, chain))
        return True

    async def get_current_chat_provider_id(self, umo):
        return "configured-provider"

    async def llm_generate(self, **kwargs):
        self.prompts.append(kwargs)
        if self.failure:
            raise self.failure
        return SimpleNamespace(completion_text=self.answer)


class Event:
    def __init__(self, user="10001", group="20001", platform="qq-one", role="member", admin=False):
        self.user, self.group, self.platform = user, group, platform
        self.unified_msg_origin = (
            f"{platform}:GroupMessage:{group}" if group else f"{platform}:FriendMessage:{user}"
        )
        self.message_obj = SimpleNamespace(raw_message={"sender": {"role": role}})
        self.admin = admin
        self.stopped = False
        self.bot = None

    def get_sender_id(self):
        return self.user

    def get_group_id(self):
        return self.group

    def get_platform_id(self):
        return self.platform

    def get_platform_name(self):
        return "aiocqhttp"

    def is_admin(self):
        return self.admin

    def stop_event(self):
        self.stopped = True

    def plain_result(self, text):
        return text

    def chain_result(self, chain):
        return chain
