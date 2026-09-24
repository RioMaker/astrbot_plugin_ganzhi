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
HERO = "#273E3B"
CREAM = "#EBDDB5"
GREEN = "#3E725E"
RED = "#A55447"
RELATION_COLORS = {"生": "#A7D4B6", "克": "#F2B4A1", "同气": "#BECBC5"}


def card_content(report: dict) -> dict:
    """Keep the public card concise; the full evidence remains in agent_payload."""
    cal = report["calendar"]
    flow = report["day_flow"]
    paths = flow["generation_paths"][:2]
    overview = flow["dominant"][0] + "气较显"
    overview += " · " + ("、".join(paths) if paths else "相生承接偏弱")
    instant = datetime.fromisoformat(cal["instant"])
    personal = report["personal"]
    return {
        "title": "干支日报" if report["ten_masters"] else "干支",
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
        "personal": {
            "label": f"{personal['day_pillar']} · {personal['master']}{personal['element']}日主",
            "today": personal["day_advice"],
            "hour": personal["hour_advice"],
        }
        if personal
        else None,
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
        f"{view['title']} · {view['date']} {view['time']}",
        "  ".join(value + label for label, value in view["pillars"]),
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
        lines.append(p["label"])
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
        offset = 250
        height = (1100 if view["daily"] else 790 if view["personal"] else 490) + offset
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

        def arrow(start, end, relation):
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
            if dx == 0:
                text(relation["kind"], start[0] + 13, (start[1] + end[1]) / 2 - 9, 18, color)
            else:
                text(relation["kind"], (start[0] + end[0]) / 2, start[1] - 28, 18, color, "center")

        # One restrained red mark gives the calendar an identity without ornament.
        draw.rounded_rectangle((40, 38, 48, 68), radius=3, fill=RED)
        text(view["title"], 62, 36, 28)
        text(view["date"], 920, 36, 28, align="right")
        text(view["lunar"], 40, 89, 22, MUTED)
        text(view["time"], 920, 89, 22, MUTED, "right")

        draw.rounded_rectangle((40, 140, 920, 345 + offset), radius=24, fill=HERO)
        graph = view["graph"]
        text("干", 65, 226, 18, "#BECBC5")
        text("支", 65, 363, 18, "#BECBC5")
        for index, column in enumerate(graph["columns"]):
            center = 150 + index * 220
            color = CREAM if column["label"] == "日" else WHITE
            text(column["label"], center, 166, 23, color, "center")
            text(column["stem"], center, 207, 62, color, "center")
            text(column["branch"], center, 347, 62, color, "center")
            arrow((center, 290), (center, 325), graph["vertical_edges"][index])
            text("藏干", center, 427, 17, "#BECBC5", "center")
            hidden = column["hidden"]
            left = center - (len(hidden) * 56 + (len(hidden) - 1) * 5) / 2
            for number, item in enumerate(hidden):
                x = left + number * 61
                draw.rounded_rectangle((x, 455, x + 56, 494), radius=7, fill="#3D5350")
                text(
                    item["stem"] + item["element"],
                    x + 28,
                    464,
                    19,
                    CREAM if number == 0 else WHITE,
                    "center",
                )
            if index < 3:
                arrow((center + 47, 243), (center + 173, 243), graph["stem_edges"][index])
                arrow((center + 47, 380), (center + 173, 380), graph["branch_edges"][index])
        text("横向看相邻柱 · 纵向看干支本气 · 藏干本气在前", 66, 519, 17, "#BECBC5")
        if graph["combinations"]:
            text(graph["combinations"], 66, 554, 18, CREAM, max_width=826)

        text("五行", 48, 378 + offset, 23, MUTED)
        text(view["overview"], 126, 377 + offset, 26, INK, max_width=780)

        if view["personal"]:
            p = view["personal"]
            text(p["label"], 48, 439 + offset, 22, MUTED)
            for index, (label, advice) in enumerate(
                (("今日", p["today"]), ("此刻 · " + view["hour_range"], p["hour"]))
            ):
                x = 40 + index * 450
                draw.rounded_rectangle(
                    (x, 480 + offset, x + 430, 720 + offset), radius=22, fill=WHITE
                )
                text(label, x + 26, 505 + offset, 21, MUTED, max_width=380)
                text(advice["theme"], x + 26, 550 + offset, 31, max_width=378)
                text("宜", x + 26, 613 + offset, 24, GREEN)
                text(advice["yi"][0], x + 71, 613 + offset, 25, max_width=332)
                text("忌", x + 26, 659 + offset, 24, RED)
                text(advice["ji"][0], x + 71, 659 + offset, 25, max_width=332)
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
