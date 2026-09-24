"""Offline Ganzhi cards with a dark celestial theme and explicit personal scope."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from math import atan2, cos, sin
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps

WIDTH = 960
FONT_PATH = Path(__file__).parent / "assets" / "fonts" / "GanzhiSans.otf"
INK = "#ECF2F5"
MUTED = "#9AAEBD"
LINE = "#2B4153"
PANEL = "#101F30"
GREEN = "#74E3BF"
RED = "#FF9D90"
GOLD = "#DFC895"
RELATION_COLORS = {"生": GREEN, "克": RED, "同气": "#A0B5C9"}
ELEMENT_COLORS = {
    "木": "#74E3BF",
    "火": "#FF9D90",
    "土": "#E6BF7C",
    "金": "#EAE3CB",
    "水": "#91BFFF",
}


def card_content(report: dict) -> dict:
    """Keep the public card concise; the full evidence remains in agent_payload."""
    cal = report["calendar"]
    flow = report["day_flow"]
    overview = flow["display_summary"]
    instant = datetime.fromisoformat(cal["instant"])
    personal = report["personal"]
    identity = None
    if personal:
        master = personal["master"] + personal["element"] + "日主"
        identity = {
            "glyphs": personal["day_pillar"]
            if len(personal["day_pillar"]) == 2
            else personal["master"] + personal["element"],
            "unit": "日柱" if len(personal["day_pillar"]) == 2 else "日主",
            "element": personal["element"],
            "label": personal["day_pillar"] + "日柱"
            if len(personal["day_pillar"]) == 2
            else master,
            "master": master,
            "source": {
                "birthday": "阳历生日换算",
                "pillar": "指定日柱",
                "stem": "仅提供日干",
            }[personal["source"]],
            "scope": "以下宜忌仅针对该日主",
            "today": personal["day_advice"],
            "hour": personal["hour_advice"],
        }
    return {
        "title": identity["label"] if identity else "干支日报" if report["ten_masters"] else "干支",
        "badge": "个人日运" if identity else "十日主参考" if report["ten_masters"] else "公共干支",
        "date": instant.strftime("%Y.%m.%d"),
        "time": f"{instant.hour:02}时 · 北京时间",
        "lunar": "农历" + cal["lunar_date"],
        "pillars": [
            ("年", cal["year"]),
            ("月", cal["month"]),
            ("日", cal["day"]),
            ("时", cal["hour"]),
        ],
        "hour_range": cal["hour_range"],
        "overview": overview,
        "graph": report["pillar_graph"],
        "branch_annotations": [
            " · ".join(
                r["kind"]
                for r in report["current_flow"]["branch_relations"]
                if r["indices"] == [index, index + 1]
            )
            for index in range(3)
        ],
        "personal": identity,
        "daily": [
            {
                "master": p["master"] + p["element"],
                "theme": p["day_advice"]["theme"],
                "yi": p["day_advice"]["yi"][0],
                "ji": p["day_advice"]["ji"][0],
            }
            for p in report["ten_masters"]
        ],
        "footer": "日常参考" + (" · 子初换日" if cal["boundary"] == "zi" else ""),
    }


def compact_text(report: dict) -> str:
    """The image fallback follows the same reduced information hierarchy."""
    view = card_content(report)
    lines = [
        f"{view['title']} · {view['badge']} · {view['date']} {view['time']}",
        "当前四柱：" + "  ".join(value + label for label, value in view["pillars"]),
        view["hour_range"],
        view["overview"],
    ]
    for column in view["graph"]["columns"]:
        hidden = "、".join(item["stem"] + item["element"] for item in column["hidden"])
        lines.append(f"{column['label']}柱 {column['stem']}{column['branch']} · 藏干 {hidden}")
    if view["graph"]["combinations"]:
        lines.append(view["graph"]["combinations"])
    if view["personal"]:
        p = view["personal"]
        lines.append(f"分析对象：{p['label']} · {p['master']}（{p['source']}）\n{p['scope']}")
        for label, advice in (("今日", p["today"]), ("此刻", p["hour"])):
            lines.append(
                f"{label} · {advice['theme']}\n宜 {advice['yi'][0]}  /  忌 {advice['ji'][0]}"
            )
    for p in view["daily"]:
        lines.append(f"{p['master']} · {p['theme']}；宜 {p['yi']} / 忌 {p['ji']}")
    lines.append(view["footer"])
    return "\n".join(lines)


class Renderer:
    def __init__(self, font_path: str = ""):
        self.font_path = Path(font_path) if font_path else FONT_PATH
        ImageFont.truetype(str(self.font_path), 28)

    def render(self, report: dict) -> bytes:
        view = card_content(report)
        height = 1500 if view["daily"] else 1240 if view["personal"] else 900
        gradient = Image.linear_gradient("L").resize((WIDTH, height))
        canvas = ImageOps.colorize(gradient, "#081722", "#111426").convert("RGBA")
        atmosphere = Image.new("RGBA", canvas.size)
        haze = ImageDraw.Draw(atmosphere)
        haze.ellipse((-240, -220, 580, 480), fill=(33, 118, 111, 48))
        haze.ellipse((620, 100, 1170, 850), fill=(69, 93, 159, 35))
        haze.ellipse((80, height - 220, 880, height + 320), fill=(51, 75, 114, 32))
        canvas.alpha_composite(atmosphere.filter(ImageFilter.GaussianBlur(90)))
        draw = ImageDraw.Draw(canvas)
        fonts, halos = {}, {}

        def font(size):
            if size not in fonts:
                fonts[size] = ImageFont.truetype(str(self.font_path), size)
            return fonts[size]

        def text(value, x, y, size=26, color=INK, align="left", max_width=None):
            while max_width and draw.textlength(value, font=font(size)) > max_width and size > 16:
                size -= 1
            anchor = {"left": "lt", "center": "mt", "right": "rt"}[align]
            draw.text((x, y), value, font=font(size), fill=color, anchor=anchor)

        def tint(color, amount=0.2, base=PANEL):
            a, b = ImageColor.getrgb(color), ImageColor.getrgb(base)
            return tuple(round(x * amount + y * (1 - amount)) for x, y in zip(a, b))

        def panel(box, fill=PANEL, outline=LINE, radius=22):
            draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=1)

        def pill(value, x, y, color=GREEN, size=19):
            width = draw.textlength(value, font=font(size)) + 28
            panel((x, y, x + width, y + 34), tint(color, 0.12), tint(color, 0.4), 9)
            text(value, x + 14, y + 7, size, color)
            return width

        def glow(center, color):
            if color not in halos:
                halo = Image.new("RGBA", (132, 132))
                ImageDraw.Draw(halo).ellipse(
                    (26, 26, 106, 106), fill=(*ImageColor.getrgb(color), 36)
                )
                halos[color] = halo.filter(ImageFilter.GaussianBlur(20))
            canvas.alpha_composite(halos[color], (int(center[0] - 66), int(center[1] - 66)))

        def node(glyph, element, x, y):
            color = ELEMENT_COLORS[element]
            glow((x, y), color)
            draw.ellipse((x - 43, y - 43, x + 43, y + 43), outline=tint(color, 0.28), width=1)
            draw.arc((x - 48, y - 48, x + 48, y + 48), 215, 280, fill=tint(color, 0.75), width=2)
            draw.arc((x - 48, y - 48, x + 48, y + 48), 35, 75, fill=tint(color, 0.55), width=2)
            text(glyph, x, y - 35, 65, color, "center")

        def arrow(start, end, relation, label=True, annotation=""):
            color = RELATION_COLORS[relation["kind"]]
            if relation["direction"] == -1:
                start, end = end, start
            dx, dy = end[0] - start[0], end[1] - start[1]
            length = (dx * dx + dy * dy) ** 0.5
            if relation["direction"] == 0:
                for step in range(0, int(length), 12):
                    a, b = step / length, min(step + 5, length) / length
                    draw.line(
                        (
                            start[0] + a * dx,
                            start[1] + a * dy,
                            start[0] + b * dx,
                            start[1] + b * dy,
                        ),
                        fill=color,
                        width=2,
                    )
            else:
                draw.line((start, end), fill=tint(color, 0.14), width=6)
                draw.line((start, end), fill=color, width=2)

            def head(tail, tip):
                angle = atan2(tip[1] - tail[1], tip[0] - tail[0])
                draw.polygon(
                    (
                        tip,
                        (tip[0] - 8 * cos(angle - 0.45), tip[1] - 8 * sin(angle - 0.45)),
                        (tip[0] - 8 * cos(angle + 0.45), tip[1] - 8 * sin(angle + 0.45)),
                    ),
                    fill=color,
                )

            head(start, end)
            if relation["direction"] == 0:
                head(end, start)
            if label:
                if dx == 0:
                    text(relation["kind"], start[0] + 15, (start[1] + end[1]) / 2 - 9, 18, color)
                else:
                    mid = (start[0] + end[0]) / 2
                    text(relation["kind"], mid, start[1] - 27, 18, color, "center")
                    if annotation:
                        text(annotation, mid, start[1] + 14, 17, MUTED, "center")

        # Fixed decorative marks carry no astronomical or strength data.
        for x, y, r in (
            (420, 67, 2),
            (590, 129, 1),
            (541, 39, 1),
            (906, 197, 2),
            (18, 416, 1),
            (936, 687, 2),
            (24, 778, 1),
        ):
            draw.ellipse((x - r, y - r, x + r, y + r), fill="#567084")
        for radius in (92, 116, 134):
            draw.arc(
                (760 - radius, 129 - radius, 760 + radius, 129 + radius),
                215,
                330,
                fill="#29404F",
                width=1,
            )
            draw.arc(
                (760 - radius, 129 - radius, 760 + radius, 129 + radius),
                30,
                118,
                fill="#203746",
                width=1,
            )
        draw.polygon(((48, 37), (56, 45), (48, 53), (40, 45)), outline=GREEN)
        draw.line((48, 40, 48, 50), fill=GREEN, width=1)
        text("干支  /  GANZHI", 70, 36, 19, GREEN)
        text(view["badge"], 908, 36, 20, GOLD, "right")

        personal = view["personal"]
        if personal:
            color = ELEMENT_COLORS[personal["element"]]
            text(personal["glyphs"], 43, 82, 82, color)
            pill(personal["unit"], 229, 122, color, 20)
            text(personal["master"] + " · " + personal["source"], 48, 183, 22, MUTED)
        else:
            text("干支日报" if view["daily"] else "干支纪时", 44, 93, 56)
            text(
                "公共环境 · 十日主概览" if view["daily"] else "此刻的四柱与五行", 48, 177, 22, MUTED
            )
        text(view["date"], 908, 101, 32, INK, "right")
        text(view["lunar"], 908, 153, 20, MUTED, "right")
        text(view["time"], 908, 183, 20, GREEN, "right")

        graph = view["graph"]
        panel((40, 230, 920, 718))
        draw.line((65, 230, 340, 230), fill="#54877E", width=2)
        text("当前四柱", 64, 249, 23)
        text("天干在上 · 地支在下", 896, 253, 18, MUTED, "right")
        # All four columns use the same scale; only today's column is highlighted.
        panel((499, 288, 681, 626), "#162B39", "#365466", 17)
        text("干", 66, 363, 17, MUTED)
        text("支", 66, 496, 17, MUTED)
        for index, column in enumerate(graph["columns"]):
            center = 154 + index * 218
            text(column["label"] + "柱", center, 299, 20, GREEN if index == 2 else MUTED, "center")
            node(column["stem"], column["stem_element"], center, 373)
            node(column["branch"], column["branch_element"], center, 506)
            arrow((center, 424), (center, 453), graph["vertical_edges"][index])
            text("藏干", center, 559, 16, MUTED, "center")
            hidden = column["hidden"]
            left = center - (len(hidden) * 53 + (len(hidden) - 1) * 5) / 2
            for number, item in enumerate(hidden):
                x = left + number * 58
                color = ELEMENT_COLORS[item["element"]]
                panel(
                    (x, 587, x + 53, 619),
                    color if number == 0 else PANEL,
                    color if number == 0 else tint(color, 0.5),
                    6,
                )
                text(
                    item["stem"] + item["element"],
                    x + 26.5,
                    594,
                    18,
                    "#102032" if number == 0 else color,
                    "center",
                )
            if index < 3:
                arrow((center + 54, 373), (center + 164, 373), graph["stem_edges"][index])
                arrow(
                    (center + 54, 506),
                    (center + 164, 506),
                    graph["branch_edges"][index],
                    annotation=view["branch_annotations"][index],
                )

        draw.line((64, 640, 896, 640), fill=LINE, width=1)
        text("图例", 65, 660, 17, MUTED)
        for kind, x, direction in (("生", 142, 1), ("克", 302, 1), ("同气", 462, 0)):
            arrow((x, 670), (x + 48, 670), {"kind": kind, "direction": direction}, label=False)
            text(kind, x + 62, 660, 19, RELATION_COLORS[kind])
        text("合 · 未定化", 730, 660, 19, GOLD)
        text("横向相邻 / 纵向本气 / 线下标支关系 / 藏干实底为本气、描边为兼气", 65, 694, 16, MUTED)

        panel((40, 738, 920, 834), "#122332", "#2D4958", 18)
        draw.rounded_rectangle((62, 758, 65, 783), radius=1, fill=GREEN)
        text("五行流通", 80, 759, 21, GREEN)
        text(view["overview"], 198, 757, 25, INK, max_width=695)
        text(
            graph["combinations"] or "干支关系 · 暂无需额外标注的合冲刑害",
            64,
            802,
            18,
            MUTED,
            max_width=830,
        )

        if personal:
            panel((40, 854, 920, 912), "#15322F", "#36675A", 15)
            draw.polygon(((66, 876), (73, 883), (66, 890), (59, 883)), fill=GREEN)
            text(personal["label"] + " · 个人宜忌", 90, 872, 22, INK)
            text(personal["scope"], 894, 875, 20, GREEN, "right")
            for index, (label, advice) in enumerate(
                (("今日", personal["today"]), (view["hour_range"], personal["hour"]))
            ):
                x = 40 + index * 450
                accent = GREEN if index == 0 else ELEMENT_COLORS["水"]
                panel((x, 928, x + 430, 1182), "#132434", "#314B5C", 22)
                draw.line((x + 25, 928, x + 130, 928), fill=accent, width=2)
                draw.ellipse((x + 26, 952, x + 33, 959), fill=accent)
                text(label, x + 44, 946, 20, accent, max_width=361)
                text(advice["theme"], x + 26, 987, 30, INK, max_width=378)
                draw.line((x + 26, 1036, x + 404, 1036), fill=LINE, width=1)
                for mark, values, y, color in (
                    ("宜", advice["yi"], 1056, GREEN),
                    ("忌", advice["ji"], 1112, RED),
                ):
                    panel((x + 25, y, x + 61, y + 36), tint(color, 0.13), tint(color, 0.28), 8)
                    text(mark, x + 43, y + 7, 21, color, "center")
                    text(values[0], x + 79, y + 5, 25, INK, max_width=323)
        elif view["daily"]:
            panel((40, 854, 920, 1438), "#122231", "#314B5C", 22)
            text("十日主 · 今日简览", 64, 876, 25)
            text("按各自日主查看宜忌", 895, 880, 19, GOLD, "right")
            for title, x in (("日主", 76), ("今日主题", 185), ("宜", 510), ("忌", 710)):
                text(title, x, 924, 19, MUTED)
            draw.line((64, 955, 896, 955), fill=LINE, width=1)
            for index, item in enumerate(view["daily"]):
                y = 964 + index * 46
                if index % 2 == 0:
                    draw.rounded_rectangle((57, y - 2, 903, y + 40), radius=6, fill="#192D3D")
                color = ELEMENT_COLORS[item["master"][1]]
                draw.rounded_rectangle((64, y + 10, 67, y + 26), radius=1, fill=color)
                text(item["master"], 78, y + 5, 24, color)
                text(item["theme"], 185, y + 6, 22, INK, max_width=304)
                text(item["yi"], 510, y + 6, 22, GREEN, max_width=182)
                text(item["ji"], 710, y + 6, 22, RED, max_width=183)

        text(
            "GANZHI  /  "
            + (view["hour_range"] if not personal and not view["daily"] else "干支纪时"),
            48,
            height - 35,
            16,
            MUTED,
        )
        text(view["footer"], 912, height - 35, 16, MUTED, "right")
        result = BytesIO()
        canvas.convert("RGB").save(result, "PNG", optimize=True)
        return result.getvalue()
