# -*- coding: utf-8 -*-
"""Unit tests for tzcore: conversion, DST boundaries, holidays,
business-hours judgement and candidate-slot computation."""

import sys
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tzcore
from tzcore import OwnSettings, Partner

TOKYO = OwnSettings(zone="Asia/Tokyo", country_code="JP",
                    work_start="09:00", work_end="18:00")
NY = Partner(name="NY Office", country_code="US", city="New York",
             zone="America/New_York")
LONDON = Partner(name="London Office", country_code="GB", city="London",
                 zone="Europe/London")
BERLIN = Partner(name="Berlin Office", country_code="DE", city="Berlin",
                 zone="Europe/Berlin")
SINGAPORE = Partner(name="SG Office", country_code="SG", city="Singapore",
                    zone="Asia/Singapore")


def aware(zone, y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=ZoneInfo(zone))


# ---------------- conversion ----------------

def test_conversion_tokyo_to_new_york_winter():
    res = tzcore.check_partner(aware("Asia/Tokyo", 2026, 1, 15, 10), TOKYO, NY)
    assert (res.local_dt.year, res.local_dt.month, res.local_dt.day,
            res.local_dt.hour) == (2026, 1, 14, 20)
    assert res.offset_label == "UTC-05:00"
    assert res.diff_hours == -14.0


def test_conversion_tokyo_to_london_summer():
    res = tzcore.check_partner(aware("Asia/Tokyo", 2026, 7, 1, 17), TOKYO, LONDON)
    assert res.local_dt.hour == 9           # BST = UTC+1
    assert res.offset_label == "UTC+01:00"
    assert res.diff_hours == -8.0


# ---------------- DST boundaries ----------------

def test_dst_us_spring_forward_2026():
    zone = ZoneInfo("America/New_York")
    before = datetime(2026, 3, 7, 12, tzinfo=zone).utcoffset()
    after = datetime(2026, 3, 9, 12, tzinfo=zone).utcoffset()
    assert before.total_seconds() == -5 * 3600
    assert after.total_seconds() == -4 * 3600


def test_dst_eu_spring_forward_2026():
    zone = ZoneInfo("Europe/Berlin")
    before = datetime(2026, 3, 28, 12, tzinfo=zone).utcoffset()
    after = datetime(2026, 3, 30, 12, tzinfo=zone).utcoffset()
    assert before.total_seconds() == 1 * 3600
    assert after.total_seconds() == 2 * 3600


def test_dst_change_near_detects_us_switch():
    found = tzcore.dst_change_near("America/New_York", date(2026, 3, 5),
                                   within_days=7)
    assert found == date(2026, 3, 8)


def test_dst_change_near_none_for_tokyo():
    assert tzcore.dst_change_near("Asia/Tokyo", date(2026, 3, 5),
                                  within_days=7) is None


# ---------------- holidays ----------------

def test_holiday_japan_new_year():
    assert tzcore.holiday_on("JP", date(2026, 1, 1)) is not None


def test_holiday_us_christmas():
    name = tzcore.holiday_on("US", date(2026, 12, 25))
    assert name is not None and "Christmas" in name


def test_holiday_germany_unity_day():
    assert tzcore.holiday_on("DE", date(2026, 10, 3)) is not None


def test_no_holiday_on_plain_day():
    assert tzcore.holiday_on("JP", date(2026, 1, 19)) is None


# ---------------- business-hours judgement ----------------

def test_business_hours_ok_london_summer():
    # Mon 2026-07-06 17:00 JST = 09:00 BST, a business day in both.
    res = tzcore.check_partner(aware("Asia/Tokyo", 2026, 7, 6, 17),
                               TOKYO, LONDON)
    assert res.in_business_hours
    assert not res.is_weekend
    assert res.holiday_name is None
    assert res.ok


def test_outside_hours_london_winter_morning():
    # Mon 2026-01-19 10:00 JST = 01:00 GMT -> outside hours.
    res = tzcore.check_partner(aware("Asia/Tokyo", 2026, 1, 19, 10),
                               TOKYO, LONDON)
    assert not res.in_business_hours
    assert not res.ok


def test_weekend_detection():
    # Sat 2026-01-17 in Tokyo for a Tokyo partner.
    tokyo_partner = Partner(name="Tokyo", country_code="JP", city="Tokyo",
                            zone="Asia/Tokyo")
    res = tzcore.check_partner(aware("Asia/Tokyo", 2026, 1, 17, 11),
                               TOKYO, tokyo_partner)
    assert res.is_weekend
    assert not res.ok


def test_holiday_blocks_ok():
    # Fri 2026-12-25 20:00 JST = 11:00 GMT in London, but Christmas.
    res = tzcore.check_partner(aware("Asia/Tokyo", 2026, 12, 25, 20),
                               TOKYO, LONDON)
    assert res.holiday_name is not None
    assert not res.ok


def test_weekend_fri_sat_country():
    # Israel weekend is Fri/Sat: Fri 2026-01-16 is a weekend day.
    assert tzcore.is_weekend((4, 5), date(2026, 1, 16))
    assert not tzcore.is_weekend((4, 5), date(2026, 1, 18))  # Sunday


# ---------------- candidate slots ----------------

def test_slots_singapore_overlap():
    slots = tzcore.find_candidate_slots(
        TOKYO, SINGAPORE, date(2026, 1, 19), 1, duration_min=60)
    assert slots, "expected overlapping slots Tokyo/Singapore"
    first = slots[0]
    assert first.own_start.hour == 10       # 10:00 JST = 09:00 SGT
    assert first.partner_start.hour == 9


def test_slots_london_summer_one_hour():
    slots = tzcore.find_candidate_slots(
        TOKYO, LONDON, date(2026, 7, 6), 1, duration_min=60)
    assert len(slots) == 1
    assert slots[0].own_start.hour == 17    # 17:00 JST = 09:00 BST
    assert slots[0].partner_start.hour == 9


def test_slots_london_winter_none_for_60min():
    slots = tzcore.find_candidate_slots(
        TOKYO, LONDON, date(2026, 1, 19), 1, duration_min=60)
    assert slots == []


def test_slots_skip_own_holiday():
    # 2026-01-01 is a JP holiday -> no slots even with Singapore.
    slots = tzcore.find_candidate_slots(
        TOKYO, SINGAPORE, date(2026, 1, 1), 1, duration_min=60)
    assert slots == []


def test_slots_skip_weekend():
    # Sat 2026-01-17 -> no slots.
    slots = tzcore.find_candidate_slots(
        TOKYO, SINGAPORE, date(2026, 1, 17), 1, duration_min=60)
    assert slots == []


# ---------------- misc ----------------

def test_fmt_diff_hours():
    assert tzcore.fmt_diff_hours(-14.0) == "-14h"
    assert tzcore.fmt_diff_hours(5.5) == "+5.5h"
    assert tzcore.fmt_diff_hours(0.0) == "+0h"


def test_state_roundtrip(tmp_path, monkeypatch):
    target = tmp_path / "settings.json"
    monkeypatch.setattr(tzcore, "settings_path", lambda: str(target))
    state = tzcore.AppState(
        own=OwnSettings(zone="Europe/London", country_code="GB"),
        partners=[NY], lang="de")
    tzcore.save_state(state)
    loaded = tzcore.load_state()
    assert loaded.own.zone == "Europe/London"
    assert loaded.lang == "de"
    assert len(loaded.partners) == 1
    assert loaded.partners[0].zone == "America/New_York"
    assert loaded.partners[0].proposal_lang == "en"
