import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest
from astrbot_plugin_ganzhi.calendar_core import (
    BEIJING,
    CYCLE,
    STEMS,
    parse_profile,
    snapshot,
)
from astrbot_plugin_ganzhi.engine import (
    TEN_GODS,
    agent_payload,
    branch_links,
    build_report,
    element_relation,
    pillar_graph,
    ten_god,
)


@pytest.mark.parametrize(
    "left,right,kind,direction",
    [
        ("木", "火", "生", 1),
        ("火", "木", "生", -1),
        ("金", "木", "克", 1),
        ("木", "金", "克", -1),
        ("水", "水", "同气", 0),
    ],
)
def test_relation_arrows_point_to_recipient(left, right, kind, direction):
    assert element_relation(left, right) == {"kind": kind, "direction": direction}


def test_pillar_graph_hidden_stems_and_vertical_direction():
    cal = snapshot(datetime(2026, 9, 24, 8, tzinfo=BEIJING))
    graph = pillar_graph(cal)
    assert ["".join(x["stem"] for x in c["hidden"]) for c in graph["columns"]] == [
        "丁己",
        "辛",
        "己癸辛",
        "戊乙癸",
    ]
    assert graph["stem_edges"] == [
        {"kind": "同气", "direction": 0},
        {"kind": "克", "direction": 1},
        {"kind": "生", "direction": 1},
    ]
    assert graph["branch_edges"][1] == {"kind": "生", "direction": -1}  # 丑土生酉金
    assert graph["vertical_edges"][2] == {"kind": "生", "direction": -1}  # 丑土生辛金
    assert graph["vertical_edges"][3] == {"kind": "克", "direction": -1}  # 辰土克壬水
    assert "干合 丙辛、丁壬（未定化）" in graph["combinations"]
    assert "午丑害" in graph["combinations"] and "酉辰合" in graph["combinations"]
    assert build_report(cal)["pillar_graph"] == graph


def test_repeated_pillars_do_not_repeat_combination_labels():
    base = snapshot(datetime(2026, 9, 24, 8, tzinfo=BEIJING))
    graph = pillar_graph(replace(base, year="甲子", month="己丑", day="甲子", hour="己丑"))
    assert graph["combinations"] == "干合 甲己（未定化） · 支间 子丑合"


@pytest.mark.parametrize(
    "ymdhms,expected",
    [
        ((2005, 12, 23, 8, 37, 0), ("乙酉", "戊子", "辛巳", "壬辰")),
        ((2022, 8, 28, 1, 50, 0), ("壬寅", "戊申", "癸丑", "癸丑")),
        ((1988, 2, 15, 23, 30, 0), ("戊辰", "甲寅", "庚子", "戊子")),
    ],
)
def test_upstream_calendar_golden_cases(ymdhms, expected):
    """Fixed examples from 6tail/lunar-python EightCharTest, not self-generated."""
    cal = snapshot(datetime(*ymdhms, tzinfo=BEIJING))
    assert (cal.year, cal.month, cal.day, cal.hour) == expected


def test_li_chun_exact_second_and_solar_month():
    boundary = datetime(2026, 2, 4, 4, 2, 8, tzinfo=BEIJING)
    before, after = snapshot(boundary - timedelta(seconds=1)), snapshot(boundary)
    assert (before.year, before.month) == ("乙巳", "己丑")
    assert (after.year, after.month) == ("丙午", "庚寅")
    assert before.day == after.day


def test_late_zi_both_schools_and_timezone():
    instant = datetime(1988, 2, 15, 23, 30, tzinfo=BEIJING)
    midnight, zi = snapshot(instant), snapshot(instant, "zi")
    assert midnight.day == "庚子"
    assert zi.day == "辛丑"
    assert midnight.hour == zi.hour == "戊子"
    assert snapshot(instant.astimezone(timezone.utc)) == midnight
    assert snapshot(instant + timedelta(minutes=30)).day == zi.day


@pytest.mark.parametrize(
    "hour,branch", [(0, "子"), (1, "丑"), (2, "丑"), (3, "寅"), (21, "亥"), (22, "亥"), (23, "子")]
)
def test_hour_boundaries(hour, branch):
    assert snapshot(datetime(2026, 9, 24, hour, tzinfo=BEIJING)).hour[1] == branch


def test_sixty_days_and_midnight_rollover():
    start = datetime(2024, 2, 1, 12, tzinfo=BEIJING)
    days = [snapshot(start + timedelta(days=i)).day for i in range(61)]
    assert len(set(days[:60])) == 60
    assert days[0] == days[-1]
    assert all(CYCLE[(CYCLE.index(a) + 1) % 60] == b for a, b in zip(days, days[1:]))


@pytest.mark.parametrize(
    "value",
    [
        "甲丑",
        "辛子",
        "20010229",
        "20011301",
        "18990101",
        "21010101",
        "99999999",
        "农历20010319",
        "",
        "辛巳/../../",
        "辛巳 甲子",
    ],
)
def test_reject_invalid_profile(value):
    with pytest.raises(ValueError):
        parse_profile(value, today=date(2026, 9, 24))


def test_birthday_no_time_and_future_rejection():
    a, b = parse_profile("20010319"), parse_profile("2001-03-19")
    assert a == b
    assert a.source == "birthday" and a.day_pillar in CYCLE
    assert parse_profile("20000229").value == "2000-02-29"
    with pytest.raises(ValueError):
        parse_profile("20260925", today=date(2026, 9, 24))


def test_ten_gods_known_table_and_all_pairs():
    assert [ten_god("甲", x) for x in STEMS] == [
        "比肩",
        "劫财",
        "食神",
        "伤官",
        "偏财",
        "正财",
        "七杀",
        "正官",
        "偏印",
        "正印",
    ]
    assert [ten_god("辛", x) for x in "壬癸丙丁己戊"] == [
        "伤官",
        "食神",
        "正官",
        "七杀",
        "偏印",
        "正印",
    ]
    for master in STEMS:
        assert {ten_god(master, x) for x in STEMS} == set(TEN_GODS)


def test_day_flow_hour_independent_and_personal_evidence():
    am = snapshot(datetime(2026, 9, 24, 8, tzinfo=BEIJING))
    pm = snapshot(datetime(2026, 9, 24, 14, tzinfo=BEIJING))
    report = build_report(am, parse_profile("辛巳"))
    other = build_report(pm, parse_profile("辛巳"))
    assert report["day_flow"] == other["day_flow"]
    assert report["personal"]["hour_god"] != other["personal"]["hour_god"]
    assert sum(report["day_flow"]["percent"].values()) == pytest.approx(100, abs=0.2)
    assert report["personal"]["day_god"] == "比肩"
    assert report["personal"]["hour_god"] == "伤官"
    assert report["day_flow"]["dominant"][0] == "金"
    assert report["day_flow"]["season_states"]["金"] == "旺"
    assert report["personal"]["day_hidden"]


def test_reference_payload_and_ten_masters_no_birthday_leak():
    cal = snapshot(datetime(2026, 9, 24, 8, tzinfo=BEIJING))
    payload = agent_payload(build_report(cal, parse_profile("20010319")))
    assert "2001-03-19" not in payload
    loaded = json.loads(payload)
    assert "阳历" in loaded["reference_document"]
    assert len(loaded["ten_god_reference"]) == 10
    daily = build_report(cal, daily=True)
    assert daily["personal"] is None
    assert "".join(x["master"] for x in daily["ten_masters"]) == STEMS


def test_branch_evidence_does_not_invent_combination():
    assert "六冲" in branch_links("巳", "亥")[0]
    assert "合化" in branch_links("巳", "申")[0]
    assert "六害" in branch_links("子", "未")[0]
    assert branch_links("寅", "辰") == []
