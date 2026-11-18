# -*- coding: utf-8 -*-
"""Single source of truth for the app's names.

Rename the app by editing ONLY this file: every display string, file
name, data folder and bundle name derives from the values below.
"""

APP_ID = "VersionDetective"
APP_NAME_EN = "VersionDetective"
APP_NAME_JA = "バージョン探偵"

# File-name base used for the EXE, ZIPs, launcher scripts and .app bundle.
FILE_BASE = "VersionDetective"

VERSION = "1.0.0"


def display_name(lang: str) -> str:
    """User-visible app name in the given UI language."""
    if lang == "ja":
        return APP_NAME_JA
    return APP_NAME_EN
