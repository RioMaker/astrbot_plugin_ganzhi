"""Deterministic calendar boundary; all civil instants are converted to UTC+8."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from lunar_python import Solar

BEIJING = timezone(timedelta(hours=8), "北京时间")
STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
CYCLE = tuple(STEMS[i % 10] + BRANCHES[i % 12] for i in range(60))


def now_beijing() -> datetime:
    return datetime.now(BEIJING)


@dataclass(frozen=True)
class Profile:
    source: str
    value: str
    day_pillar: str

    @property
    def stem(self) -> str:
        return self.day_pillar[0]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CalendarSnapshot:
    instant: str
    year: str
    month: str
    day: str
    hour: str
    hour_range: str
    lunar_date: str
    boundary: str

    def to_dict(self) -> dict:
        return asdict(self)


def snapshot(instant: datetime, boundary: str = "midnight") -> CalendarSnapshot:
    if boundary not in {"midnight", "zi"}:
        raise ValueError("换日规则只能是 midnight 或 zi。")
    if instant.tzinfo is None:
        raise ValueError("时间必须带时区。")
    local = instant.astimezone(BEIJING)
    if not 1900 <= local.year <= 2100:
        raise ValueError("目前支持 1900–2100 年。")
    lunar = Solar.fromYmdHms(
        local.year, local.month, local.day, local.hour, local.minute, local.second
    ).getLunar()
    # Sect 2 keeps the late Zi hour on the civil day; hour stem follows 五鼠遁
    # as implemented by lunar-python (late Zi uses the following day stem).
    eight = lunar.getEightChar()
    eight.setSect(2 if boundary == "midnight" else 1)
    branch_index = ((local.hour + 1) // 2) % 12
    start = (branch_index * 2 - 1) % 24
    end = (start + 2) % 24
    return CalendarSnapshot(
        instant=local.isoformat(timespec="seconds"),
        year=eight.getYear(),
        month=eight.getMonth(),
        day=eight.getDay(),
        hour=eight.getTime(),
        hour_range=f"{BRANCHES[branch_index]}时 {start:02}:00–{end:02}:00",
        lunar_date=f"{lunar.getMonthInChinese()}月{lunar.getDayInChinese()}",
        boundary=boundary,
    )


def parse_profile(value: str, today=None) -> Profile:
    text = value.strip()
    if text in STEMS and len(text) == 1:
        return Profile("stem", text, text)
    if text in CYCLE:
        return Profile("pillar", text, text)
    if re.fullmatch(r"\d{8}|\d{4}-\d{2}-\d{2}", text):
        try:
            birth = datetime.strptime(text.replace("-", ""), "%Y%m%d").date()
        except ValueError as exc:
            raise ValueError("阳历生日无效，请检查年月日，例如 20010319。") from exc
        if not 1900 <= birth.year <= 2100 or birth > (today or now_beijing().date()):
            raise ValueError("生日须在 1900 年至今天之间，不能填写未来日期。")
        # Date-only input intentionally uses noon; no fictitious natal time pillar.
        pillar = snapshot(datetime(birth.year, birth.month, birth.day, 12, tzinfo=BEIJING)).day
        return Profile("birthday", birth.isoformat(), pillar)
    raise ValueError(
        "请输入阳历生日 YYYYMMDD（如 20010319），或六十甲子日柱（如 辛巳），"
        "也可只填日主（如 辛）。生日不支持农历输入。"
    )
