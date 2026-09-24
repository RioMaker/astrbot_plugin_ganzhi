"""Offline PNG card; measured Chinese wrapping, no network or persistent image cache."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .engine import ELEMENTS, STEM_ELEMENT

BG = "#F5F1E8"
INK = "#262D29"
MUTED = "#646C64"
JADE = "#285D4C"
RED = "#9A4838"
COLORS = {"木": "#397C60", "火": "#AD5540", "土": "#90723D", "金": "#7A7B80", "水": "#436D92"}
WIDTH = 1120
FONT_PATH = Path(__file__).parent / "assets" / "fonts" / "GanzhiSans.otf"


class Renderer:
    def __init__(self, font_path: str = ""):
        self.font_path = Path(font_path) if font_path else FONT_PATH
        # Fail visibly at construction; callers retain a text fallback.
        ImageFont.truetype(str(self.font_path), 28)

    def render(self, report: dict) -> bytes:
        fonts = {
            size: ImageFont.truetype(str(self.font_path), size)
            for size in (22, 25, 28, 30, 34, 48, 68)
        }
        # Layout is measured first, then drawn to the exact height.
        probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        ops = []
        y = 44

        def text(value, x, top, size=28, color=INK):
            ops.append(("text", (x, top), value, size, color))

        def para(value, size=28, color=INK, x=52, width=1016, gap=10):
            nonlocal y
            for block in str(value).split("\n"):
                line = ""
                for char in block:
                    if line and probe.textlength(line + char, font=fonts[size]) > width:
                        text(line, x, y, size, color)
                        y += int(size * 1.55)
                        line = char
                    else:
                        line += char
                text(line, x, y, size, color)
                y += int(size * 1.55)
            y += gap

        def section(label):
            nonlocal y
            y += 15
            ops.append(("line", (52, y, WIDTH - 52, y), "#D9DACE"))
            y += 22
            para(label, 30, JADE, gap=12)

        cal = report["calendar"]
        para("GANZHI  /  干支纪时", 22, JADE, gap=18)
        para("今日干支日报" if report["ten_masters"] else "此时 · 此日", 48, gap=8)
        para(
            f"{cal['instant'][:13].replace('T', ' ')}时  北京时间  ·  农历{cal['lunar_date']}",
            25,
            MUTED,
            gap=24,
        )
        top = y
        for i, (label, key) in enumerate(
            (("年柱", "year"), ("月柱", "month"), ("日柱", "day"), ("时柱", "hour"))
        ):
            x = 52 + i * 259
            ops.append(("rect", (x, top, x + 239, top + 192), "#FFFCF5"))
            text(label, x + 24, top + 18, 25, MUTED)
            text(cal[key], x + 24, top + 63, 68, COLORS[STEM_ELEMENT[cal[key][0]]])
            text(
                STEM_ELEMENT[cal[key][0]] + " · " + cal[key][1] + "支", x + 24, top + 154, 22, MUTED
            )
        y += 216
        boundary = "零点换日" if cal["boundary"] == "midnight" else "子初换日"
        para(f"{cal['hour_range']}  ·  立春换年 / 节气换月 / {boundary}", 22, MUTED)
        section("01  今日五行流通")
        f = report["day_flow"]
        for element in ELEMENTS:
            value = f["percent"][element]
            text(f"{element}  {f['season_states'][element]}", 52, y, 28, COLORS[element])
            ops.append(("rect", (176, y + 11, 854, y + 31), "#E1E3DA"))
            if value:
                ops.append(
                    ("rect", (176, y + 11, 176 + 678 * value / 100, y + 31), COLORS[element])
                )
            text(f"{value:4.1f}%", 901, y, 28, INK)
            y += 50
        y += 8
        para(f["summary"], 28)
        para("承接偏弱：" + ("、".join(f["weak_paths"]) or "无低于阈值的相生边"), 25, MUTED)
        para("占比表示当前环境的相对权重，用于说明依据。", 22, MUTED)
        p = report["personal"]
        if p:
            section(f"02  你的日主 · {p['master']}{p['element']}  /  {p['day_pillar']}")
            para(f"今日{p['day_god']} · {p['day_advice']['theme']}", 34)
            para(p["environment_note"], 25, MUTED)
            para("宜  " + " · ".join(p["day_advice"]["yi"]), 28, JADE)
            para("忌  " + " · ".join(p["day_advice"]["ji"]), 28, RED)
            para(
                "日支藏干：" + " / ".join(x["stem"] + "·" + x["god"] for x in p["day_hidden"]),
                25,
                MUTED,
            )
            for link in p["day_links"]:
                para(link, 25, MUTED)
            section(f"03  当前时辰 · {cal['hour_range']}")
            para(f"{p['hour_god']} · {p['hour_advice']['theme']}", 34)
            para("宜  " + " · ".join(p["hour_advice"]["yi"]), 28, JADE)
            para("忌  " + " · ".join(p["hour_advice"]["ji"]), 28, RED)
            for link in p["hour_links"]:
                para(link, 25, MUTED)
            para("仅据日主与今日环境研判，未定本命强弱与用神。", 22, MUTED)
        elif not report["ten_masters"]:
            section("02  加入你的日主")
            para("/干支 辛巳   或   /干支 20010319", 28)
            para("生日默认阳历；/干支 绑定 20010319 可保存资料。", 25, MUTED)
        if report["ten_masters"]:
            section("02  十天干日主 · 今日简览")
            for p in report["ten_masters"]:
                para(
                    f"{p['master']}{p['element']}  /  {p['day_god']} · {p['day_advice']['theme']}",
                    28,
                )
                para(
                    f"宜 {p['day_advice']['yi'][0]}   ·   忌 {p['day_advice']['ji'][0]}",
                    25,
                    MUTED,
                    gap=20,
                )
        section("日常安排参考")
        para("宜忌取自插件内置规则文档；更多依据可请 AI 解读。", 22, MUTED)
        para("传统文化参考  ·  ganzhi 0.1.0", 22, MUTED, gap=0)
        canvas = Image.new("RGB", (WIDTH, y + 44), BG)
        draw = ImageDraw.Draw(canvas)
        for op in ops:
            if op[0] == "text":
                draw.text(op[1], op[2], font=fonts[op[3]], fill=op[4])
            elif op[0] == "rect":
                draw.rectangle(op[1], fill=op[2])
            elif op[0] == "line":
                draw.line(op[1], fill=op[2], width=2)
        result = BytesIO()
        canvas.save(result, "PNG", optimize=True)
        return result.getvalue()
