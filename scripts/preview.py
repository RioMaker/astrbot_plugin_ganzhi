"""Create real rendered sample cards without an AstrBot instance."""

import json
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
cal = snapshot(datetime(2026, 9, 24, 14, tzinfo=BEIJING))
for name, profile, daily in (
    ("public", None, False),
    ("personal", parse_profile("辛巳"), False),
    ("birthday", parse_profile("20010319"), False),
    ("daily", None, True),
):
    path = out / f"{name}.png"
    report = build_report(cal, profile, daily)
    path.write_bytes(renderer.render(report))
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
