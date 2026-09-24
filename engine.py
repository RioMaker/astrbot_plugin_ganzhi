"""Traceable, deliberately limited daily five-element / ten-god interpretation."""

from __future__ import annotations

import json
from pathlib import Path

from .calendar_core import STEMS, CalendarSnapshot, Profile
from .wuxing import (
    BRANCH_PAIRS,
    CONTROLS,
    ELEMENTS,
    GENERATES,
    HIDDEN,
    RULE_VERSION,
    STEM_ELEMENT,
    element_relation,
    flow,
)

ROOT = Path(__file__).resolve().parent
TEN_GODS = json.loads((ROOT / "data" / "ten_gods.json").read_text(encoding="utf-8"))
REFERENCE_TEXT = "\n\n".join(
    (ROOT / "references" / name).read_text(encoding="utf-8")
    for name in ("calendar.md", "interpretation.md", "bazi_notes.md")
)

RULE_CATALOG = json.loads((ROOT / "data" / "rule_sources.json").read_text(encoding="utf-8"))


def ten_god(master: str, other: str) -> str:
    same_polarity = STEMS.index(master) % 2 == STEMS.index(other) % 2
    own, target = STEM_ELEMENT[master], STEM_ELEMENT[other]
    if own == target:
        pair = ("比肩", "劫财")
    elif GENERATES[own] == target:
        pair = ("食神", "伤官")
    elif CONTROLS[own] == target:
        pair = ("偏财", "正财")
    elif CONTROLS[target] == own:
        pair = ("七杀", "正官")
    else:
        pair = ("偏印", "正印")
    return pair[0 if same_polarity else 1]


def branch_links(natal: str, present: str) -> list[str]:
    pair = frozenset((natal, present))
    out = []
    for kind, name, detail in (
        ("合", "六合", "适合协调，合不等于已经合化"),
        ("冲", "六冲", "安排留余地，变动处多复核"),
        ("害", "六害", "把隐含期待说清楚，减少误解"),
        ("刑", "刑", "检查相处边界；仅见刑的关系，不断定刑局或灾祸"),
    ):
        if pair in [frozenset(x) for x in BRANCH_PAIRS[kind]]:
            out.append(f"{natal}{present}{name}：{detail}")
    if natal == present:
        if natal in "辰午酉亥":
            out.append(f"{natal}{present}自刑：重复支的结构提示，不据此断吉凶")
        out.append(f"日支同为{natal}：重复议题适合回顾，不据此断吉凶")
    return out


def personal(profile: Profile, cal: CalendarSnapshot, day_flow: dict) -> dict:
    master = profile.stem
    day_god, hour_god = ten_god(master, cal.day[0]), ten_god(master, cal.hour[0])
    own = STEM_ELEMENT[master]
    relation_elements = {
        "同我": own,
        "我生": GENERATES[own],
        "我克": CONTROLS[own],
        "生我": next(x for x in ELEMENTS if GENERATES[x] == own),
        "克我": next(x for x in ELEMENTS if CONTROLS[x] == own),
    }
    relations = {
        name: {
            "element": element,
            "presence": day_flow["elements"][element]["presence"],
            "season_state": day_flow["season_states"][element],
            "evidence_ref": "day_flow.elements." + element,
        }
        for name, element in relation_elements.items()
    }
    environment_note = (
        day_flow["month"]["note"]
        + "；环境中"
        + own
        + day_flow["elements"][own]["presence"]
        + "。这是当前环境证据，不能代替本命根气或喜忌。"
    )
    return {
        # Do not return the exact birthday to the model or draw it on a group image.
        "day_pillar": profile.day_pillar,
        "source": profile.source,
        "master": master,
        "element": own,
        "season_state": day_flow["season_states"][own],
        "day_god": day_god,
        "hour_god": hour_god,
        "day_advice": TEN_GODS[day_god],
        "hour_advice": TEN_GODS[hour_god],
        "relations_evidence": relations,
        "environment_note": environment_note,
        "rule_ids": ["WX04", "WX12"],
        "day_hidden": [{"stem": x, "god": ten_god(master, x)} for x in HIDDEN[cal.day[1]]],
        "hour_hidden": [{"stem": x, "god": ten_god(master, x)} for x in HIDDEN[cal.hour[1]]],
        "day_links": branch_links(profile.day_pillar[1], cal.day[1])
        if len(profile.day_pillar) == 2
        else [],
        "hour_links": branch_links(profile.day_pillar[1], cal.hour[1])
        if len(profile.day_pillar) == 2
        else [],
        "scope": "日主与当前环境的关系；未评定本命强弱、用神或完整格局。",
    }


def build_report(
    cal: CalendarSnapshot, profile: Profile | None = None, daily: bool = False
) -> dict:
    day_pillars = [("年", cal.year), ("月", cal.month), ("日", cal.day)]
    day_flow = flow(day_pillars, cal.month[1])
    current_flow = flow([*day_pillars, ("时", cal.hour)], cal.month[1])
    report = {
        "rule_version": RULE_VERSION,
        "calendar": cal.to_dict(),
        "pillar_graph": pillar_graph(cal, current_flow),
        "current_flow": current_flow,
        "day_flow": day_flow,
        "hour_flow": flow([("时", cal.hour)], cal.month[1]),
        "personal": personal(profile, cal, day_flow) if profile else None,
        "ten_masters": [personal(Profile("stem", x, x), cal, day_flow) for x in STEMS]
        if daily
        else [],
        "scope": "传统文化日常安排参考；候选制化不是确定结论，不推断本命强弱。",
    }
    return report


def pillar_graph(cal: CalendarSnapshot, current_flow: dict | None = None) -> dict:
    """The image and Agent share the same evidence; only the image labels are shortened."""
    analysis = (
        current_flow
        if current_flow is not None
        else flow(
            [("年", cal.year), ("月", cal.month), ("日", cal.day), ("时", cal.hour)], cal.month[1]
        )
    )
    columns = [
        {
            key: c[key]
            for key in ("label", "stem", "branch", "stem_element", "branch_element", "hidden")
        }
        for c in analysis["columns"]
    ]
    pairs = list(dict.fromkeys(x["glyphs"] for x in analysis["stem_combinations"]))
    branch_notes, keys = [], set()
    for item in analysis["branch_relations"]:
        key = (frozenset(item["glyphs"]), item["kind"])
        if key not in keys:
            keys.add(key)
            branch_notes.append(item["glyphs"] + item["kind"])
    notes = []
    if pairs:
        notes.append("干合 " + "、".join(pairs) + "（未定化）")
    if branch_notes:
        notes.append(
            "支间 " + "、".join(branch_notes[:2]) + ("等" if len(branch_notes) > 2 else "")
        )
    complete = [x for x in analysis["branch_groups"] if x["complete"]]
    if complete:
        item = complete[0]
        notes.append(item["glyphs"] + item["kind"] + "齐支")
    # Fixed compact card; the full set remains in current_flow.
    caption = " · ".join(notes)
    if len(caption) > 44:
        caption = " · ".join(notes[:2])
    return {
        "columns": columns,
        "stem_edges": [
            element_relation(a["stem_element"], b["stem_element"])
            for a, b in zip(columns, columns[1:])
        ],
        "branch_edges": [
            element_relation(a["branch_element"], b["branch_element"])
            for a, b in zip(columns, columns[1:])
        ],
        "vertical_edges": [
            element_relation(c["stem_element"], c["branch_element"]) for c in columns
        ],
        "combinations": caption,
        "rule_ids": ["WX01", "WX02", "WX05", "WX08", "WX09", "WX10"],
        "scope": "横向只画相邻柱；纵向以地支本气为参照；列出全部藏干。箭头是五行基础关系，不证明制化成功。",
    }


def agent_payload(report: dict) -> str:
    return json.dumps(
        {
            "calculated": report,
            "reference_document": REFERENCE_TEXT,
            "ten_god_reference": TEN_GODS,
            "rule_catalog": RULE_CATALOG,
            "instruction": "先读 calculated 的月令、透藏与根气，再读 mechanisms、checks、issues；按 rule_ids 回查笔记和 rule_catalog。candidate 仅为候选，不能写成已制住、已通关或已合化；未评定的力量不可另编分数。生日只接受阳历，不编造本命，不改写原干支五行。",
        },
        ensure_ascii=False,
    )


def format_text(report: dict) -> str:
    cal = report["calendar"]
    lines = [
        "干支日报" if report["ten_masters"] else "干支纪时",
        f"北京时间 {cal['instant'][:13].replace('T', ' ')}时 · 农历{cal['lunar_date']}",
        f"{cal['year']}年 {cal['month']}月 {cal['day']}日 {cal['hour']}时 · {cal['hour_range']}",
        "日柱：" + ("零点换日" if cal["boundary"] == "midnight" else "子初换日"),
        report["day_flow"]["summary"],
    ]
    if report["personal"]:
        p = report["personal"]
        lines.extend(
            [
                f"你的日主 {p['master']}{p['element']}（{p['day_pillar']}）· 今日{p['day_god']}：{p['day_advice']['theme']}",
                p["environment_note"],
                "今日宜：" + "、".join(p["day_advice"]["yi"]),
                "今日忌：" + "、".join(p["day_advice"]["ji"]),
                f"当前{cal['hour_range']} · {p['hour_god']}：{p['hour_advice']['theme']}",
                "时辰宜：" + "、".join(p["hour_advice"]["yi"]),
                "时辰忌：" + "、".join(p["hour_advice"]["ji"]),
                *p["day_links"],
                *p["hour_links"],
            ]
        )
    for p in report["ten_masters"]:
        lines.append(
            f"{p['master']}{p['element']} · {p['day_god']} / {p['day_advice']['theme']}；宜{p['day_advice']['yi'][0]}，忌{p['day_advice']['ji'][0]}。"
        )
    lines.append(report["scope"])
    return "\n".join(lines)
