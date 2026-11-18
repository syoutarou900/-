# -*- coding: utf-8 -*-
"""Application name - THE single place that defines the product name.

- Japanese UI title: UniList
- All other languages' UI title: UniList
- EXE name: UniList.exe / ZIP names: UniList-Windows.zip,
  UniList-Source.zip (all derived from APP_FILE_STEM).
"""

APP_ID = "UniList"
APP_FILE_STEM = "UniList"
APP_NAME_EN = "UniList"
APP_NAME_JA = "UniList"

APP_DISPLAY = {
    "ja": "UniList",
}

APP_VERSION = "1.0.0"


def display_name(lang):
    """Japanese UI shows UniList; every other language
    shows UniList."""
    return APP_DISPLAY.get(lang, APP_NAME_EN)
