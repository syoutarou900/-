# -*- coding: utf-8 -*-
"""Centralised app identity for RedactShot.

The display name lives ONLY here. Other modules must import from this
file and must not hard-code the display name elsewhere. File names and
the EXE name keep the ASCII form "RedactShot".
"""

APP_ID = "RedactShot"
FILE_BASE = "RedactShot"
APP_NAME_EN = "RedactShot"
APP_NAME_JA = "スクショ安心フィルター"
VERSION = "1.0.0"


def display_name(lang: str) -> str:
    """Return the localised display name for *lang*.

    Japanese uses the Japanese name; every other language uses English.
    """
    if lang == "ja":
        return APP_NAME_JA
    return APP_NAME_EN
