"""Compact offline calendar cards with a shared, minimal presentation model."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
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
        height = 1100 if view["daily"] else 790 if view["personal"] else 490
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

        # One restrained red mark gives the calendar an identity without ornament.
        draw.rounded_rectangle((40, 38, 48, 68), radius=3, fill=RED)
        text(view["title"], 62, 36, 28)
        text(view["date"], 920, 36, 28, align="right")
        text(view["lunar"], 40, 89, 22, MUTED)
        text(view["time"], 920, 89, 22, MUTED, "right")

        draw.rounded_rectangle((40, 140, 920, 345), radius=24, fill=HERO)
        for index, (label, pillar) in enumerate(view["pillars"]):
            center = 150 + index * 220
            color = CREAM if label == "日" else WHITE
            text(label, center, 173, 23, color, "center")
            text(pillar, center, 224, 66, color, "center", 196)
            if index < 3:
                draw.line((260 + index * 220, 192, 260 + index * 220, 296), fill="#4B5E59")

        text("五行", 48, 378, 23, MUTED)
        text(view["overview"], 126, 377, 26, INK, max_width=780)

        if view["personal"]:
            p = view["personal"]
            text(p["label"], 48, 439, 22, MUTED)
            for index, (label, advice) in enumerate(
                (("今日", p["today"]), ("此刻 · " + view["hour_range"], p["hour"]))
            ):
                x = 40 + index * 450
                draw.rounded_rectangle((x, 480, x + 430, 720), radius=22, fill=WHITE)
                text(label, x + 26, 505, 21, MUTED, max_width=380)
                text(advice["theme"], x + 26, 550, 31, max_width=378)
                text("宜", x + 26, 613, 24, GREEN)
                text(advice["yi"][0], x + 71, 613, 25, max_width=332)
                text("忌", x + 26, 659, 24, RED)
                text(advice["ji"][0], x + 71, 659, 25, max_width=332)
        elif view["daily"]:
            draw.rounded_rectangle((40, 437, 920, 1032), radius=22, fill=WHITE)
            for title, x in (("日主", 64), ("今日主题", 177), ("宜", 495), ("忌", 704)):
                text(title, x, 463, 21, MUTED)
            rule(501)
            for index, item in enumerate(view["daily"]):
                y = 520 + index * 50
                text(item["master"], 64, y, 26)
                text(item["theme"], 177, y + 2, 23, max_width=294)
                text(item["yi"], 495, y + 2, 23, GREEN, max_width=188)
                text(item["ji"], 704, y + 2, 23, RED, max_width=188)
        else:
            text(view["hour_range"], 48, 432, 21, MUTED)

        text(view["footer"], 912, height - 37, 18, MUTED, "right")
        result = BytesIO()
        canvas.save(result, "PNG", optimize=True)
        return result.getvalue()
