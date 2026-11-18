# -*- coding: utf-8 -*-
"""Bundled fonts: Inter (Latin / digits) + Noto Sans JP (Japanese).

The app ships its own fonts so the UI looks the same (and modern) on
every machine instead of depending on whatever the OS happens to
offer.  Both fonts are SIL OFL 1.1; see fonts/FONTS.txt.

Registration happens once at startup via QFontDatabase.  The UI font
is then set per language: Qt walks the family list per glyph, so
Latin and digits render in Inter while Japanese falls through to
Noto Sans JP in the same widget.  Arabic keeps Inter for Latin and
uses a Naskh-style system fallback for Arabic script (the task spec
allows a system fallback there); Chinese / Korean use the bundled
fonts first, then the platform's own CJK fonts.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtGui import QFont, QFontDatabase

_registered = False

# Base UI size.  QSS rules refine per-widget sizes on top of this;
# the point size only matters where QSS does not set one.
BASE_POINT_SIZE = 11.0

# Role weights.  Only weights that exist as real faces in BOTH
# bundled families are used for the roles below: Inter ships
# Regular / Medium / SemiBold / Bold and Noto Sans JP ships
# Regular / Medium / Bold.  Asking Qt for a weight with no real
# face (e.g. 800) makes the engine synthesise a smeared fake bold,
# so headings use Bold (700) and buttons SemiBold (600 — a real
# Inter face; Noto Sans JP resolves it to its Bold face).
ROLE_WEIGHTS = {
    "body": QFont.Weight.Normal,        # 400 — labels, body text
    "medium": QFont.Weight.Medium,      # 500 — secondary emphasis
    "button": QFont.Weight.DemiBold,    # 600 — buttons, status
    "heading": QFont.Weight.Bold,       # 700 — headings, clock
}

_TABULAR_TAG = None


def _tabular_tag():
    global _TABULAR_TAG
    if _TABULAR_TAG is None:
        _TABULAR_TAG = QFont.Tag.fromString("tnum")
    return _TABULAR_TAG


def polish_font(font: QFont, *, tabular: bool = False) -> QFont:
    """Apply the app-wide rendering-quality settings to `font`:
    explicit antialiasing (PreferAntialias + PreferQuality, full
    hinting) instead of the platform default strategy, and — for
    clocks and time ranges — the OpenType "tnum" feature so every
    digit takes the same width and times line up in columns."""
    font.setStyleStrategy(
        QFont.StyleStrategy.PreferAntialias
        | QFont.StyleStrategy.PreferQuality)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    if tabular:
        font.setFeature(_tabular_tag(), 1)
    return font


def make_font(lang: str, *, point_size: float | None = None,
              pixel_size: int | None = None,
              weight: QFont.Weight | None = None,
              tabular: bool = False) -> QFont:
    """Build a polished font on the family stack for `lang`."""
    font = QFont()
    font.setFamilies(stack_for(lang))
    if point_size is not None:
        font.setPointSizeF(point_size)
    if pixel_size is not None:
        font.setPixelSize(pixel_size)
    if weight is not None:
        font.setWeight(weight)
    return polish_font(font, tabular=tabular)

_INTER = "Inter"
_NOTO_JP = "Noto Sans JP"

# Family stacks per UI language, most-preferred first.  Qt tries each
# family in order until it finds the glyph it needs.
STACKS = {
    "ja": [_INTER, _NOTO_JP, "Yu Gothic UI", "Hiragino Sans",
           "Noto Sans CJK JP"],
    "zh": [_INTER, _NOTO_JP, "Microsoft YaHei UI", "PingFang SC",
           "Noto Sans CJK SC"],
    "ko": [_INTER, _NOTO_JP, "Malgun Gothic", "Apple SD Gothic Neo",
           "Noto Sans CJK KR"],
    "ar": [_INTER, "Noto Naskh Arabic", "Amiri", "Segoe UI", "Tahoma"],
}
GENERIC_STACK = [_INTER, _NOTO_JP, "Segoe UI", "Hiragino Sans",
                 "Noto Sans CJK JP", "Noto Sans CJK SC",
                 "Noto Sans CJK KR", "DejaVu Sans"]


def base_dir() -> str:
    """Directory that holds fonts/ and assets/ (source tree, or the
    PyInstaller _internal folder when frozen)."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS",
                       os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.abspath(__file__))


def fonts_dir() -> str:
    return os.path.join(base_dir(), "fonts")


def assets_dir() -> str:
    return os.path.join(base_dir(), "assets")


def register_fonts() -> None:
    """Load every bundled font file into Qt (idempotent)."""
    global _registered
    if _registered:
        return
    _registered = True
    folder = fonts_dir()
    if not os.path.isdir(folder):
        return
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith((".ttf", ".otf", ".ttc")):
            # A failed load is not fatal: Qt falls back to system
            # fonts, which is exactly the old behaviour.
            QFontDatabase.addApplicationFont(os.path.join(folder, name))


def stack_for(lang: str) -> list:
    return list(STACKS.get(lang, GENERIC_STACK))


def apply_language_font(app, lang: str) -> None:
    """Set the application font to the stack for `lang`."""
    register_fonts()
    font = QFont()
    font.setFamilies(stack_for(lang))
    font.setPointSizeF(BASE_POINT_SIZE)
    polish_font(font)
    app.setFont(font)
