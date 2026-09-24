"""Create real rendered sample cards without an AstrBot instance."""

import json
import sys
from datetime import datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_ganzhi.calendar_core import BEIJING, parse_profile, snapshot  # noqa: E402
from astrbot_plugin_ganzhi.engine import build_report  # noqa: E402
from astrbot_plugin_ganzhi.renderer import Renderer  # noqa: E402

out = ROOT / ".dev" / "previews"
out.mkdir(parents=True, exist_ok=True)
renderer = Renderer()
examples = []
for name, command, profile, daily in (
    ("public", "/干支（未绑定）", None, False),
    ("personal", "/干支 辛巳；或绑定辛巳后 /干支", parse_profile("辛巳"), False),
    ("birthday", "/干支 20010319；或绑定该阳历生日后 /干支", parse_profile("20010319"), False),
    ("stem", "/干支 甲；或绑定甲日主后 /干支", parse_profile("甲"), False),
    ("daily", "/干支日报 开 → 每日 08:00 推送", None, True),
):
    cal = snapshot(datetime(2026, 9, 24, 8 if daily else 14, tzinfo=BEIJING))
    path = out / f"{name}.png"
    report = build_report(cal, profile, daily)
    path.write_bytes(renderer.render(report))
    examples.append({"command": command, "image": path.name, "instant": cal.instant})
    print(path)
    if name == "personal":
        data = {
            "source": "lunar-python 1.4.8 + ganzhi 本地规则引擎；固定时间的真实计算结果",
            "example_profile": "辛巳（演示输入，不表示当前用户已绑定）",
            "calendar": report["calendar"],
            "pillars": report["pillar_graph"]["columns"],
            "day_overview": report["day_flow"]["display_summary"],
            "current_branch_relations": report["current_flow"]["branch_relations"],
            "personal": report["personal"],
        }
        (out / "personal-data.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

cards = "\n".join(
    f"<section><h2>{escape(item['command'])}</h2>"
    f'<a href="{item["image"]}"><img src="{item["image"]}" '
    f'alt="{escape(item["command"])}" loading="lazy"></a></section>'
    for item in examples
)
(out / "index.html").write_text(
    '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1">'
    "<title>干支 · 指令图片一览</title><style>"
    "body{margin:0;background:#091722;color:#ecf2f5;font:16px/1.7 system-ui,sans-serif}"
    "header,main{max-width:1440px;margin:auto;padding:24px}h1{margin:0;font-size:28px}"
    "p{margin:8px 0;color:#9aaebd}main{display:grid;grid-template-columns:"
    "repeat(auto-fit,minmax(min(100%,420px),1fr));gap:28px;padding-top:0}"
    "section{min-width:0}h2{font-size:18px;min-height:62px;margin:0 0 12px}"
    "img{display:block;width:100%;border-radius:14px;border:1px solid #2b4153}"
    "</style><header><h1>干支 · 指令图片一览</h1>"
    "<p>同一渲染器实算：2026-09-24 北京时间，普通查询 14:00，日报 08:00。"
    "示例资料不代表用户绑定。</p>"
    "<p>/干支纪年法、/干支纪时法与/干支等价。Agent 默认也发送对应图片。"
    "同一资料绑定后查询与临时输入的图片相同。</p>"
    "<p>help、绑定、我的、解绑、日报开/关/状态返回文字；开启日报只确认订阅，"
    "到设定时间才推送日报图。点击图片可查看原尺寸。</p></header><main>"
    + cards
    + "</main></html>\n",
    encoding="utf-8",
)
print(out / "index.html")
