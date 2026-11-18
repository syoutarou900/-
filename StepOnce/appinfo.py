# -*- coding: utf-8 -*-
"""Application name - THE single place that defines the product name.

Formal name decided by the user on 2026-11-15: StepOnce.
(The former working title was replaced everywhere user-visible;
"ManualMaker" is already used by an existing iOS manual-creation app,
so it must not be used as the product name.)

- Japanese UI title: 一回やれば手順書
- All other languages' UI title: StepOnce
- EXE name: StepOnce.exe / ZIP names: StepOnce-Windows.zip,
  StepOnce-Source.zip (all derived from APP_FILE_STEM / FILE_BASE).
"""

APP_ID = "StepOnce"
APP_FILE_STEM = "StepOnce"
FILE_BASE = "StepOnce"
APP_NAME_EN = "StepOnce"
APP_NAME_JA = "一回やれば手順書"

APP_DISPLAY = {
    "ja": APP_NAME_JA,
}

APP_VERSION = "1.0.0"


def display_name(lang):
    """Japanese UI shows the Japanese name; every other language
    shows the English name."""
    return APP_DISPLAY.get(lang, APP_NAME_EN)
