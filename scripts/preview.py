"""Create real rendered sample cards without an AstrBot instance."""

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_ganzhi.calendar_core import BEIJING, parse_profile, snapshot  # noqa: E402
from astrbot_plugin_ganzhi.engine import build_report  # noqa: E402
from astrbot_plugin_ganzhi.renderer import Renderer  # noqa: E402

out = ROOT / ".dev" / "previews"
out.mkdir(parents=True, exist_ok=True)
renderer = Renderer()
cal = snapshot(datetime(2026, 9, 24, 8, tzinfo=BEIJING))
for name, profile, daily in (
    ("public", None, False),
    ("personal", parse_profile("辛巳"), False),
    ("birthday", parse_profile("20010319"), False),
    ("daily", None, True),
):
    path = out / f"{name}.png"
    path.write_bytes(renderer.render(build_report(cal, profile, daily)))
    print(path)
