# -*- coding: utf-8 -*-
"""Two switchable themes for GlobalHours.

Dark (default): a deep-indigo "night sky" with amber sunlight —
partner time bands are drawn on a night ground and business hours
glow amber like sunlight.

Light: a clean "daytime sky" for bright offices and anyone who
finds dark screens hard to read — near-white panels, dark slate
text, a brighter sky gradient in the bands and a strong orange
segment (with an outline) for business hours. It is a designed
palette, not a colour inversion of the dark one.

The user switches themes with one header button; the choice is
saved in the app state and restored on the next launch. Switching
re-applies the stylesheet and repaints in place — no restart.

Colour values are looked up dynamically: ``theme.BG`` etc. always
return the ACTIVE palette's value (module __getattr__), so widgets
that read them at build/refresh time follow the current theme.
Bundled fonts (Inter + Noto Sans JP, see fonts.py), flat buttons
with 10 px radii, custom-drawn combo chevrons and checkbox
indicators (assets/, with "-lt" variants for the light theme),
slim scrollbars.
"""

import os

import fonts as _fonts

DARK = {
    "name": "dark",
    "BG": "#0C1230",            # deep indigo night sky
    "BG_DEEP": "#080D24",
    "PANEL": "#171F47",         # band label / card ground
    "PANEL_SOFT": "#1E2757",
    "INK": "#EDF1FF",
    "SUBINK": "#9AA7D6",
    "ACCENT": "#F5A623",        # amber sunlight (primary)
    "ACCENT_DEEP": "#C77F0A",
    "ACCENT_HOVER": "#FFB93E",
    "ACCENT_SOFT": "#4A3A14",
    "ACCENT_WASH": "#232A55",
    "BTN_HOVER_TEXT": "#FFB93E",
    "LINE": "#2E3A6E",
    "LINE_STRONG": "#46548F",
    "HEADER": "#080D24",
    "HEADER_INK": "#FFFFFF",
    "HEADER_SUB": "#8E9CC9",
    "OK_GREEN": "#3ED598",
    "WARN_AMBER": "#FFB93E",
    "BAD_RED": "#FF9D9D",
    "STATUS_OK": "#3ED598",
    "STATUS_OUT": "#FFB93E",
    "STATUS_OFF": "#FF9D9D",
    "BTN_DIS_TEXT": "#5D6890",
    "BTN_DIS_BORDER": "#232C58",
    "BTN_DIS_BG": "#141B3E",
    "SCROLL": "#3A477A",
    "SCROLL_HOVER": "#55639C",
    "SLIDER_HANDLE_BORDER": "#FFE1A8",
    "PRIMARY_TEXT": "#1A1206",
    "ASSET_SUFFIX": "",
    # --- band painting (see bands.py) ---
    "BAND_STOPS": [
        (0.0, "#0F1734"), (4.5, "#121B40"), (6.3, "#5C3E63"),
        (7.6, "#D9825F"), (9.0, "#7FB2E8"), (13.0, "#A5CFF5"),
        (16.5, "#7FB2E8"), (18.2, "#E08A4C"), (19.6, "#463A6E"),
        (21.0, "#131B3D"), (24.0, "#0D1330"),
    ],
    "BAND_AMBER": "#F5A623",
    "BAND_AMBER_LIGHT": "#FFCF6B",
    "BAND_AMBER_DEEP": "#D98E04",
    "BAND_SEG_PEN": None,
    "BAND_TICK": (255, 255, 255, 90),
    "BAND_TICK_TEXT": (255, 255, 255, 170),
    "BAND_DIM": (5, 8, 22, 150),
    "BAND_BADGE_BG": (5, 8, 22, 228),
    "BAND_BADGE_TEXT": (237, 241, 255, 235),
    "BAND_BADGE_TEXT_DIM": "#FFFFFF",
    "BAND_FRAME": "#2E3A6E",
}

LIGHT = {
    "name": "light",
    "BG": "#EFF4FC",            # pale daytime-sky ground
    "BG_DEEP": "#E2EAF8",
    "PANEL": "#FFFFFF",         # band label / card ground
    "PANEL_SOFT": "#FFFFFF",
    "INK": "#182242",           # dark slate-navy text
    "SUBINK": "#4E5D85",
    "ACCENT": "#F5A623",        # amber (primary buttons)
    "ACCENT_DEEP": "#C77F0A",
    "ACCENT_HOVER": "#FFB93E",
    "ACCENT_SOFT": "#FFE3AC",
    "ACCENT_WASH": "#FFF3D3",
    "BTN_HOVER_TEXT": "#9C6A02",
    "LINE": "#C2D1EC",
    "LINE_STRONG": "#8FA5CF",
    "HEADER": "#FFFFFF",
    "HEADER_INK": "#182242",
    "HEADER_SUB": "#4E5D85",
    "OK_GREEN": "#0B8A5F",
    "WARN_AMBER": "#9C6A02",
    "BAD_RED": "#C22418",
    "STATUS_OK": "#0B8A5F",
    "STATUS_OUT": "#9C6A02",
    "STATUS_OFF": "#C22418",
    "BTN_DIS_TEXT": "#9AA7C4",
    "BTN_DIS_BORDER": "#D5DEEF",
    "BTN_DIS_BG": "#EDF1F9",
    "SCROLL": "#B4C3E0",
    "SCROLL_HOVER": "#8FA5CF",
    "SLIDER_HANDLE_BORDER": "#C77F0A",
    "PRIMARY_TEXT": "#1A1206",
    "ASSET_SUFFIX": "-lt",
    # --- band painting: a brighter sky, strong orange segment ---
    "BAND_STOPS": [
        (0.0, "#39466E"), (4.5, "#42538A"), (6.3, "#D98A6C"),
        (7.6, "#F7B26B"), (9.0, "#8FC7F7"), (13.0, "#C4E6FF"),
        (16.5, "#8FC7F7"), (18.2, "#F79E57"), (19.6, "#8A76B8"),
        (21.0, "#4A5B96"), (24.0, "#3C4A78"),
    ],
    "BAND_AMBER": "#FFAE1A",
    "BAND_AMBER_LIGHT": "#FFC94D",
    "BAND_AMBER_DEEP": "#E8890C",
    "BAND_SEG_PEN": (146, 64, 14, 170),
    "BAND_TICK": (255, 255, 255, 180),
    "BAND_TICK_TEXT": (255, 255, 255, 240),
    "BAND_DIM": (240, 245, 253, 168),
    "BAND_BADGE_BG": (255, 255, 255, 245),
    "BAND_BADGE_TEXT": (51, 64, 107, 255),
    "BAND_BADGE_TEXT_DIM": "#C22418",
    "BAND_FRAME": "#A9BBDD",
}

PALETTES = {"dark": DARK, "light": LIGHT}
THEME_NAMES = ("dark", "light")
_state = {"name": "dark"}

UI_FAMILY_CSS = ('"Inter", "Noto Sans JP", "Segoe UI", '
                 '"Hiragino Sans", sans-serif')


def current_name() -> str:
    return _state["name"]


def palette() -> dict:
    return PALETTES[_state["name"]]


def __getattr__(name):
    """Dynamic colour lookup: theme.BG -> active palette value."""
    pal = PALETTES[_state["name"]]
    if name in pal:
        return pal[name]
    raise AttributeError(f"module 'theme' has no attribute {name!r}")


def _asset(name):
    path = os.path.join(_fonts.base_dir(), "assets", name)
    return path.replace(os.sep, "/")


def stylesheet(pal=None):
    if pal is None:
        pal = palette()
    sfx = pal["ASSET_SUFFIX"]
    chev = _asset(f"chevron-down{sfx}.png")
    chev_hot = _asset(f"chevron-down-hot{sfx}.png")
    chk_off = _asset(f"check-off{sfx}.png")
    chk_off_h = _asset(f"check-off-hover{sfx}.png")
    chk_on = _asset(f"check-on{sfx}.png")
    chk_on_h = _asset(f"check-on-hover{sfx}.png")
    chk_off_d = _asset(f"check-off-dis{sfx}.png")
    chk_on_d = _asset(f"check-on-dis{sfx}.png")
    BG = pal["BG"]; PANEL = pal["PANEL"]; PANEL_SOFT = pal["PANEL_SOFT"]
    INK = pal["INK"]; LINE = pal["LINE"]; LINE_STRONG = pal["LINE_STRONG"]
    ACCENT = pal["ACCENT"]; ACCENT_DEEP = pal["ACCENT_DEEP"]
    ACCENT_HOVER = pal["ACCENT_HOVER"]; ACCENT_SOFT = pal["ACCENT_SOFT"]
    ACCENT_WASH = pal["ACCENT_WASH"]; PRIMARY_TEXT = pal["PRIMARY_TEXT"]
    return f"""
QMainWindow {{ background: {BG}; }}
QWidget {{ color: {INK}; }}
QLabel {{ color: {INK}; }}
QPushButton {{
    background: {PANEL_SOFT}; border: 1px solid {LINE}; border-radius: 10px;
    padding: 9px 18px; font-size: 15px; font-weight: 600; color: {INK};
}}
QPushButton:hover {{ border-color: {ACCENT}; color: {pal["BTN_HOVER_TEXT"]}; background: {ACCENT_WASH}; }}
QPushButton:pressed {{ background: {ACCENT_SOFT}; }}
QPushButton:checked {{ background: {ACCENT}; border-color: {ACCENT}; color: {PRIMARY_TEXT}; }}
QPushButton:disabled {{ color: {pal["BTN_DIS_TEXT"]}; border-color: {pal["BTN_DIS_BORDER"]}; background: {pal["BTN_DIS_BG"]}; }}
QPushButton.primary {{
    background: {ACCENT}; border: 1px solid {ACCENT}; color: {PRIMARY_TEXT}; font-weight: 700;
}}
QPushButton.primary:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; color: {PRIMARY_TEXT}; }}
QPushButton.primary:pressed {{ background: {ACCENT_DEEP}; border-color: {ACCENT_DEEP}; }}
QComboBox {{
    background: {PANEL_SOFT}; border: 1px solid {LINE}; border-radius: 10px;
    padding: 8px 12px; font-size: 15px; font-weight: 600; color: {INK};
}}
QComboBox:hover {{ border-color: {LINE_STRONG}; }}
QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url({chev}); width: 12px; height: 12px; }}
QComboBox::down-arrow:hover {{ image: url({chev_hot}); }}
QComboBox QAbstractItemView {{
    background: {PANEL}; border: 1px solid {LINE}; border-radius: 8px;
    selection-background-color: {ACCENT_SOFT}; selection-color: {INK};
    padding: 4px; outline: none; font-size: 14px;
}}
QLineEdit, QDateEdit, QTimeEdit, QDateTimeEdit, QSpinBox {{
    background: {PANEL_SOFT}; border: 1px solid {LINE}; border-radius: 10px;
    padding: 8px 12px; font-size: 15px; color: {INK};
}}
QLineEdit:focus, QDateEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}
QTextEdit {{
    background: {PANEL}; border: 1px solid {LINE}; border-radius: 10px; padding: 10px 12px;
    font-size: 14px; color: {INK};
}}
QTextEdit:focus {{ border-color: {ACCENT}; }}
QCheckBox {{ font-size: 15px; font-weight: 600; spacing: 7px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; image: url({chk_off}); }}
QCheckBox::indicator:hover {{ image: url({chk_off_h}); }}
QCheckBox::indicator:checked {{ image: url({chk_on}); }}
QCheckBox::indicator:checked:hover {{ image: url({chk_on_h}); }}
QCheckBox::indicator:disabled {{ image: url({chk_off_d}); }}
QCheckBox::indicator:checked:disabled {{ image: url({chk_on_d}); }}
QSlider::groove:horizontal {{
    height: 6px; border-radius: 3px; background: {LINE};
}}
QSlider::handle:horizontal {{
    width: 18px; height: 18px; margin: -6px 0; border-radius: 9px;
    background: {ACCENT}; border: 2px solid {pal["SLIDER_HANDLE_BORDER"]};
}}
QSlider::sub-page:horizontal {{ background: {ACCENT_DEEP}; border-radius: 3px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {pal["SCROLL"]}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {pal["SCROLL_HOVER"]}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {pal["SCROLL"]}; border-radius: 5px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {pal["SCROLL_HOVER"]}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QDialog {{ background: {BG}; }}
QToolTip {{ background: {PANEL}; color: {INK}; border: 1px solid {LINE}; font-size: 13px; padding: 5px 9px; }}
"""


def apply_theme(app, name: str = "dark") -> None:
    """Apply the named palette + stylesheet (before building widgets,
    and again in place when the user toggles the theme)."""
    from PySide6.QtGui import QColor, QPalette
    if name not in PALETTES:
        name = "dark"
    _state["name"] = name
    pal = PALETTES[name]
    _fonts.register_fonts()
    qt_pal = app.palette()
    qt_pal.setColor(QPalette.ColorRole.Window, QColor(pal["BG"]))
    qt_pal.setColor(QPalette.ColorRole.Base, QColor(pal["PANEL"]))
    qt_pal.setColor(QPalette.ColorRole.WindowText, QColor(pal["INK"]))
    qt_pal.setColor(QPalette.ColorRole.Text, QColor(pal["INK"]))
    qt_pal.setColor(QPalette.ColorRole.Highlight, QColor(pal["ACCENT"]))
    qt_pal.setColor(QPalette.ColorRole.HighlightedText,
                    QColor(pal["PRIMARY_TEXT"]))
    app.setPalette(qt_pal)
    app.setStyleSheet(stylesheet(pal))
