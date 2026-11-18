# -*- coding: utf-8 -*-
"""Centralised app identity for the timezone / business-hours checker.

The display name lives ONLY here. Other modules must import from this
file and must not hard-code the display name elsewhere.

FORMAL NAME: "GlobalHours" (decided by the user on 2026-11-15).
The idea-sheet name "TimeZone Guard" must NOT be used (same-name
products exist). File names and the EXE name keep the ASCII form in
FILE_BASE.
"""

APP_ID = "GlobalHours"
FILE_BASE = "GlobalHours"
APP_NAME_EN = "GlobalHours"
APP_NAME_JA = "タイムゾーン・営業時間チェッカー"
VERSION = "1.0.0"


def display_name(lang: str) -> str:
    """Return the localised display name for *lang*.

    Japanese uses the Japanese name; every other language uses English.
    """
    if lang == "ja":
        return APP_NAME_JA
    return APP_NAME_EN
