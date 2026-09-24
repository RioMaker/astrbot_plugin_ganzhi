"""Traceable, deliberately limited daily five-element / ten-god interpretation."""

from __future__ import annotations

import json
from pathlib import Path

from .calendar_core import STEMS, CalendarSnapshot, Profile

RULE_VERSION = "ganzhi-rules-v1"
ELEMENTS = "木火土金水"
STEM_ELEMENT = dict(zip(STEMS, "木木火火土土金金水水"))
GENERATES = dict(zip(ELEMENTS, "火土金水木"))
CONTROLS = dict(zip(ELEMENTS, "土金水木火"))
HIDDEN = dict(
    zip(
        "子丑寅卯辰巳午未申酉戌亥",
        (
            "癸",
            "己癸辛",
            "甲丙戊",
            "乙",
            "戊乙癸",
            "丙庚戊",
            "丁己",
            "己丁乙",
            "庚壬戊",
            "辛",
            "戊辛丁",
            "壬甲",
        ),
    )
)
ROOT = Path(__file__).resolve().parent
TEN_GODS = json.loads((ROOT / "data" / "ten_gods.json").read_text(encoding="utf-8"))
REFERENCE_TEXT = "\n\n".join(
    (ROOT / "references" / name).read_text(encoding="utf-8")
    for name in ("calendar.md", "interpretation.md")
)


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


def season_states(month_branch: str) -> dict[str, str]:
    dominant = STEM_ELEMENT[HIDDEN[month_branch][0]]
    return {
        dominant: "旺",
        GENERATES[dominant]: "相",
        CONTROLS[dominant]: "死",
        next(x for x in ELEMENTS if GENERATES[x] == dominant): "休",
        next(x for x in ELEMENTS if CONTROLS[x] == dominant): "囚",
    }


def flow(pillars: list[tuple[str, str, float]], month_branch: str) -> dict:
    amounts = dict.fromkeys(ELEMENTS, 0.0)
    evidence = []
    for label, pillar, weight in pillars:
        amounts[STEM_ELEMENT[pillar[0]]] += weight
        hidden = HIDDEN[pillar[1]]
        ratios = {1: (1.0,), 2: (0.7, 0.3), 3: (0.6, 0.3, 0.1)}[len(hidden)]
        for stem, ratio in zip(hidden, ratios):
            amounts[STEM_ELEMENT[stem]] += weight * ratio
        evidence.append({"position": label, "pillar": pillar, "hidden": hidden, "weight": weight})
    states = season_states(month_branch)
    factor = {"旺": 1.4, "相": 1.2, "休": 1.0, "囚": 0.8, "死": 0.6}
    weighted = {x: amounts[x] * factor[states[x]] for x in ELEMENTS}
    total = sum(weighted.values())
    percent = {x: round(weighted[x] / total * 100, 1) for x in ELEMENTS}
    paths, weak_paths = [], []
    for x in ELEMENTS:
        dest = GENERATES[x]
        (paths if min(percent[x], percent[dest]) >= 10 else weak_paths).append(f"{x}生{dest}")
    order = sorted(ELEMENTS, key=lambda x: -percent[x])
    return {
        "percent": percent,
        "raw": {x: round(amounts[x], 3) for x in ELEMENTS},
        "season_states": states,
        "dominant": order[:2],
        "low": [x for x in ELEMENTS if percent[x] < 10],
        "generation_paths": paths,
        "weak_paths": weak_paths,
        "control_paths": [
            f"{x}克{CONTROLS[x]}" for x in ELEMENTS if min(percent[x], percent[CONTROLS[x]]) >= 10
        ],
        "evidence": evidence,
        "summary": f"{month_branch}月；环境以{order[0]}为主，{order[1]}次之。"
        + ("可见生路：" + "、".join(paths) + "。" if paths else "相生承接偏弱。")
        + (
            "偏少：" + "、".join(x for x in ELEMENTS if percent[x] < 10) + "。"
            if any(percent[x] < 10 for x in ELEMENTS)
            else "五行均有一定呈现。"
        ),
    }


def branch_links(natal: str, present: str) -> list[str]:
    pair = frozenset((natal, present))
    out = []
    for name, pairs, detail in (
        ("六合", ("子丑", "寅亥", "卯戌", "辰酉", "巳申", "午未"), "适合协调，合不等于已经合化"),
        ("六冲", ("子午", "丑未", "寅申", "卯酉", "辰戌", "巳亥"), "安排留余地，变动处多复核"),
        ("六害", ("子未", "丑午", "寅巳", "卯辰", "申亥", "酉戌"), "把隐含期待说清楚，减少误解"),
    ):
        if pair in [frozenset(x) for x in pairs]:
            out.append(f"{natal}{present}{name}：{detail}")
    if natal == present:
        out.append(f"日支同为{natal}：重复议题适合回顾，不据此断吉凶")
    return out


def personal(profile: Profile, cal: CalendarSnapshot, day_flow: dict) -> dict:
    master = profile.stem
    day_god, hour_god = ten_god(master, cal.day[0]), ten_god(master, cal.hour[0])
    own = STEM_ELEMENT[master]
    proportions = day_flow["percent"]
    relations = {
        "同我": proportions[own],
        "我生": proportions[GENERATES[own]],
        "我克": proportions[CONTROLS[own]],
        "生我": proportions[next(x for x in ELEMENTS if GENERATES[x] == own)],
        "克我": proportions[next(x for x in ELEMENTS if CONTROLS[x] == own)],
    }
    emphasis = max(relations, key=relations.get)
    environment_note = {
        "同我": "同类力量较显，协作时说清资源和分工",
        "我生": "产出议题较显，表达和创作也要安排休息",
        "我克": "管理议题较显，落实事项前核对可用精力与成本",
        "生我": "支持与输入较显，学习整理后及时转为行动",
        "克我": "规则和要求较显，先明确标准再分步推进",
    }[emphasis]
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
        "relations_percent": relations,
        "environment_note": f"{emphasis}环境占比 {relations[emphasis]:.1f}%：{environment_note}。",
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
    day_flow = flow(
        [("年", cal.year, 0.5), ("月", cal.month, 1.5), ("日", cal.day, 1.0)], cal.month[1]
    )
    report = {
        "rule_version": RULE_VERSION,
        "calendar": cal.to_dict(),
        "day_flow": day_flow,
        "hour_flow": flow([("时", cal.hour, 1.0)], cal.month[1]),
        "personal": personal(profile, cal, day_flow) if profile else None,
        "ten_masters": [personal(Profile("stem", x, x), cal, day_flow) for x in STEMS]
        if daily
        else [],
        "scope": "传统文化日常安排参考；环境权重不是吉凶概率。",
    }
    return report


def agent_payload(report: dict) -> str:
    return json.dumps(
        {
            "calculated": report,
            "reference_document": REFERENCE_TEXT,
            "ten_god_reference": TEN_GODS,
            "instruction": "先用 calculated 说明依据，再参考文档解读；生日只接受阳历。不要编造本命、改写干支或把象意当确定预测。",
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
        "环境占比：" + " / ".join(f"{x} {v}%" for x, v in report["day_flow"]["percent"].items()),
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
