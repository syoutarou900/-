# -*- coding: utf-8 -*-
"""Modern flat theme for RedactShot (dark slate + magenta identity).

2026 design refresh: bundled fonts (Inter + Noto Sans JP, see
fonts.py), flat buttons with 10 px radii and role colours (magenta
primary, white secondary), custom-drawn combo chevrons and checkbox
indicators (assets/, drawn with QPainter — no emoji glyphs), slim
scrollbars, and card-style panels. Palette + stylesheet are applied
at application level from main() BEFORE the main window is built.
"""

import os

import fonts as _fonts

BG = "#ECEEF3"             # soft light ground
PANEL = "#FFFFFF"
INK = "#232838"
SUBINK = "#6B7280"
ACCENT = "#D6336C"         # magenta (primary)
ACCENT_DEEP = "#A61E4D"
ACCENT_HOVER = "#C2255C"
ACCENT_SOFT = "#FCE4EE"
ACCENT_WASH = "#FFF7FA"
LINE = "#D9DCE4"
LINE_STRONG = "#C3C8D4"
HEADER = "#1E2432"         # dark slate
HEADER_SUB = "#C3C9D9"

UI_FAMILY_CSS = ('"Inter", "Noto Sans JP", "Segoe UI", '
                 '"Hiragino Sans", sans-serif')


def _asset(name):
    path = os.path.join(_fonts.base_dir(), "assets", name)
    return path.replace(os.sep, "/")


def stylesheet():
    chev = _asset("chevron-down.png")
    chev_hot = _asset("chevron-down-hot.png")
    chk_off = _asset("check-off.png")
    chk_off_h = _asset("check-off-hover.png")
    chk_on = _asset("check-on.png")
    chk_on_h = _asset("check-on-hover.png")
    chk_off_d = _asset("check-off-dis.png")
    chk_on_d = _asset("check-on-dis.png")
    return f"""
QMainWindow {{ background: {BG}; }}
QLabel {{ color: {INK}; }}
QPushButton {{
    background: {PANEL}; border: 1px solid {LINE}; border-radius: 10px;
    padding: 7px 14px; font-weight: 600; color: {INK};
}}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT_DEEP}; background: {ACCENT_WASH}; }}
QPushButton:pressed {{ background: {ACCENT_SOFT}; }}
QPushButton:checked {{ background: {ACCENT}; border-color: {ACCENT}; color: #FFFFFF; }}
QPushButton:disabled {{ color: #9AA0B0; border-color: #E3E5EC; background: #F4F5F8; }}
QPushButton.primary {{
    background: {ACCENT}; border: 1px solid {ACCENT}; color: #FFFFFF; font-weight: 700;
}}
QPushButton.primary:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; color: #FFFFFF; }}
QPushButton.primary:pressed {{ background: {ACCENT_DEEP}; border-color: {ACCENT_DEEP}; }}
QComboBox {{
    background: {PANEL}; border: 1px solid {LINE}; border-radius: 10px;
    padding: 6px 10px; font-weight: 600; color: {INK};
}}
QComboBox:hover {{ border-color: {LINE_STRONG}; }}
QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url({chev}); width: 12px; height: 12px; }}
QComboBox::down-arrow:hover {{ image: url({chev_hot}); }}
QComboBox QAbstractItemView {{
    background: {PANEL}; border: 1px solid {LINE}; border-radius: 8px;
    selection-background-color: {ACCENT_SOFT}; selection-color: {INK};
    padding: 4px; outline: none;
}}
QLineEdit {{
    background: {PANEL}; border: 1px solid {LINE}; border-radius: 10px; padding: 6px 10px;
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QCheckBox {{ font-weight: 600; spacing: 7px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; image: url({chk_off}); }}
QCheckBox::indicator:hover {{ image: url({chk_off_h}); }}
QCheckBox::indicator:checked {{ image: url({chk_on}); }}
QCheckBox::indicator:checked:hover {{ image: url({chk_on_h}); }}
QCheckBox::indicator:disabled {{ image: url({chk_off_d}); }}
QCheckBox::indicator:checked:disabled {{ image: url({chk_on_d}); }}
QListWidget {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 10px; padding: 4px; }}
QListWidget::item {{ padding: 4px 6px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {ACCENT_SOFT}; color: {INK}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #C6CAD4; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #A8ACBC; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #C6CAD4; border-radius: 5px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: #A8ACBC; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSplitter::handle {{ background: transparent; width: 6px; }}
QDialog {{ background: {BG}; }}
"""


def apply_theme(app) -> None:
    """Apply palette + stylesheet (call before building widgets)."""
    from PySide6.QtGui import QColor, QPalette
    _fonts.register_fonts()
    pal = app.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor(BG))
    pal.setColor(QPalette.ColorRole.Base, QColor(PANEL))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(INK))
    pal.setColor(QPalette.ColorRole.Text, QColor(INK))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet())
