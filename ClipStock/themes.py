# -*- coding: utf-8 -*-
"""Visual themes for ClipStock: "dark" and "light" (2026 refresh).

Each theme provides the full application stylesheet plus the handful of
colours that Python code applies directly (kind badges / accent bars,
the pinned-row card, the pin star, the status text and the drop
shadows), so a theme switch re-skins every surface consistently.

Typography: the app bundles the Inter typeface (assets/fonts) and
prefers it everywhere; the fallback chain keeps native platforms
looking right (Segoe UI Variable / Segoe UI on Windows, Hiragino on
macOS, Yu Gothic / Noto Sans CJK for Japanese glyphs Inter lacks).
Weights are used deliberately: 600 for titles and primary actions,
500 for buttons and row text, 400 for body copy.
"""

FONT_FAMILIES = [
    "Inter", "Segoe UI Variable Text", "Segoe UI", "Yu Gothic UI",
    "Hiragino Sans", "Noto Sans CJK JP", "Noto Sans",
]
FONT_FAMILY_QSS = ", ".join('"%s"' % f for f in FONT_FAMILIES)

KIND_COLORS_DARK = {
    "url": "#4FB0F5", "email": "#B197FC", "amount": "#FFC53D",
    "date": "#3ED598", "address": "#FF8FBE", "code": "#38D9C4",
    "other": "#A5B4CC",
}
# Deeper, more saturated variants so the badges stay easy to tell apart
# on a white background (badge text switches to white in this theme).
KIND_COLORS_LIGHT = {
    "url": "#0B7CC4", "email": "#7A4FD0", "amount": "#CE7A00",
    "date": "#0C9B6C", "address": "#D6337F", "code": "#0E7C74",
    "other": "#64748B",
}

QSS_DARK = """
QWidget {
    color: #EDF0FA; font-size: 10.5pt; font-family: FONTLIST;
}
QMainWindow, QWidget#centralRoot {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #181C36, stop:1 #101223);
}
QFrame#topCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #2F356B, stop:0.55 #252B57, stop:1 #1E2347);
    border: 1px solid rgba(139, 127, 245, 0.42); border-radius: 16px;
}
QLabel#appTitle { font-size: 16pt; font-weight: 600; color: #FFFFFF; }
QLabel#appSub { color: #A3ACC9; font-size: 9.5pt; }
QLabel#statusDot { font-size: 10.5pt; font-weight: 600; }
QLabel#countLabel { color: #8E97B4; font-size: 9.5pt; }
QLineEdit {
    background: #1E2242; border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 11px; padding: 8px 12px;
    selection-background-color: #5A4FD0; selection-color: #FFFFFF;
}
QLineEdit:focus { border: 1px solid #8B7FF5; background: #222750; }
QComboBox {
    background: #1E2242; border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 11px; padding: 7px 10px; min-width: 90px;
    selection-background-color: #5A4FD0; selection-color: #FFFFFF;
}
QComboBox:focus { border: 1px solid #8B7FF5; }
QComboBox::drop-down {
    subcontrol-origin: padding; subcontrol-position: center right;
    width: 22px; border-left: 1px solid rgba(255, 255, 255, 0.07);
    border-top-right-radius: 10px; border-bottom-right-radius: 10px;
    background: rgba(255, 255, 255, 0.04);
}
QComboBox QAbstractItemView {
    background: #232842; border: 1px solid rgba(255, 255, 255, 0.12);
    selection-background-color: #5A4FD0; selection-color: #FFFFFF;
    outline: none;
}
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #2E345E, stop:1 #262C4E);
    border: 1px solid rgba(255, 255, 255, 0.11); border-radius: 12px;
    padding: 8px 15px; font-weight: 500;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #39406E, stop:1 #2F3760);
    border-color: rgba(139, 127, 245, 0.55);
}
QPushButton:pressed { background: #222845; }
QPushButton:focus { border-color: #8B7FF5; }
QPushButton:disabled { color: #6E7692; background: #20243E; }
QPushButton#accentBtn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #7A68F2, stop:1 #5A45D8);
    border: 1px solid rgba(255, 255, 255, 0.20); color: white;
    font-weight: 600;
}
QPushButton#accentBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #8A79FF, stop:1 #6853E8);
    border-color: rgba(255, 255, 255, 0.32);
}
QPushButton#accentBtn:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #6A58E4, stop:1 #4E3CC4);
}
QPushButton#dangerBtn:hover {
    background: rgba(244, 63, 94, 0.16);
    border-color: rgba(244, 63, 94, 0.50); color: #FDA4AF;
}
QPushButton.chip {
    border-radius: 15px; padding: 6px 13px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.09); color: #C3CADF;
    font-size: 9.5pt; font-weight: 500;
}
QPushButton.chip:hover { background: rgba(255, 255, 255, 0.11); }
QPushButton.chip:checked {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #6D5DF0, stop:1 #4F46A5);
    border-color: rgba(167, 155, 255, 0.65); color: white;
    font-weight: 600;
}
QListWidget {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #1B1F38, stop:1 #161A2E);
    border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 14px;
    outline: none; padding: 5px;
}
QListWidget::item {
    border: 1px solid transparent; border-radius: 12px; margin: 2px 1px;
}
QListWidget::item:selected {
    border-color: rgba(139, 127, 245, 0.65);
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(109, 93, 240, 0.30), stop:1 rgba(109, 93, 240, 0.16));
}
QWidget#rowCard {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #232842, stop:1 #1F2440);
    border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 12px;
}
QWidget#setHeader {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #2C3266, stop:1 #212850);
    border: 1px solid rgba(139, 127, 245, 0.30); border-radius: 12px;
}
QLabel#setHeaderTitle { color: #E4E9FB; font-size: 10pt; font-weight: 600; }
QLabel#setHeaderMeta { color: #8E97B4; font-size: 8.8pt; }
QLabel#pinnedBadge {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #FFD34D, stop:1 #F6AD2A);
    color: #2A1D02; border-radius: 8px;
    padding: 2px 8px; font-size: 8.2pt; font-weight: 600;
}
QLabel#rowText { color: #F2F4FC; font-size: 10.5pt; font-weight: 500; }
QLabel#rowMeta { color: #8E97B4; font-size: 9pt; }
QLabel#kindChip {
    border-radius: 9px; padding: 3px 9px; font-size: 9pt;
    font-weight: 600; color: #10131F;
}
QPushButton.miniBtn {
    border-radius: 8px; padding: 3px 8px; background: transparent;
    border: 1px solid transparent; font-size: 11pt; color: #9AA5C4;
    font-weight: 400;
}
QPushButton.miniBtn:hover {
    background: rgba(255, 255, 255, 0.10);
    border-color: rgba(255, 255, 255, 0.14); color: #fff;
}
QPushButton.miniBtn.on { color: #FFC53D; }
QDialog { background: #161A30; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator {
    width: 18px; height: 18px; border-radius: 6px;
    border: 1px solid #4A5280; background: #1E2242;
}
QCheckBox::indicator:hover { border-color: #8B7FF5; }
QCheckBox::indicator:checked {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #7A68F2, stop:1 #5A45D8);
    border-color: rgba(167, 155, 255, 0.65);
}
QLabel#noteBox {
    background: #1E2242; border: 1px solid rgba(255, 255, 255, 0.09);
    border-radius: 12px; padding: 10px 12px; color: #C6CCE0;
    font-size: 9.5pt;
}
QScrollBar:vertical { background: transparent; width: 9px; margin: 2px; }
QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 0.16); border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: rgba(255, 255, 255, 0.28); }
QScrollBar::handle:vertical:pressed { background: rgba(139, 127, 245, 0.55); }
QScrollBar:horizontal { background: transparent; height: 9px; margin: 2px; }
QScrollBar::handle:horizontal {
    background: rgba(255, 255, 255, 0.16); border-radius: 4px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background: rgba(255, 255, 255, 0.28); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
QMenu {
    background: #232842; border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 10px; padding: 6px;
}
QMenu::item { padding: 7px 24px 7px 12px; border-radius: 7px; }
QMenu::item:selected {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #6D5DF0, stop:1 #4F46A5);
}
QMenu::separator {
    height: 1px; background: rgba(255, 255, 255, 0.09); margin: 5px 8px;
}
QToolTip {
    background: #262B4A; color: #EDF0FA;
    border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 8px;
    padding: 5px 8px;
}
QPlainTextEdit {
    background: #1E2242; border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 11px; padding: 6px;
    selection-background-color: #5A4FD0; selection-color: #FFFFFF;
}
QPlainTextEdit:focus { border: 1px solid #8B7FF5; }
""".replace("FONTLIST", FONT_FAMILY_QSS)

QSS_LIGHT = """
QWidget {
    color: #1E2438; font-size: 10.5pt; font-family: FONTLIST;
}
QMainWindow, QWidget#centralRoot {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #F8F9FC, stop:1 #ECEFF7);
}
QFrame#topCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #FFFFFF, stop:1 #EDF0FA);
    border: 1px solid #D8DEF0; border-radius: 16px;
}
QLabel#appTitle { font-size: 16pt; font-weight: 600; color: #141A2E; }
QLabel#appSub { color: #5C6680; font-size: 9.5pt; }
QLabel#statusDot { font-size: 10.5pt; font-weight: 600; }
QLabel#countLabel { color: #78819B; font-size: 9.5pt; }
QLineEdit {
    background: #FFFFFF; border: 1px solid #D3D9EC; border-radius: 11px;
    padding: 8px 12px; selection-background-color: #C9C2F5;
    selection-color: #1E2438;
}
QLineEdit:focus { border: 1px solid #7C6FF0; }
QComboBox {
    background: #FFFFFF; border: 1px solid #D3D9EC; border-radius: 11px;
    padding: 7px 10px; min-width: 90px;
    selection-background-color: #4F46A5; selection-color: #FFFFFF;
}
QComboBox:focus { border: 1px solid #7C6FF0; }
QComboBox::drop-down {
    subcontrol-origin: padding; subcontrol-position: center right;
    width: 22px; border-left: 1px solid #E4E8F4;
    border-top-right-radius: 10px; border-bottom-right-radius: 10px;
    background: #F4F6FB;
}
QComboBox QAbstractItemView {
    background: #FFFFFF; border: 1px solid #D3D9EC;
    selection-background-color: #4F46A5; selection-color: #FFFFFF;
    outline: none;
}
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #FFFFFF, stop:1 #EDF0F8);
    border: 1px solid #D3D9EC; border-radius: 12px;
    padding: 8px 15px; color: #232941; font-weight: 500;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #FFFFFF, stop:1 #E3E8F6);
    border-color: #A9B4DC;
}
QPushButton:pressed { background: #E4E8F4; }
QPushButton:focus { border-color: #7C6FF0; }
QPushButton:disabled { color: #9AA2B8; background: #EEF0F6; }
QPushButton#accentBtn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #7A68F2, stop:1 #5A45D8);
    border: 1px solid rgba(60, 40, 180, 0.35); color: white;
    font-weight: 600;
}
QPushButton#accentBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #8A79FF, stop:1 #6853E8);
}
QPushButton#accentBtn:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #6A58E4, stop:1 #4E3CC4);
}
QPushButton#dangerBtn:hover {
    background: #FDECEF; border-color: #D98CA0; color: #B03048;
}
QPushButton.chip {
    border-radius: 15px; padding: 6px 13px; background: #EDF0F8;
    border: 1px solid #D8DEF0; color: #4A5470; font-size: 9.5pt;
    font-weight: 500;
}
QPushButton.chip:hover { background: #E1E7F5; }
QPushButton.chip:checked {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #6D5DF0, stop:1 #4F46A5);
    border-color: rgba(60, 40, 180, 0.35); color: white;
    font-weight: 600;
}
QListWidget {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #FFFFFF, stop:1 #FAFBFE);
    border: 1px solid #DCE1F0; border-radius: 14px;
    outline: none; padding: 5px;
}
QListWidget::item {
    border: 1px solid transparent; border-radius: 12px; margin: 2px 1px;
}
QListWidget::item:selected {
    border-color: rgba(109, 93, 240, 0.55);
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(109, 93, 240, 0.14), stop:1 rgba(109, 93, 240, 0.07));
}
QWidget#rowCard {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #FFFFFF, stop:1 #F7F8FC);
    border: 1px solid #E0E5F2; border-radius: 12px;
}
QWidget#setHeader {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #EEF1FA, stop:1 #DFE7F8);
    border: 1px solid #D3DCEF; border-radius: 12px;
}
QLabel#setHeaderTitle { color: #232C4C; font-size: 10pt; font-weight: 600; }
QLabel#setHeaderMeta { color: #66708C; font-size: 8.8pt; }
QLabel#pinnedBadge {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #FFD34D, stop:1 #F6AD2A);
    color: #2A1D02; border-radius: 8px;
    padding: 2px 8px; font-size: 8.2pt; font-weight: 600;
}
QLabel#rowText { color: #1B2136; font-size: 10.5pt; font-weight: 500; }
QLabel#rowMeta { color: #66708C; font-size: 9pt; }
QLabel#kindChip {
    border-radius: 9px; padding: 3px 9px; font-size: 9pt;
    font-weight: 600; color: #FFFFFF;
}
QPushButton.miniBtn {
    border-radius: 8px; padding: 3px 8px; background: transparent;
    border: 1px solid transparent; font-size: 11pt; color: #66708C;
    font-weight: 400;
}
QPushButton.miniBtn:hover {
    background: #E8ECF7; border-color: #C9D2EA; color: #141A2E;
}
QPushButton.miniBtn.on { color: #CE7A00; }
QDialog { background: #F2F4FA; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator {
    width: 18px; height: 18px; border-radius: 6px;
    border: 1px solid #A9B4D4; background: #FFFFFF;
}
QCheckBox::indicator:hover { border-color: #7C6FF0; }
QCheckBox::indicator:checked {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #7A68F2, stop:1 #5A45D8);
    border-color: rgba(60, 40, 180, 0.35);
}
QLabel#noteBox {
    background: #FFFFFF; border: 1px solid #DCE1F0; border-radius: 12px;
    padding: 10px 12px; color: #3C4358; font-size: 9.5pt;
}
QPlainTextEdit {
    background: #FFFFFF; border: 1px solid #D3D9EC; border-radius: 11px;
    padding: 6px; selection-background-color: #C9C2F5;
    selection-color: #1E2438;
}
QPlainTextEdit:focus { border: 1px solid #7C6FF0; }
QScrollBar:vertical { background: transparent; width: 9px; margin: 2px; }
QScrollBar::handle:vertical {
    background: rgba(30, 36, 66, 0.18); border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: rgba(30, 36, 66, 0.30); }
QScrollBar::handle:vertical:pressed { background: rgba(109, 93, 240, 0.45); }
QScrollBar:horizontal { background: transparent; height: 9px; margin: 2px; }
QScrollBar::handle:horizontal {
    background: rgba(30, 36, 66, 0.18); border-radius: 4px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background: rgba(30, 36, 66, 0.30); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
QMenu {
    background: #FFFFFF; border: 1px solid #D8DEF0; padding: 6px;
    color: #232941; border-radius: 10px;
}
QMenu::item { padding: 7px 24px 7px 12px; border-radius: 7px; }
QMenu::item:selected { background: rgba(109, 93, 240, 0.13); color: #232941; }
QMenu::separator {
    height: 1px; background: #E2E7F2; margin: 5px 8px;
}
QToolTip {
    background: #FFFFFF; color: #232941; border: 1px solid #D3D9EC;
    border-radius: 8px; padding: 5px 8px;
}
""".replace("FONTLIST", FONT_FAMILY_QSS)


THEMES = {
    "dark": {
        "qss": QSS_DARK,
        "kind_colors": KIND_COLORS_DARK,
        "pinned_card_qss": (
            "QWidget#rowCard { "
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 #372C10, stop:1 #2A2108); "
            "border: 1px solid #C79A35; border-radius: 12px; }"),
        "pin_on_color": "#FFC53D",
        "pin_bar": "#FFC53D",
        "status_recording": "#3ED598",
        "status_paused": "#FFC53D",
        "shadow_top": (0, 0, 0, 150),
        "shadow_list": (0, 0, 0, 120),
        "shadow_top_blur": 28, "shadow_top_dy": 6,
        "shadow_list_blur": 22, "shadow_list_dy": 4,
    },
    "light": {
        "qss": QSS_LIGHT,
        "kind_colors": KIND_COLORS_LIGHT,
        "pinned_card_qss": (
            "QWidget#rowCard { "
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 #FFF8DC, stop:1 #FCEFC0); "
            "border: 1px solid #DFA92E; border-radius: 12px; }"),
        "pin_on_color": "#CE7A00",
        "pin_bar": "#E8A20C",
        "status_recording": "#0C9B6C",
        "status_paused": "#CE7A00",
        "shadow_top": (35, 42, 90, 70),
        "shadow_list": (35, 42, 90, 52),
        "shadow_top_blur": 28, "shadow_top_dy": 6,
        "shadow_list_blur": 22, "shadow_list_dy": 4,
    },
}

DEFAULT_THEME = "dark"
THEME_NAMES = list(THEMES.keys())


def get_theme(name):
    """Theme dict for `name`, falling back to the default theme."""
    return THEMES.get(name, THEMES[DEFAULT_THEME])
