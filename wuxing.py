"""Evidence-based traditional relations; implementation policy: references/bazi_notes.md."""

from __future__ import annotations

from collections import Counter
from itertools import combinations

from .calendar_core import CYCLE, STEMS

RULE_VERSION = "ganzhi-rules-v2"
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
STEM_COMBINATIONS = {"甲己": "土", "乙庚": "金", "丙辛": "水", "丁壬": "木", "戊癸": "火"}
TRANSFORM_MONTHS = {
    "土": "辰戌丑未午",
    "金": "巳酉丑申",
    "水": "申子辰亥",
    "木": "亥卯未寅",
    "火": "寅午戌巳",
}
BRANCH_PAIRS = {
    "合": ("子丑", "寅亥", "卯戌", "辰酉", "巳申", "午未"),
    "冲": ("子午", "丑未", "寅申", "卯酉", "辰戌", "巳亥"),
    "害": ("子未", "丑午", "寅巳", "卯辰", "申亥", "酉戌"),
    "刑": ("子卯", "寅巳", "巳申", "申寅", "丑戌", "戌未", "未丑"),
}
TRINES = {"申子辰": "水", "亥卯未": "木", "寅午戌": "火", "巳酉丑": "金"}
SEASON_GROUPS = {"寅卯辰": "木", "巳午未": "火", "申酉戌": "金", "亥子丑": "水"}


def element_relation(left: str, right: str) -> dict:
    """WX01: direction 1 = left/top to right/bottom, -1 = reverse, 0 = peers."""
    if left == right:
        return {"kind": "同气", "direction": 0}
    if GENERATES[left] == right:
        return {"kind": "生", "direction": 1}
    if GENERATES[right] == left:
        return {"kind": "生", "direction": -1}
    return {"kind": "克", "direction": 1 if CONTROLS[left] == right else -1}


def season_states(month_branch: str) -> dict[str, str]:
    # WX03: without a verified daily commander table, mixed months remain unresolved.
    if month_branch in "辰戌丑未":
        return dict.fromkeys(ELEMENTS, "杂气待辨")
    principal = STEM_ELEMENT[HIDDEN[month_branch][0]]
    return {
        principal: "旺",
        GENERATES[principal]: "相",
        CONTROLS[principal]: "死",
        next(x for x in ELEMENTS if GENERATES[x] == principal): "休",
        next(x for x in ELEMENTS if CONTROLS[x] == principal): "囚",
    }


def check(code: str, passed: bool, detail: str) -> dict:
    return {"code": code, "passed": bool(passed), "detail": detail}


def branch_relations(columns: list[dict]) -> list[dict]:
    """WX09: preserve simultaneous relations and physical positions, including duplicates."""
    out = []
    for a, b in combinations(columns, 2):
        glyphs = a["branch"] + b["branch"]
        kinds = [
            kind
            for kind, pairs in BRANCH_PAIRS.items()
            if any(set(glyphs) == set(pair) for pair in pairs)
        ]
        if a["branch"] == b["branch"] and a["branch"] in "辰午酉亥":
            kinds.append("自刑")
        for kind in kinds:
            out.append(
                {
                    "kind": kind,
                    "glyphs": glyphs,
                    "indices": [a["index"], b["index"]],
                    "positions": [a["label"], b["label"]],
                    "adjacent": b["index"] - a["index"] == 1,
                    "status": "observed",
                    "rule_ids": ["WX09"],
                }
            )
    return out


def disturbed(indices: list[int], links: list[dict]) -> list[dict]:
    return [
        r for r in links if r["kind"] in {"冲", "刑", "自刑"} and set(indices) & set(r["indices"])
    ]


def build_columns(pillars: list[tuple[str, str]]) -> list[dict]:
    if not pillars or len(pillars) > 4 or len({x[0] for x in pillars}) != len(pillars):
        raise ValueError("分析须提供 1–4 个不同位置的干支柱")
    columns = []
    for index, (label, value) in enumerate(pillars):
        if value not in CYCLE:
            raise ValueError(f"无效干支柱：{value}")
        columns.append(
            {
                "index": index,
                "label": label,
                "pillar": value,
                "stem": value[0],
                "branch": value[1],
                "stem_element": STEM_ELEMENT[value[0]],
                "branch_element": STEM_ELEMENT[HIDDEN[value[1]][0]],
                "hidden": [
                    {
                        "stem": stem,
                        "element": STEM_ELEMENT[stem],
                        "qi": "本气" if n == 0 else "兼气",
                        "exposed_at": [p for p, v in pillars if v[0] == stem],
                    }
                    for n, stem in enumerate(HIDDEN[value[1]])
                ],
            }
        )
    links = branch_relations(columns)
    for column in columns:
        roots = []
        for root in columns:
            for hidden in root["hidden"]:
                if hidden["element"] == column["stem_element"]:
                    roots.append(
                        {
                            "index": root["index"],
                            "position": root["label"],
                            "branch": root["branch"],
                            "stem": hidden["stem"],
                            "qi": hidden["qi"],
                            "same_stem": hidden["stem"] == column["stem"],
                            "disturbances": disturbed([root["index"]], links),
                        }
                    )
        column["roots"] = roots
        column["root_status"] = (
            "本气通根"
            if any(r["qi"] == "本气" for r in roots)
            else "兼气通根"
            if roots
            else "未见藏干根"
        )
    return columns


def stem_combinations(columns: list[dict], month: str, links: list[dict]) -> list[dict]:
    matches = []
    for a, b in combinations(columns, 2):
        pair = "".join(sorted(a["stem"] + b["stem"], key=STEMS.index))
        if pair in STEM_COMBINATIONS:
            matches.append((a, b, pair))
    partners = Counter(c["index"] for a, b, _ in matches for c in (a, b))
    out = []
    for a, b, pair in matches:
        target = STEM_COMBINATIONS[pair]
        indices = [a["index"], b["index"]]
        other = [c for c in columns if c["index"] not in indices]
        target_roots = [
            c
            for c in columns
            if c["branch_element"] == target and not disturbed([c["index"]], links)
        ]
        checks = [
            check("adjacent", b["index"] - a["index"] == 1, "配对天干相邻"),
            check(
                "exclusive", all(partners[i] == 1 for i in indices), "无重复相合对象（争合待察）"
            ),
            check(
                "month",
                month in TRANSFORM_MONTHS[target],
                f"化神{target}的月份线索：{TRANSFORM_MONTHS[target]}",
            ),
            check(
                "exposed_target",
                any(c["stem_element"] == target for c in other),
                "化神另有独立透干",
            ),
            check("target_root", bool(target_roots), "化神有未受冲刑的本气根"),
            check(
                "no_control",
                not any(CONTROLS[c["stem_element"]] == target for c in other),
                "未见其他透干克化神",
            ),
            check("seat_undisturbed", not disturbed(indices, links), "配对坐支未见冲刑"),
        ]
        out.append(
            {
                "glyphs": pair,
                "indices": indices,
                "positions": [a["label"], b["label"]],
                "target": target,
                "status": "candidate" if all(c["passed"] for c in checks) else "conditional",
                "checks": checks,
                "issues": ["未满足：" + c["detail"] for c in checks if not c["passed"]],
                "transformed": False,
                "rule_ids": ["WX08", "WX05"],
                "scope": "当前环境中的合化候选筛选；未定化，不改原五行，不判化气格。",
            }
        )
    return out


def branch_groups(columns: list[dict], links: list[dict]) -> list[dict]:
    present = {c["branch"] for c in columns}
    counts = Counter(c["branch"] for c in columns)
    out = []
    for kind, table in (
        ("三合", TRINES),
        ("三会", SEASON_GROUPS),
        ("三刑", {"寅巳申": None, "丑戌未": None}),
    ):
        for group, target in table.items():
            seen = [x for x in group if x in present]
            if len(seen) < 2:
                continue
            indices = [c["index"] for c in columns if c["branch"] in group]
            complete = len(seen) == 3
            disturbance = disturbed(indices, links)
            # A group's own partial刑 pairs are evidence of that group, not external damage.
            if kind == "三刑":
                disturbance = [r for r in disturbance if r["kind"] == "冲"]
            out.append(
                {
                    "kind": kind,
                    "glyphs": group,
                    "target": target,
                    "present": "".join(seen),
                    "missing": "".join(x for x in group if x not in present),
                    "indices": indices,
                    "complete": complete,
                    "status": "complete_with_conflict"
                    if complete and disturbance
                    else "complete"
                    if complete
                    else "partial",
                    "partial_kind": ("半合候选" if group[1] in seen else "拱合候选")
                    if kind == "三合" and not complete
                    else None,
                    "disturbances": disturbance,
                    "duplicate_members": [x for x in group if counts[x] > 1],
                    "transformed": False,
                    "rule_ids": ["WX09" if kind == "三刑" else "WX10"],
                }
            )
    for index, item in enumerate(out):
        item["competing_groups"] = [
            other["glyphs"] + other["kind"]
            for n, other in enumerate(out)
            if index != n
            and item["complete"]
            and other["complete"]
            and set(item["indices"]) & set(other["indices"])
        ]
    return out


def relation_edges(columns: list[dict]) -> list[dict]:
    edges = []

    def append(a, b, level, adjacent):
        relation = element_relation(a["element"], b["element"])
        if relation["direction"] == -1:
            a, b = b, a
        edges.append(
            {
                "kind": relation["kind"],
                "source": a,
                "target": b,
                "level": level,
                "adjacent": adjacent,
                "label": a["element"] + relation["kind"] + b["element"],
                "source_effect": "泄气"
                if relation["kind"] == "生"
                else "克出"
                if relation["kind"] == "克"
                else "同气",
                "status": "observed",
                "rule_ids": ["WX01", "WX05"],
            }
        )

    def stem_node(c):
        return {
            "index": c["index"],
            "position": c["label"],
            "stem": c["stem"],
            "element": c["stem_element"],
        }

    for a, b in combinations(columns, 2):
        append(stem_node(a), stem_node(b), "stem", b["index"] - a["index"] == 1)
    for c in columns:
        for hidden in c["hidden"]:
            append(
                stem_node(c),
                {"index": c["index"], "position": c["label"], "branch": c["branch"], **hidden},
                "stem_hidden",
                True,
            )
    return edges


def mechanisms(columns: list[dict], edges: list[dict], merges: list[dict]) -> list[dict]:
    out = []
    for edge in edges:
        if edge["level"] != "stem" or edge["kind"] != "克":
            continue
        source, target = edge["source"], edge["target"]
        for kind, mediator, rule in (
            ("通关", GENERATES[source["element"]], "WX06"),
            ("制约", next(x for x in ELEMENTS if CONTROLS[x] == source["element"]), "WX07"),
        ):
            carriers = [c for c in columns if c["stem_element"] == mediator]
            base = {
                "kind": kind,
                "source": source,
                "target": target,
                "mediator_element": mediator,
                "path": source["element"] + "→" + mediator + "→" + target["element"]
                if kind == "通关"
                else mediator + "克" + source["element"] + "克" + target["element"],
                "rule_ids": [rule, "WX04", "WX05"],
                "resolved": False,
            }
            if not carriers:
                hidden = [
                    {"position": c["label"], "branch": c["branch"], "stem": h["stem"]}
                    for c in columns
                    for h in c["hidden"]
                    if h["element"] == mediator
                ]
                out.append(
                    {
                        **base,
                        "status": "hidden_only" if hidden else "missing",
                        "mediator": None,
                        "hidden_evidence": hidden,
                        "checks": [],
                        "issues": ["中介仅藏未透，未评定暗中承接" if hidden else "中介五行未见"],
                    }
                )
                continue
            for mid in carriers:
                index = mid["index"]
                connected = abs(index - source["index"]) == 1 and (
                    abs(index - target["index"]) == 1
                    if kind == "通关"
                    else abs(source["index"] - target["index"]) == 1
                )
                checks = [
                    check("connected", connected, "两段天干关系直接相邻承接"),
                    check("rooted", bool(mid["roots"]), "中介天干有藏干根"),
                    check(
                        "root_undisturbed",
                        bool(mid["roots"]) and not any(r["disturbances"] for r in mid["roots"]),
                        "中介根支未见冲刑",
                    ),
                    check(
                        "uncontrolled",
                        not any(
                            abs(c["index"] - index) == 1 and CONTROLS[c["stem_element"]] == mediator
                            for c in columns
                        ),
                        "中介未受相邻天干克制",
                    ),
                    check(
                        "uncombined",
                        not any(index in m["indices"] for m in merges),
                        "中介无干合牵涉",
                    ),
                ]
                out.append(
                    {
                        **base,
                        "mediator": {
                            "position": mid["label"],
                            "stem": mid["stem"],
                            "roots": mid["roots"],
                        },
                        "status": "candidate"
                        if all(c["passed"] for c in checks)
                        else "conditional",
                        "checks": checks,
                        "issues": ["未满足：" + c["detail"] for c in checks if not c["passed"]],
                    }
                )
    return out


def flow(pillars: list[tuple[str, str]], month_branch: str) -> dict:
    """WX01–12: facts, conditional mechanisms and known unknowns, without invented scores."""
    columns = build_columns(pillars)
    states = season_states(month_branch)
    links = branch_relations(columns)
    merges = stem_combinations(columns, month_branch, links)
    edges = relation_edges(columns)
    chains = mechanisms(columns, edges, merges)
    elements = {}
    for element in ELEMENTS:
        exposed = [
            {"position": c["label"], "stem": c["stem"], "root_status": c["root_status"]}
            for c in columns
            if c["stem_element"] == element
        ]
        roots = [
            {"position": c["label"], "branch": c["branch"], **h}
            for c in columns
            for h in c["hidden"]
            if h["element"] == element
        ]
        elements[element] = {
            "exposed": exposed,
            "hidden": roots,
            "season_state": states[element],
            "presence": "透藏皆见"
            if exposed and roots
            else "仅透干"
            if exposed
            else "仅藏支"
            if roots
            else "未见",
        }
    paths = list(dict.fromkeys(e["label"] for e in edges if e["kind"] == "生" and e["adjacent"]))
    controls = list(dict.fromkeys(e["label"] for e in edges if e["kind"] == "克" and e["adjacent"]))
    mixed = month_branch in "辰戌丑未"
    month_note = (
        month_branch + "月杂气待辨"
        if mixed
        else month_branch + "月" + STEM_ELEMENT[HIDDEN[month_branch][0]] + "当令"
    )
    candidates = [c for c in chains if c["status"] == "candidate"]
    short = (
        candidates[0]["kind"] + "候选 " + candidates[0]["path"]
        if candidates
        else "、".join(paths[:2])
        if paths
        else "生路待察"
    )
    return {
        "rule_version": RULE_VERSION,
        "columns": columns,
        "elements": elements,
        "month": {
            "branch": month_branch,
            "hidden": HIDDEN[month_branch],
            "mixed": mixed,
            "commander": None,
            "note": month_note,
            "rule_ids": ["WX03"],
        },
        "season_states": states,
        "relations": edges,
        "branch_relations": links,
        "stem_combinations": merges,
        "branch_groups": branch_groups(columns, links),
        "mechanisms": chains,
        "generation_paths": paths,
        "control_paths": controls,
        "display_summary": month_note + " · " + short,
        "summary": month_note
        + "；"
        + "，".join(x + elements[x]["presence"] for x in ELEMENTS)
        + "。生路仅表示观察到的生泄关系，候选制化仍需辨作用力量。",
        "unassessed": [
            "全局力量及生克成败",
            "反生反克与生泄过度",
            "逐日人元司令",
            "寒暖燥湿调候",
            "从格与化气格",
        ],
        "rule_ids": ["WX01", "WX02", "WX03", "WX04", "WX05", "WX11", "WX12"],
    }
