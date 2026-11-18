# -*- coding: utf-8 -*-
"""Application name - THE single place that defines the product name.

Final name (decided by the user, 2026-11-14):
- Japanese UI title: たしかめーる
- All other languages' UI title: TashikaMail
- EXE name: TashikaMail.exe / ZIP names: TashikaMail-Windows.zip,
  TashikaMail-Source.zip (all derived from APP_FILE_STEM).
"""

APP_ID = "TashikaMail"
APP_FILE_STEM = "TashikaMail"
APP_NAME_EN = "TashikaMail"
APP_NAME_JA = "たしかめーる"

APP_DISPLAY = {
    "ja": "たしかめーる",
}

APP_VERSION = "1.1.0"


def display_name(lang):
    """Japanese UI shows たしかめーる; every other language TashikaMail."""
    return APP_DISPLAY.get(lang, APP_NAME_EN)
