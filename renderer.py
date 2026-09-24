"""Compact offline calendar cards with a shared, minimal presentation model."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from math import atan2, cos, sin
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH = 960
FONT_PATH = Path(__file__).parent / "assets" / "fonts" / "GanzhiSans.otf"
PAPER = "#F4F3EF"
WHITE = "#FFFFFF"
INK = "#252B2D"
MUTED = "#717675"
LINE = "#E6E8E3"
GREEN = "#3E725E"
RED = "#A55447"
RELATION_COLORS = {"生": "#348168", "克": "#B75D4B", "同气": "#68756E"}
ELEMENT_COLORS = {
    "木": "#3E7860",
    "火": "#B05B48",
    "土": "#96713A",
    "金": "#647985",
    "水": "#426A91",
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
        offset = 340
        height = (1100 if view["daily"] else 850 if view["personal"] else 490) + offset
        canvas = Image.new("RGB", (WIDTH, height), PAPER)
        draw = ImageDraw.Draw(canvas)
        fonts = {}

        def font(size):
            if size not in fonts:
                fonts[size] = ImageFont.truetype(str(self.font_path), size)
            return fonts[size]

        def text(value, x, y, size=26, color=INK, align="left", max_width=None):
            # Fit finite rule vocabulary and custom fonts without cutting text.
            while max_width and draw.textlength(value, font=font(size)) > max_width and size > 18:
                size -= 1
            anchor = {"left": "lt", "center": "mt", "right": "rt"}[align]
            draw.text((x, y), value, font=font(size), fill=color, anchor=anchor)

        def rule(y, left=60, right=900):
            draw.line((left, y, right, y), fill=LINE, width=2)

        def arrow(start, end, relation, label=True, annotation=""):
            color = RELATION_COLORS[relation["kind"]]
            if relation["direction"] == -1:
                start, end = end, start
            dx, dy = end[0] - start[0], end[1] - start[1]
            length = (dx * dx + dy * dy) ** 0.5
            if relation["direction"] == 0:
                for step in range(0, int(length), 11):
                    a, b = step / length, min(step + 6, length) / length
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
                draw.line((start, end), fill=color, width=2)

            def head(tail, tip):
                angle = atan2(tip[1] - tail[1], tip[0] - tail[0])
                draw.polygon(
                    (
                        tip,
                        (tip[0] - 9 * cos(angle - 0.45), tip[1] - 9 * sin(angle - 0.45)),
                        (tip[0] - 9 * cos(angle + 0.45), tip[1] - 9 * sin(angle + 0.45)),
                    ),
                    fill=color,
                )

            head(start, end)
            if relation["direction"] == 0:
                head(end, start)
            if not label:
                return
            if dx == 0:
                text(relation["kind"], start[0] + 13, (start[1] + end[1]) / 2 - 9, 18, color)
            else:
                text(relation["kind"], (start[0] + end[0]) / 2, start[1] - 28, 18, color, "center")
                if annotation:
                    text(annotation, (start[0] + end[0]) / 2, start[1] + 13, 16, MUTED, "center")

        # Put the selected natal identity first, separate from the current calendar.
        accent = GREEN if view["personal"] else RED
        title_size = 40 if view["personal"] else 32
        draw.rounded_rectangle((40, 35, 48, 72), radius=3, fill=accent)
        text(view["title"], 62, 30, title_size)
        badge_x = 62 + draw.textlength(view["title"], font=font(title_size)) + 20
        badge_width = draw.textlength(view["badge"], font=font(21)) + 26
        draw.rounded_rectangle((badge_x, 34, badge_x + badge_width, 70), radius=9, fill=accent)
        text(view["badge"], badge_x + 13, 41, 21, WHITE)
        text(view["date"], 920, 36, 28, align="right")
        text("当前四柱 · " + view["lunar"], 40, 89, 22, MUTED)
        text(view["time"], 920, 89, 22, MUTED, "right")

        draw.rounded_rectangle((40, 140, 920, 520), radius=24, fill=WHITE)
        draw.rounded_rectangle((493, 155, 687, 508), radius=18, fill="#F8F5EB")
        graph = view["graph"]
        text("干", 65, 226, 18, MUTED)
        text("支", 65, 363, 18, MUTED)
        for index, column in enumerate(graph["columns"]):
            center = 150 + index * 220
            text(column["label"], center, 166, 23, INK, "center")
            text(column["stem"], center, 207, 62, ELEMENT_COLORS[column["stem_element"]], "center")
            text(
                column["branch"],
                center,
                347,
                62,
                ELEMENT_COLORS[column["branch_element"]],
                "center",
            )
            arrow((center, 290), (center, 325), graph["vertical_edges"][index])
            text("藏干", center, 427, 17, MUTED, "center")
            hidden = column["hidden"]
            left = center - (len(hidden) * 56 + (len(hidden) - 1) * 5) / 2
            for number, item in enumerate(hidden):
                x = left + number * 61
                color = ELEMENT_COLORS[item["element"]]
                draw.rounded_rectangle(
                    (x, 455, x + 56, 494),
                    radius=7,
                    fill=color if number == 0 else WHITE,
                    outline=color,
                    width=1,
                )
                text(
                    item["stem"] + item["element"],
                    x + 28,
                    464,
                    19,
                    WHITE if number == 0 else color,
                    "center",
                )
            if index < 3:
                arrow((center + 47, 243), (center + 173, 243), graph["stem_edges"][index])
                arrow(
                    (center + 47, 380),
                    (center + 173, 380),
                    graph["branch_edges"][index],
                    annotation=view["branch_annotations"][index],
                )
        # Legend symbols use the very same arrow renderer as the data diagram.
        draw.rounded_rectangle((40, 534, 920, 630), radius=18, fill=WHITE)
        text("图例", 64, 553, 19, MUTED)
        for kind, x, direction in (("生", 140, 1), ("克", 292, 1), ("同气", 444, 0)):
            arrow((x, 565), (x + 55, 565), {"kind": kind, "direction": direction}, label=False)
            text(kind, x + 68, 553, 21, RELATION_COLORS[kind])
        draw.rounded_rectangle((650, 547, 692, 578), radius=7, outline="#96713A", width=1)
        text("合", 671, 553, 19, "#96713A", "center")
        text("未定化", 704, 553, 21, "#96713A")
        text("横向相邻 · 纵向本气 · 线下标支关系 · 藏干实底为本气，描边为兼气", 64, 598, 17, MUTED)
        if graph["combinations"]:
            text("关系", 48, 660, 21, MUTED)
            text(graph["combinations"], 126, 660, 19, INK, max_width=780)

        text("五行", 48, 378 + offset, 23, MUTED)
        text(view["overview"], 126, 377 + offset, 26, INK, max_width=780)

        if view["personal"]:
            p = view["personal"]
            draw.rounded_rectangle((40, 773, 920, 870), radius=22, fill="#294D40")
            text("分析对象", 66, 790, 18, "#C4D8CD")
            text(p["label"], 66, 821, 34, WHITE)
            draw.line((298, 795, 298, 860), fill="#597568", width=1)
            text(p["master"] + " · " + p["source"], 326, 794, 22, "#C4D8CD")
            text(p["scope"], 326, 834, 26, WHITE)
            for index, (label, advice) in enumerate(
                (("个人 · 今日", p["today"]), ("个人 · " + view["hour_range"], p["hour"]))
            ):
                x = 40 + index * 450
                draw.rounded_rectangle(
                    (x, 540 + offset, x + 430, 780 + offset), radius=22, fill=WHITE
                )
                text(label, x + 26, 565 + offset, 21, GREEN, max_width=380)
                text(advice["theme"], x + 26, 610 + offset, 31, max_width=378)
                text("宜", x + 26, 673 + offset, 24, GREEN)
                text(advice["yi"][0], x + 71, 673 + offset, 25, max_width=332)
                text("忌", x + 26, 719 + offset, 24, RED)
                text(advice["ji"][0], x + 71, 719 + offset, 25, max_width=332)
        elif view["daily"]:
            draw.rounded_rectangle((40, 437 + offset, 920, 1032 + offset), radius=22, fill=WHITE)
            for title, x in (("日主", 64), ("今日主题", 177), ("宜", 495), ("忌", 704)):
                text(title, x, 463 + offset, 21, MUTED)
            rule(501 + offset)
            for index, item in enumerate(view["daily"]):
                y = 520 + index * 50 + offset
                text(item["master"], 64, y, 26)
                text(item["theme"], 177, y + 2, 23, max_width=294)
                text(item["yi"], 495, y + 2, 23, GREEN, max_width=188)
                text(item["ji"], 704, y + 2, 23, RED, max_width=188)
        else:
            text(view["hour_range"], 48, 432 + offset, 21, MUTED)

        text(view["footer"], 912, height - 37, 18, MUTED, "right")
        result = BytesIO()
        canvas.save(result, "PNG", optimize=True)
        return result.getvalue()
