# -*- coding: utf-8 -*-
"""Core timezone / business-hours logic for GlobalHours.

Everything here is pure computation on bundled data:
  * timezone maths  -> zoneinfo + tzdata (IANA database)
  * public holidays -> the `holidays` library's bundled country data
No network access is needed or used.

The app never sends anything. It only *checks* and *proposes*;
the human decides when to actually contact the partner.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import holidays as _holidays_lib

import appinfo
import data as master


# ----------------------------------------------------------------------
# Data model
# ----------------------------------------------------------------------

@dataclass
class Partner:
    name: str
    country_code: str          # ISO alpha-2, key into master.COUNTRIES
    city: str
    zone: str                  # IANA timezone name
    work_start: str = "09:00"  # local wall time "HH:MM"
    work_end: str = "18:00"
    lang: str = ""             # proposal language override; "" = auto

    @property
    def country(self):
        return master.country_by_code(self.country_code)

    @property
    def weekend(self):
        c = self.country
        return c["weekend"] if c else master.WEEKEND_SAT_SUN

    @property
    def proposal_lang(self):
        if self.lang:
            return self.lang
        c = self.country
        return c["lang"] if c else "en"


@dataclass
class OwnSettings:
    zone: str = "Asia/Tokyo"
    country_code: str = "JP"
    work_start: str = "09:00"
    work_end: str = "18:00"

    @property
    def country(self):
        return master.country_by_code(self.country_code)

    @property
    def weekend(self):
        c = self.country
        return c["weekend"] if c else master.WEEKEND_SAT_SUN


@dataclass
class AppState:
    own: OwnSettings = field(default_factory=OwnSettings)
    partners: list = field(default_factory=list)   # list[Partner]
    lang: str = "ja"                               # UI language
    theme: str = "dark"                            # "dark" | "light"


# ----------------------------------------------------------------------
# Persistence (per-user app data folder)
# ----------------------------------------------------------------------

def app_data_dir() -> str:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"),
                            "Library", "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
            os.path.expanduser("~"), ".config")
    path = os.path.join(base, appinfo.APP_ID)
    os.makedirs(path, exist_ok=True)
    return path


def settings_path() -> str:
    return os.path.join(app_data_dir(), "settings.json")


def save_state(state: AppState) -> None:
    payload = {
        "own": asdict(state.own),
        "partners": [asdict(p) for p in state.partners],
        "lang": state.lang,
        "theme": state.theme if state.theme in ("dark", "light")
        else "dark",
    }
    with open(settings_path(), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def load_state() -> AppState:
    try:
        with open(settings_path(), "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        own = OwnSettings(**payload.get("own", {}))
        partners = [Partner(**p) for p in payload.get("partners", [])]
        saved_theme = payload.get("theme", "dark")
        return AppState(own=own, partners=partners,
                        lang=payload.get("lang", "ja"),
                        theme=saved_theme if saved_theme in ("dark", "light")
                        else "dark")
    except Exception:
        return AppState()


# ----------------------------------------------------------------------
# Holiday lookup (bundled data, cached per country+year)
# ----------------------------------------------------------------------

@lru_cache(maxsize=256)
def _holiday_map(country_code: str, year: int) -> dict:
    """{date: name} for one country and year. Empty dict when the
    country has no bundled holiday data."""
    if not country_code:
        return {}
    try:
        try:
            cal = _holidays_lib.country_holidays(
                country_code, years=year, language="en_US")
        except Exception:
            cal = _holidays_lib.country_holidays(country_code, years=year)
        return {d: str(name) for d, name in cal.items()}
    except Exception:
        return {}


def holiday_on(country_code: str, day: date):
    """Holiday name on *day* in *country_code*, or None."""
    return _holiday_map(country_code, day.year).get(day)


def is_weekend(country_weekend, day: date) -> bool:
    return day.weekday() in country_weekend


# ----------------------------------------------------------------------
# Business-hours judgement
# ----------------------------------------------------------------------

def _parse_hhmm(text: str) -> time:
    hh, mm = text.split(":")
    return time(int(hh), int(mm))


def _within(day: date, local_dt: datetime, start_s: str, end_s: str) -> bool:
    start = datetime.combine(day, _parse_hhmm(start_s))
    end = datetime.combine(day, _parse_hhmm(end_s))
    naive = local_dt.replace(tzinfo=None)
    return start <= naive < end


@dataclass
class CheckResult:
    partner: Partner
    local_dt: datetime          # aware datetime in the partner zone
    offset_label: str           # e.g. "UTC+09:00"
    diff_hours: float           # partner offset minus own offset
    is_weekend: bool
    holiday_name: str | None
    in_business_hours: bool     # time-of-day inside the work window
    ok: bool                    # business day AND inside the window
    dst_change_date: date | None  # nearby DST switch, if any


def utc_offset_label(dt: datetime) -> str:
    off = dt.utcoffset() or timedelta(0)
    total = int(off.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"UTC{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}"


def check_partner(own_dt: datetime, own: OwnSettings,
                  partner: Partner) -> CheckResult:
    """Judge one partner at the aware datetime *own_dt* (own zone)."""
    zone = ZoneInfo(partner.zone)
    local = own_dt.astimezone(zone)
    day = local.date()
    weekend = is_weekend(partner.weekend, day)
    hol = holiday_on(partner.country_code, day)
    in_hours = _within(day, local, partner.work_start, partner.work_end)
    ok = in_hours and not weekend and hol is None
    own_off = own_dt.utcoffset() or timedelta(0)
    loc_off = local.utcoffset() or timedelta(0)
    dst = dst_change_near(partner.zone, day, within_days=7)
    return CheckResult(
        partner=partner, local_dt=local,
        offset_label=utc_offset_label(local),
        diff_hours=(loc_off - own_off).total_seconds() / 3600.0,
        is_weekend=weekend, holiday_name=hol,
        in_business_hours=in_hours, ok=ok, dst_change_date=dst)


# ----------------------------------------------------------------------
# DST transition detection
# ----------------------------------------------------------------------

@lru_cache(maxsize=128)
def _transitions_in_year(zone_name: str, year: int) -> tuple:
    """Dates in *year* on which the zone's UTC offset changes."""
    zone = ZoneInfo(zone_name)
    found = []
    prev = None
    day = date(year, 1, 1)
    while day.year == year:
        probe = datetime.combine(day, time(12, 0), tzinfo=zone)
        off = probe.utcoffset()
        if prev is not None and off != prev:
            found.append(day)
        prev = off
        day += timedelta(days=1)
    return tuple(found)


def dst_change_near(zone_name: str, day: date, within_days: int = 7):
    """A DST switch date within +/- *within_days* of *day*, or None."""
    for year in (day.year - 1, day.year, day.year + 1):
        for t in _transitions_in_year(zone_name, year):
            if abs((t - day).days) <= within_days:
                return t
    return None


# ----------------------------------------------------------------------
# Candidate time slots that fit BOTH sides' business hours
# ----------------------------------------------------------------------

@dataclass
class Slot:
    own_start: datetime
    own_end: datetime
    partner_start: datetime
    partner_end: datetime


def _business_day(country_code: str, weekend, day: date) -> bool:
    return (not is_weekend(weekend, day)
            and holiday_on(country_code, day) is None)


def find_candidate_slots(own: OwnSettings, partner: Partner,
                         start_day: date, num_days: int,
                         duration_min: int = 60,
                         step_min: int = 30,
                         max_results: int = 60) -> list:
    """Slots (in the own zone) whose full duration fits inside both
    sides' business hours on business days (no weekend / holiday)."""
    own_zone = ZoneInfo(own.zone)
    p_zone = ZoneInfo(partner.zone)
    results: list[Slot] = []
    duration = timedelta(minutes=duration_min)
    step = timedelta(minutes=step_min)
    for delta in range(num_days):
        day = start_day + timedelta(days=delta)
        if not _business_day(own.country_code, own.weekend, day):
            continue
        start = datetime.combine(day, _parse_hhmm(own.work_start),
                                 tzinfo=own_zone)
        end_limit = datetime.combine(day, _parse_hhmm(own.work_end),
                                     tzinfo=own_zone)
        cur = start
        while cur + duration <= end_limit:
            p_start = cur.astimezone(p_zone)
            p_end = (cur + duration).astimezone(p_zone)
            p_day = p_start.date()
            if (_business_day(partner.country_code, partner.weekend, p_day)
                    and p_end.date() == p_day
                    and _within(p_day, p_start,
                                partner.work_start, partner.work_end)
                    and _within(p_day, p_end - timedelta(seconds=1),
                                partner.work_start, partner.work_end)):
                results.append(Slot(cur, cur + duration, p_start, p_end))
                if len(results) >= max_results:
                    return results
            cur += step
    return results


def classify_local(zone_name: str, naive_dt: datetime) -> str:
    """Classify a wall-clock time in *zone_name*:
    "normal", "gap" (does not exist, spring-forward) or
    "ambiguous" (occurs twice, fall-back)."""
    zone = ZoneInfo(zone_name)
    a0 = naive_dt.replace(tzinfo=zone, fold=0)
    a1 = naive_dt.replace(tzinfo=zone, fold=1)
    if a0.utcoffset() == a1.utcoffset():
        return "normal"
    from datetime import timezone as _tz
    roundtrip = a0.astimezone(_tz.utc).astimezone(zone)
    if roundtrip.replace(tzinfo=None) != naive_dt:
        return "gap"
    return "ambiguous"


def fmt_diff_hours(diff: float) -> str:
    if diff == int(diff):
        return f"{diff:+.0f}h"
    return f"{diff:+.1f}h"
