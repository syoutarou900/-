# -*- coding: utf-8 -*-
"""Theme for the genealogy design.

A completely new look, built around a floating pill command bar and a
version family-tree (genealogy) canvas:

- pale lavender-white ground, deep indigo (#3730A3) as the main colour
- thin rules and generous whitespace; big numerals / typography first
- amber reserved for the branch (fork) warning and one accent action

2026 refresh: the typography now comes from the bundled fonts
(Inter + Noto Sans JP, see fonts.py) and every control was redrawn
in a flat, modern idiom — no bevels or heavy gradients, generous
corner radii, state changes carried by colour alone, custom-drawn
combo chevrons and check/radio indicators (assets/, drawn with
QPainter), slim scrollbars and soft, sparing drop shadows.
"""

import os

import fonts as _fonts

BG = "#F4F3FA"            # pale lavender white
PANEL = "#FFFFFF"
INK = "#232038"           # deep plum-black
SUBINK = "#6E6A87"
INDIGO = "#4F46E5"
INDIGO_MID = "#4338CA"
INDIGO_DEEP = "#3730A3"
INDIGO_SOFT = "#ECEDFC"
INDIGO_WASH = "#F5F5FE"
LINE = "#DDDAEE"
LINE_STRONG = "#C6C2DE"
AMBER = "#B45309"
AMBER_BG = "#FDF3E2"
AMBER_LINE = "#E3B76B"
GREEN = "#15803D"
GREEN_BG = "#E9F7EE"
RED = "#B91C1C"
RED_BG = "#FBEAEA"
ADD_BG = "#E9F7EE"
DEL_BG = "#FBEAEA"
DISABLED_INK = "#ABA8C2"

# CSS stack for the few places QSS must name a family itself (the
# main UI family is applied per-language via fonts.apply_language_font
# and inherited everywhere else).
UI_FAMILY_CSS = ('"Inter", "Noto Sans JP", "Segoe UI", '
                 '"Hiragino Sans", sans-serif')
MONO_FAMILY_CSS = ('"Cascadia Mono", "Consolas", "SF Mono", "Menlo", '
                   '"DejaVu Sans Mono", monospace')


def apply_theme(app) -> None:
    """Apply palette + stylesheet.

    Ground colours come from the palette, NOT from a global
    "QWidget { background }" rule: a global background paints a
    visible block behind every label's text (seen under Wine).
    """
    from PySide6.QtGui import QColor, QPalette
    _fonts.register_fonts()
    pal = app.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor(BG))
    pal.setColor(QPalette.ColorRole.Base, QColor(PANEL))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(INK))
    pal.setColor(QPalette.ColorRole.Text, QColor(INK))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(INDIGO))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet())


def soft_shadow(widget, blur=22, dy=3, alpha=26) -> None:
    """Attach a restrained drop shadow (cards, command bar, panel).

    Kept deliberately faint: it only lifts the surface off the
    lavender ground, never a heavy grey halo.
    """
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QGraphicsDropShadowEffect
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(0, dy)
    eff.setColor(QColor(35, 32, 56, alpha))
    widget.setGraphicsEffect(eff)


def _asset(name: str) -> str:
    path = os.path.join(_fonts.assets_dir(), name)
    return path.replace(os.sep, "/")


def stylesheet() -> str:
    chev = _asset("chevron-down.png")
    chev_hot = _asset("chevron-down-indigo.png")
    chk_off = _asset("check-off.png")
    chk_off_h = _asset("check-off-hover.png")
    chk_on = _asset("check-on.png")
    chk_on_h = _asset("check-on-hover.png")
    chk_off_d = _asset("check-off-dis.png")
    chk_on_d = _asset("check-on-dis.png")
    rad_off = _asset("radio-off.png")
    rad_off_h = _asset("radio-off-hover.png")
    rad_on = _asset("radio-on.png")
    rad_on_h = _asset("radio-on-hover.png")
    rad_off_d = _asset("radio-off-dis.png")
    rad_on_d = _asset("radio-on-dis.png")
    return f"""
QWidget {{ color: {INK}; font-size: 13px; }}
QMainWindow {{ background: {BG}; }}
QToolTip {{ background: {INK}; color: white; border: none;
    padding: 5px 9px; font-size: 12px; }}

/* ---- buttons: flat, colour carries the state ------------------ */
QPushButton {{ background: {PANEL}; color: {INK};
    border: 1px solid {LINE_STRONG}; border-radius: 10px;
    padding: 7px 16px; font-weight: 500; }}
QPushButton:hover {{ background: {INDIGO_WASH};
    border-color: {INDIGO}; color: {INDIGO_DEEP}; }}
QPushButton:pressed {{ background: {INDIGO_SOFT};
    border-color: {INDIGO}; color: {INDIGO_DEEP}; }}
QPushButton:disabled {{ background: {BG}; color: {DISABLED_INK};
    border-color: {LINE}; }}
QPushButton#primary {{ background: {INDIGO}; border: 1px solid {INDIGO};
    color: white; font-weight: 600; }}
QPushButton#primary:hover {{ background: {INDIGO_MID};
    border-color: {INDIGO_MID}; color: white; }}
QPushButton#primary:pressed {{ background: {INDIGO_DEEP};
    border-color: {INDIGO_DEEP}; color: white; }}
QPushButton#primary:disabled {{ background: #C7C4E8;
    border-color: #C7C4E8; color: white; }}
QPushButton#accent {{ background: {AMBER_BG};
    border: 1px solid {AMBER_LINE}; color: {AMBER}; font-weight: 600; }}
QPushButton#accent:hover {{ background: #FBEED3;
    border-color: {AMBER}; color: {AMBER}; }}
QPushButton#accent:pressed {{ background: #F7E3BC;
    border-color: {AMBER}; color: {AMBER}; }}
QPushButton#accent:disabled {{ background: {BG};
    border-color: {LINE}; color: {DISABLED_INK}; }}

/* ---- inputs ---------------------------------------------------- */
QLineEdit {{ background: {PANEL}; border: 1px solid {LINE_STRONG};
    border-radius: 10px; padding: 7px 12px;
    selection-background-color: {INDIGO}; selection-color: white; }}
QLineEdit:focus {{ border: 1.5px solid {INDIGO};
    background: {PANEL}; }}
QLineEdit:disabled {{ background: {BG}; color: {DISABLED_INK}; }}
QLineEdit#searchEdit {{ border-radius: 12px; }}
QPlainTextEdit {{ background: {PANEL}; border: 1px solid {LINE_STRONG};
    border-radius: 12px; padding: 6px;
    font-family: {MONO_FAMILY_CSS}; font-size: 12px;
    selection-background-color: {INDIGO}; selection-color: white; }}
QPlainTextEdit:focus {{ border: 1.5px solid {INDIGO}; }}

/* ---- combo boxes: hand-drawn chevron --------------------------- */
QComboBox {{ background: {PANEL}; border: 1px solid {LINE_STRONG};
    border-radius: 10px; padding: 6px 30px 6px 12px; font-weight: 500; }}
QComboBox:hover {{ border-color: {INDIGO}; }}
QComboBox:on, QComboBox:focus {{ border-color: {INDIGO}; }}
QComboBox:disabled {{ background: {BG}; color: {DISABLED_INK}; }}
QComboBox::drop-down {{ subcontrol-origin: padding;
    subcontrol-position: center right; width: 26px; border: none; }}
QComboBox::down-arrow {{ image: url({chev}); width: 12px; height: 12px; }}
QComboBox::down-arrow:hover {{ image: url({chev_hot}); }}
QComboBox QAbstractItemView {{ background: {PANEL};
    border: 1px solid {LINE}; border-radius: 8px; padding: 4px;
    outline: 0; selection-background-color: {INDIGO_SOFT};
    selection-color: {INK}; }}
QComboBox#langCombo {{ border-radius: 12px; padding: 6px 28px 6px 12px; }}

/* ---- check boxes / radio buttons: drawn indicators ------------- */
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px;
    image: url({chk_off}); }}
QCheckBox::indicator:hover {{ image: url({chk_off_h}); }}
QCheckBox::indicator:checked {{ image: url({chk_on}); }}
QCheckBox::indicator:checked:hover {{ image: url({chk_on_h}); }}
QCheckBox::indicator:disabled {{ image: url({chk_off_d}); }}
QCheckBox::indicator:checked:disabled {{ image: url({chk_on_d}); }}
QRadioButton {{ spacing: 8px; }}
QRadioButton::indicator {{ width: 18px; height: 18px;
    image: url({rad_off}); }}
QRadioButton::indicator:hover {{ image: url({rad_off_h}); }}
QRadioButton::indicator:checked {{ image: url({rad_on}); }}
QRadioButton::indicator:checked:hover {{ image: url({rad_on_h}); }}
QRadioButton::indicator:disabled {{ image: url({rad_off_d}); }}
QRadioButton::indicator:checked:disabled {{ image: url({rad_on_d}); }}
QListWidget::indicator, QTreeWidget::indicator,
QTableWidget::indicator {{ width: 18px; height: 18px;
    image: url({chk_off}); }}
QListWidget::indicator:checked, QTreeWidget::indicator:checked,
QTableWidget::indicator:checked {{ image: url({chk_on}); }}

/* ---- floating pill command bar ------------------------------- */
QFrame#commandBar {{ background: {PANEL}; border: 1px solid {LINE};
    border-radius: 24px; }}
QLabel#cmdTitle {{ font-size: 18px; font-weight: 700; color: {INDIGO_DEEP}; }}
QLabel#cmdTagline {{ color: {SUBINK}; font-size: 11.5px; font-weight: 500; }}

/* ---- left rail: case-file mini cards ------------------------- */
QFrame#railCard {{ background: {PANEL}; border: 1px solid {LINE};
    border-radius: 14px; }}
QFrame#railCard:hover {{ border-color: #A5A0D8; }}
QFrame#railCard[selected="true"] {{ background: {INDIGO_SOFT};
    border: 1.5px solid {INDIGO}; }}
QLabel#railTitle {{ font-size: 13px; font-weight: 600; color: {INK}; }}
QLabel#railMeta {{ color: {SUBINK}; font-size: 11.5px; }}
QLabel#railCount {{ font-size: 24px; font-weight: 700; color: {INDIGO_DEEP}; }}
QLabel#railHead {{ font-size: 11px; font-weight: 700; color: {SUBINK};
    letter-spacing: 2px; }}

/* ---- badges --------------------------------------------------- */
QLabel#kindExact {{ background: {GREEN_BG}; color: {GREEN};
    border-radius: 8px; padding: 2px 9px; font-weight: 600; font-size: 11px; }}
QLabel#kindCandidate {{ background: {INDIGO_SOFT}; color: {INDIGO_DEEP};
    border-radius: 8px; padding: 2px 9px; font-weight: 600; font-size: 11px; }}
QLabel#branchBadge {{ background: {AMBER_BG}; color: {AMBER};
    border-radius: 8px; padding: 2px 9px; font-weight: 600; font-size: 11px; }}
QLabel#latestBadge {{ background: {INDIGO}; color: white;
    border-radius: 8px; padding: 2px 9px; font-weight: 600; font-size: 11px; }}
QLabel#manualBadge {{ background: {PANEL}; color: {INDIGO_DEEP};
    border: 1px solid {INDIGO}; border-radius: 8px; padding: 1px 8px;
    font-weight: 600; font-size: 11px; }}
QLabel#hashBadge {{ background: {BG}; color: {SUBINK};
    border: 1px solid {LINE}; border-radius: 8px; padding: 1px 8px;
    font-size: 11px; }}

/* ---- main panels ---------------------------------------------- */
QFrame#panel {{ background: {PANEL}; border: 1px solid {LINE};
    border-radius: 18px; }}
QLabel#bigTitle {{ font-size: 21px; font-weight: 700; color: {INK}; }}
QLabel#panelTitle {{ font-size: 12px; font-weight: 700; color: {INDIGO_DEEP};
    letter-spacing: 1.5px; }}
QLabel#reasonText {{ color: {SUBINK}; font-size: 12.5px; }}
QLabel#nodeDetail {{ font-size: 12.5px; color: {INK}; }}
QLabel#statusLabel {{ color: {SUBINK}; font-size: 12.5px; }}
QLabel#warnLabel {{ color: {AMBER}; font-size: 12.5px; font-weight: 600; }}
QLabel#dropHint {{ color: {INDIGO_DEEP}; font-size: 15px; font-weight: 600; }}
QFrame#dropZone {{ background: {INDIGO_WASH}; border: 2px dashed {INDIGO};
    border-radius: 18px; }}

/* ---- lists ------------------------------------------------------ */
QListWidget {{ background: {PANEL}; border: 1px solid {LINE};
    border-radius: 10px; padding: 3px; outline: 0; }}
QListWidget::item {{ padding: 4px 6px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {INDIGO_SOFT}; color: {INK}; }}

/* ---- spread (side-by-side diff) -------------------------------- */
QLabel#spreadHead {{ font-size: 12px; font-weight: 700; color: {INDIGO_DEEP}; }}
QTableWidget {{ background: {PANEL}; border: 1px solid {LINE};
    border-radius: 12px; gridline-color: #ECEAF6;
    font-family: {MONO_FAMILY_CSS}; font-size: 12px;
    selection-background-color: {INDIGO_SOFT}; selection-color: {INK}; }}
QHeaderView::section {{ background: {INDIGO_WASH}; color: {INDIGO_DEEP};
    border: none; border-bottom: 1px solid {LINE}; padding: 6px;
    font-family: {UI_FAMILY_CSS}; font-weight: 600; font-size: 12px; }}

/* ---- misc ------------------------------------------------------- */
QProgressBar {{ border: none; border-radius: 8px;
    background: #E7E5F5; text-align: center; height: 16px;
    color: {SUBINK}; font-size: 11px; font-weight: 600; }}
QProgressBar::chunk {{ background: {INDIGO}; border-radius: 8px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #CFCBEA; border-radius: 5px;
    min-height: 32px; }}
QScrollBar::handle:vertical:hover {{ background: #A5A0D8; }}
QScrollBar::handle:vertical:pressed {{ background: #7C74D6; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: #CFCBEA; border-radius: 5px;
    min-width: 32px; }}
QScrollBar::handle:horizontal:hover {{ background: #A5A0D8; }}
QScrollBar::handle:horizontal:pressed {{ background: #7C74D6; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none; }}
QSplitter::handle {{ background: transparent; }}
"""
