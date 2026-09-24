from datetime import datetime
from io import BytesIO

from astrbot_plugin_ganzhi.calendar_core import BEIJING, parse_profile, snapshot
from astrbot_plugin_ganzhi.engine import build_report
from astrbot_plugin_ganzhi.renderer import FONT_PATH, Renderer, compact_text
from fontTools.ttLib import TTFont
from PIL import Image


def test_png_variants_and_character_coverage():
    renderer = Renderer()
    cmap = TTFont(FONT_PATH).getBestCmap()
    cal = snapshot(datetime(2026, 9, 24, 8, tzinfo=BEIJING))
    for profile, daily in (
        (None, False),
        (parse_profile("辛巳"), False),
        (parse_profile("丁未"), False),
        (None, True),
    ):
        report = build_report(cal, profile, daily)
        png = renderer.render(report)
        image = Image.open(BytesIO(png))
        assert image.width == 960
        assert image.height == (1100 if daily else 790 if profile else 490)
        image.verify()
        assert {ord(x) for x in compact_text(report) if not x.isspace()} <= set(cmap)
