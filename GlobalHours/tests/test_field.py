# -*- coding: utf-8 -*-
"""Field verification: conversions between real city pairs checked
against known-correct answers (IANA rules, incl. southern-hemisphere
DST, half-hour and 45-minute offsets, and the date line)."""

import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tzcore
from tzcore import OwnSettings, Partner

TOKYO = OwnSettings(zone="Asia/Tokyo", country_code="JP")


def conv(from_zone, y, m, d, hh, mm, to_partner):
    own = OwnSettings(zone=from_zone, country_code="JP")
    dt = datetime(y, m, d, hh, mm, tzinfo=ZoneInfo(from_zone))
    return tzcore.check_partner(dt, own, to_partner)


def P(code, city, zone):
    return Partner(name=city, country_code=code, city=city, zone=zone)


LONDON = P("GB", "London", "Europe/London")
NY = P("US", "New York", "America/New_York")
SYDNEY = P("AU", "Sydney", "Australia/Sydney")
DUBAI = P("AE", "Dubai", "Asia/Dubai")
DELHI = P("IN", "Delhi", "Asia/Kolkata")
KATHMANDU = P("NP", "Kathmandu", "Asia/Kathmandu")
ADELAIDE = P("AU", "Adelaide", "Australia/Adelaide")
AUCKLAND = P("NZ", "Auckland", "Pacific/Auckland")
HONOLULU = P("US", "Honolulu", "Pacific/Honolulu")
LA = P("US", "Los Angeles", "America/Los_Angeles")


def hm(res):
    return (res.local_dt.month, res.local_dt.day, res.local_dt.hour,
            res.local_dt.minute)


# --- 14 known-answer city-pair cases ---------------------------------

def test_tokyo_london_winter():
    assert hm(conv("Asia/Tokyo", 2026, 1, 15, 19, 0, LONDON)) == (1, 15, 10, 0)


def test_tokyo_london_summer():
    assert hm(conv("Asia/Tokyo", 2026, 7, 15, 19, 0, LONDON)) == (7, 15, 11, 0)


def test_tokyo_new_york_winter():
    assert hm(conv("Asia/Tokyo", 2026, 1, 15, 10, 0, NY)) == (1, 14, 20, 0)


def test_tokyo_sydney_summer_dst():
    # January: Sydney is on AEDT (UTC+11) -> +2h from Tokyo
    r = conv("Asia/Tokyo", 2026, 1, 15, 10, 0, SYDNEY)
    assert hm(r) == (1, 15, 12, 0)
    assert r.offset_label == "UTC+11:00"


def test_tokyo_sydney_winter():
    # July: Sydney is on AEST (UTC+10) -> +1h from Tokyo
    r = conv("Asia/Tokyo", 2026, 7, 15, 10, 0, SYDNEY)
    assert hm(r) == (7, 15, 11, 0)
    assert r.offset_label == "UTC+10:00"


def test_tokyo_dubai_no_dst():
    r = conv("Asia/Tokyo", 2026, 6, 15, 10, 0, DUBAI)
    assert hm(r) == (6, 15, 5, 0)
    assert r.diff_hours == -5.0


def test_tokyo_delhi_half_hour():
    r = conv("Asia/Tokyo", 2026, 1, 15, 10, 0, DELHI)
    assert hm(r) == (1, 15, 6, 30)
    assert r.offset_label == "UTC+05:30"


def test_tokyo_kathmandu_45_minutes():
    r = conv("Asia/Tokyo", 2026, 1, 15, 10, 0, KATHMANDU)
    assert hm(r) == (1, 15, 6, 45)
    assert r.offset_label == "UTC+05:45"
    assert r.diff_hours == -3.25


def test_tokyo_adelaide_dst_half_hour():
    # January: ACDT = UTC+10:30
    assert hm(conv("Asia/Tokyo", 2026, 1, 15, 10, 0, ADELAIDE)) == (1, 15, 11, 30)


def test_tokyo_adelaide_winter_half_hour():
    # July: ACST = UTC+09:30
    assert hm(conv("Asia/Tokyo", 2026, 7, 15, 10, 0, ADELAIDE)) == (7, 15, 10, 30)


def test_tokyo_auckland_summer():
    # January: NZDT = UTC+13
    assert hm(conv("Asia/Tokyo", 2026, 1, 15, 10, 0, AUCKLAND)) == (1, 15, 14, 0)


def test_tokyo_auckland_winter():
    # July: NZST = UTC+12
    assert hm(conv("Asia/Tokyo", 2026, 7, 15, 10, 0, AUCKLAND)) == (7, 15, 13, 0)


def test_tokyo_honolulu_previous_day():
    # Date line: Tokyo morning is Honolulu's previous afternoon
    r = conv("Asia/Tokyo", 2026, 1, 15, 10, 0, HONOLULU)
    assert hm(r) == (1, 14, 15, 0)
    assert r.diff_hours == -19.0


def test_sydney_los_angeles_dateline():
    r = conv("Australia/Sydney", 2026, 1, 15, 12, 0, LA)
    assert hm(r) == (1, 14, 17, 0)


# --- DST transition-day conversions -----------------------------------

def test_us_spring_forward_day():
    # 2026-03-08 16:00 JST = 07:00 UTC = 03:00 EDT (02:00-03:00 skipped)
    r = conv("Asia/Tokyo", 2026, 3, 8, 16, 0, NY)
    assert hm(r) == (3, 8, 3, 0)
    assert r.offset_label == "UTC-04:00"


def test_us_fall_back_day():
    # 2026-11-01 15:00 JST = 06:00 UTC = 01:00 EST (second 01:00)
    r = conv("Asia/Tokyo", 2026, 11, 1, 15, 0, NY)
    assert hm(r) == (11, 1, 1, 0)
    assert r.offset_label == "UTC-05:00"


def test_uk_spring_forward_day():
    # 2026-03-29 10:00 JST = 01:00 UTC = 02:00 BST (01:00-02:00 skipped)
    r = conv("Asia/Tokyo", 2026, 3, 29, 10, 0, LONDON)
    assert hm(r) == (3, 29, 2, 0)
    assert r.offset_label == "UTC+01:00"


def test_sydney_dst_end_day():
    # Sydney DST ends Sun 2026-04-05 (03:00 AEDT -> 02:00 AEST).
    # Tokyo 2026-04-05 10:00 JST = 01:00 UTC = 11:00 AEST.
    r = conv("Asia/Tokyo", 2026, 4, 5, 10, 0, SYDNEY)
    assert hm(r) == (4, 5, 11, 0)
    assert r.offset_label == "UTC+10:00"


# --- wall-clock classification (gap / ambiguous) ----------------------

def test_classify_gap_new_york():
    naive = datetime(2026, 3, 8, 2, 30)
    assert tzcore.classify_local("America/New_York", naive) == "gap"


def test_classify_ambiguous_new_york():
    naive = datetime(2026, 11, 1, 1, 30)
    assert tzcore.classify_local("America/New_York", naive) == "ambiguous"


def test_classify_normal():
    assert tzcore.classify_local("America/New_York",
                                 datetime(2026, 1, 15, 12, 0)) == "normal"
    assert tzcore.classify_local("Asia/Tokyo",
                                 datetime(2026, 3, 8, 2, 30)) == "normal"


def test_classify_gap_london():
    naive = datetime(2026, 3, 29, 1, 30)
    assert tzcore.classify_local("Europe/London", naive) == "gap"


# --- holidays: substitute / observed ---------------------------------

def test_japan_substitute_holiday_2026():
    # 2026-05-03 (Constitution Day) is a Sunday; with May 4 and 5 also
    # holidays, Wednesday 2026-05-06 is the substitute holiday.
    assert tzcore.holiday_on("JP", date(2026, 5, 6)) is not None


def test_us_observed_christmas_2026():
    # Christmas 2026 falls on Friday; the federal holiday is the day
    # itself (no shift needed). Thanksgiving: 4th Thursday of Nov.
    assert tzcore.holiday_on("US", date(2026, 11, 26)) is not None


def test_nepal_weekend_is_saturday_only():
    # Nepal's weekly holiday is Saturday only.
    assert tzcore.is_weekend((5,), date(2026, 1, 17))       # Saturday
    assert not tzcore.is_weekend((5,), date(2026, 1, 18))   # Sunday


# --- candidate slots: more shapes -------------------------------------

def test_slots_multi_day_count():
    sg = P("SG", "Singapore", "Asia/Singapore")
    slots = tzcore.find_candidate_slots(
        TOKYO, sg, date(2026, 1, 19), 3, duration_min=60, max_results=200)
    days = {s.own_start.date() for s in slots}
    assert days == {date(2026, 1, 19), date(2026, 1, 20), date(2026, 1, 21)}
    # 10:00-17:00 starts in 30-min steps = 15 per day
    assert len(slots) == 45


def test_slots_none_when_partner_always_night():
    # Tokyo 09:00-18:00 vs New York 09:00-18:00 never overlap.
    slots = tzcore.find_candidate_slots(
        TOKYO, NY, date(2026, 1, 19), 5, duration_min=30, max_results=200)
    assert slots == []


def test_slots_partner_shifted_hours():
    # London partner working 08:00-17:00 in summer (BST): overlap with
    # Tokyo 09:00-18:00 starts at 16:00 JST (= 08:00 BST).
    london_early = Partner(name="London early", country_code="GB",
                           city="London", zone="Europe/London",
                           work_start="08:00", work_end="17:00")
    slots = tzcore.find_candidate_slots(
        TOKYO, london_early, date(2026, 7, 6), 1, duration_min=60)
    assert slots
    assert slots[0].own_start.hour == 16
    assert all(s.partner_start.hour >= 8 for s in slots)
