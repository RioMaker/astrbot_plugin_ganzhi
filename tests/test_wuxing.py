"""Counterexamples for WX01–12; fixtures are structures, not outcome predictions."""

import json
from datetime import datetime

import pytest
from astrbot_plugin_ganzhi.calendar_core import BEIJING, parse_profile, snapshot
from astrbot_plugin_ganzhi.engine import RULE_CATALOG, agent_payload, build_report
from astrbot_plugin_ganzhi.wuxing import HIDDEN, build_columns, flow, season_states
from lunar_python.util import LunarUtil


def analyze(*values):
    return flow(list(zip("年月日时", values)), values[1][1])


def mechanisms_for(result, kind, source="金", target="木"):
    return [
        m
        for m in result["mechanisms"]
        if m["kind"] == kind
        and m["source"]["element"] == source
        and m["target"]["element"] == target
    ]


def checks(item):
    return {c["code"]: c["passed"] for c in item["checks"]}


def test_all_hidden_sets_cross_checked_against_calendar_library():
    assert len(HIDDEN) == 12
    for branch, stems in HIDDEN.items():
        assert set(stems) == set(LunarUtil.ZHI_HIDE_GAN[branch])
        assert len(stems) == len(set(stems))


def test_exact_exposure_is_not_same_as_same_element_root():
    result = analyze("甲辰", "辛酉", "丙午")
    wood = result["columns"][0]
    assert wood["root_status"] == "兼气通根"
    assert wood["roots"][0]["stem"] == "乙" and not wood["roots"][0]["same_stem"]
    assert next(h for h in wood["hidden"] if h["stem"] == "乙")["exposed_at"] == []
    other = analyze("乙巳", "辛酉", "甲辰")
    assert next(h for h in other["columns"][2]["hidden"] if h["stem"] == "乙")["exposed_at"] == [
        "年"
    ]


def test_off_season_rooted_and_unrooted_wood_differ_without_strength_score():
    rooted = analyze("甲寅", "辛酉", "丙午")
    unrooted = analyze("甲午", "辛酉", "丙午")
    assert rooted["season_states"]["木"] == unrooted["season_states"]["木"] == "死"
    assert rooted["columns"][0]["root_status"] == "本气通根"
    assert unrooted["columns"][0]["root_status"] == "未见藏干根"
    assert "percent" not in rooted and "dominant" not in rooted


@pytest.mark.parametrize("month", list("辰戌丑未"))
def test_mixed_month_does_not_invent_whole_month_earth_dominance(month):
    assert set(season_states(month).values()) == {"杂气待辨"}
    assert flow([("时", "甲子")], month)["month"]["commander"] is None


def test_root_disturbed_is_retained_not_deleted():
    roots = analyze("甲寅", "庚申", "丙午")["columns"][0]["roots"]
    assert len(roots) == 1 and roots[0]["stem"] == "甲"
    assert {r["kind"] for r in roots[0]["disturbances"]} == {"冲", "刑"}


def test_generation_is_also_drain_and_hidden_nodes_remain_identifiable():
    result = analyze("甲寅", "丙午", "戊辰")
    edge = next(e for e in result["relations"] if e["level"] == "stem" and e["label"] == "木生火")
    assert edge["source"]["stem"] == "甲" and edge["source_effect"] == "泄气"
    vertical = [e for e in result["relations"] if e["level"] == "stem_hidden"]
    assert len(vertical) == 8
    assert all("branch" in e["source"] or "branch" in e["target"] for e in vertical)


def test_mediation_with_root_and_position_is_candidate_not_resolved():
    result = analyze("庚申", "壬辰", "甲子")
    (route,) = mechanisms_for(result, "通关")
    assert route["status"] == "candidate"
    assert route["path"] == "金→水→木" and not route["resolved"]
    assert all(checks(route).values())
    assert any(e["label"] == "金克木" for e in result["relations"])


@pytest.mark.parametrize(
    "pillars,status",
    [
        (("庚戌", "甲寅", "丙午"), "missing"),
        (("庚申", "甲寅", "丙午"), "hidden_only"),
        (("庚戌", "壬午", "甲寅"), "conditional"),
    ],
)
def test_mediator_absent_hidden_only_or_exposed_without_root(pillars, status):
    (route,) = mechanisms_for(analyze(*pillars), "通关")
    assert route["status"] == status
    if status == "conditional":
        assert not checks(route)["rooted"]
    assert not route["resolved"]


def test_mediation_does_not_teleport_across_pillars():
    (route,) = mechanisms_for(analyze("庚申", "甲寅", "丙戌", "壬子"), "通关")
    assert route["status"] == "conditional" and not checks(route)["connected"]


def test_combined_mediator_keeps_combination_as_complication():
    (route,) = mechanisms_for(analyze("庚申", "壬辰", "甲子", "丁卯"), "通关")
    assert route["status"] == "conditional" and not checks(route)["uncombined"]


def test_restraint_and_mediation_are_different_routes():
    result = analyze("丙午", "庚申", "甲辰")
    (restraint,) = mechanisms_for(result, "制约")
    (mediation,) = mechanisms_for(result, "通关")
    assert restraint["status"] == "candidate" and restraint["path"] == "火克金克木"
    assert mediation["status"] == "hidden_only" and not restraint["resolved"]


def test_combination_screen_does_not_replace_elements_even_when_all_checks_pass():
    result = analyze("甲寅", "己未", "戊辰", "丙午")
    (merge,) = result["stem_combinations"]
    assert merge["status"] == "candidate" and merge["target"] == "土"
    assert all(checks(merge).values()) and not merge["transformed"]
    assert result["columns"][0]["stem_element"] == "木" and result["columns"][0]["roots"]


@pytest.mark.parametrize(
    "pillars,failed",
    [
        (("甲寅", "己未", "庚辰", "丙午"), "exposed_target"),
        (("甲寅", "己酉", "戊辰", "丙午"), "month"),
        (("甲寅", "戊辰", "己未", "丙午"), "adjacent"),
        (("甲寅", "己未", "乙卯", "戊辰"), "no_control"),
    ],
)
def test_pair_and_one_condition_never_imply_transformation(pillars, failed):
    (merge,) = analyze(*pillars)["stem_combinations"]
    assert merge["status"] == "conditional" and not checks(merge)[failed]
    assert not merge["transformed"]


def test_competing_stem_pairs_preserve_both_positions():
    merges = analyze("甲寅", "己未", "甲辰", "丙午")["stem_combinations"]
    assert len(merges) == 2 and merges[0]["indices"] != merges[1]["indices"]
    assert all(not checks(m)["exclusive"] for m in merges)


def test_missing_trine_member_is_never_fabricated():
    partial = analyze("庚申", "壬子", "丙午")
    item = next(g for g in partial["branch_groups"] if g["glyphs"] == "申子辰")
    assert item["missing"] == "辰" and not item["complete"]
    assert item["partial_kind"] == "半合候选" and not item["transformed"]
    arch = analyze("庚申", "戊辰", "丙午")
    item = next(g for g in arch["branch_groups"] if g["glyphs"] == "申子辰")
    assert item["missing"] == "子" and item["partial_kind"] == "拱合候选"


def test_full_trine_keeps_conflict_and_full_season_group_is_distinct():
    result = analyze("庚申", "壬子", "戊辰", "丙午")
    item = next(g for g in result["branch_groups"] if g["glyphs"] == "申子辰")
    assert item["complete"] and item["status"] == "complete_with_conflict"
    assert item["disturbances"] and not item["transformed"]
    season = analyze("甲寅", "乙卯", "戊辰", "丙午")
    item = next(g for g in season["branch_groups"] if g["kind"] == "三会")
    assert item["glyphs"] == "寅卯辰" and item["complete"]


def test_combination_clash_harm_punishment_and_self_punishment_coexist():
    links = analyze("甲寅", "己巳", "庚申", "壬申")["branch_relations"]
    assert {r["kind"] for r in links if r["indices"] == [1, 2]} == {"合", "刑"}
    assert {r["kind"] for r in links if r["indices"] == [0, 1]} == {"害", "刑"}
    assert not any(r["kind"] == "自刑" for r in links)
    single = analyze("甲辰", "丙午", "庚申")
    assert not any(r["kind"] == "自刑" for r in single["branch_relations"])
    double = analyze("甲辰", "丙午", "戊辰")
    assert any(r["kind"] == "自刑" and r["indices"] == [0, 2] for r in double["branch_relations"])


@pytest.mark.parametrize("pillars", [[], [("年", "甲丑")], [("年", "甲子"), ("年", "乙丑")]])
def test_invalid_structures_fail_explicitly(pillars):
    with pytest.raises(ValueError):
        build_columns(pillars)


def test_agent_gets_notes_source_catalog_and_rule_ids_without_invented_scores():
    report = build_report(
        snapshot(datetime(2026, 9, 24, 8, tzinfo=BEIJING)), parse_profile("20010319")
    )
    payload = json.loads(agent_payload(report))
    assert report["rule_version"] == payload["rule_catalog"]["version"] == "ganzhi-rules-v2"
    assert "八字生克制化研读笔记" in payload["reference_document"]
    assert "2001-03-19" not in json.dumps(payload)
    assert "relations_evidence" in report["personal"]
    found = set()

    def walk(value):
        if isinstance(value, dict):
            assert not ({"percent", "relations_percent", "raw"} & value.keys())
            found.update(value.get("rule_ids", []))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(report)
    assert found <= RULE_CATALOG["rules"].keys()
    assert {"WX01", "WX06", "WX08", "WX12"} <= found
    for rule in RULE_CATALOG["rules"].values():
        assert set(rule["sources"]) <= RULE_CATALOG["sources"].keys()
