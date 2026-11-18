# -*- coding: utf-8 -*-
"""Visual theme for StepOnce.

"Document studio" look: a warm off-white paper background, a single
orange accent (the colour of idea sheet No. 06), charcoal text, thin
rules and generous whitespace - like editing the pages of a booklet.
This deliberately differs from the blue gradient headers / 3D cards /
round badges used by the user's other apps.

Only appearance lives here; behaviour is untouched.
"""

# -- palette -------------------------------------------------------------
BG = "#FAF7F2"          # warm off-white (paper)
SURFACE = "#FFFFFF"     # cards / header / inputs
SURFACE_SOFT = "#FFFDF9"
INK = "#2E2A26"         # charcoal text
INK_SOFT = "#5C554B"
MUTED = "#9A8F7D"       # warm grey for notes
LINE = "#E7DFD2"        # thin warm rule
LINE_STRONG = "#D9D0C1"
ACCENT = "#E8590C"      # orange accent (idea sheet No. 06)
ACCENT_HOVER = "#F26D1D"
ACCENT_PRESSED = "#CE4C05"
ACCENT_TINT = "#FFF3E8"  # selected card fill
NUM_IDLE = "#DCC7AC"    # step number, unselected
AMBER_BG = "#FFF7DF"    # mosaic-candidate notice
AMBER_LINE = "#EBCB7A"
AMBER_INK = "#7A5B12"
REC_RED = "#D93A2B"     # recording dot / stop button
REC_RED_DARK = "#B92A1E"
PAUSE_AMBER = "#E8A33D"

FONT_STACK = ('"Yu Gothic UI", "Hiragino Kaku Gothic ProN", '
              '"Hiragino Sans", "Noto Sans CJK JP", "Meiryo UI", '
              '"Segoe UI", "Tahoma", sans-serif')


def stylesheet():
    return """
QWidget {
    font-family: %(font)s;
    font-size: 13px;
    color: %(ink)s;
}
QMainWindow { background: %(bg)s; }
QDialog { background: %(bg)s; }
QWidget#central { background: %(bg)s; }
QToolTip {
    background: %(ink)s; color: #FFF7EA; border: none;
    padding: 4px 8px; border-radius: 6px;
}

/* ---- header: thin white band, one orange rule under it ---- */
QFrame#appHeader {
    background: %(surface)s;
    border: none;
    border-bottom: 2px solid %(accent)s;
}
QLabel#logoMark {
    background: %(accent)s; color: #FFFFFF;
    font-size: 17px; font-weight: bold; border-radius: 9px;
}
QLabel#appTitle { font-size: 19px; font-weight: bold; color: %(ink)s; }
QLabel#appSubtitle { font-size: 12px; color: %(muted)s; }
QLabel#langLabel { font-size: 12px; font-weight: bold; color: %(ink_soft)s; }

/* ---- text roles ---- */
QLabel#sectionTitle { font-size: 12px; font-weight: bold; color: #8A7D68; }
QLabel#mutedNote { color: %(muted)s; font-size: 12px; }
QLabel#draftNote { color: %(muted)s; font-size: 11px; }
QLabel#modeNote { color: #9A5B1E; font-size: 12px; }
QLabel#emptyState {
    border: 1.5px dashed %(line_strong)s; border-radius: 10px;
    background: %(surface_soft)s; color: %(muted)s; padding: 16px 12px;
}

/* ---- buttons: flat, rounded; primary is orange ---- */
QPushButton {
    background: %(surface)s;
    border: 1px solid %(line_strong)s;
    border-radius: 8px;
    padding: 7px 14px;
    color: %(ink)s;
}
QPushButton:hover {
    border-color: %(accent)s; color: %(accent)s; background: #FFF8F2;
}
QPushButton:pressed { background: #FDEBDD; }
QPushButton:disabled {
    color: #BFB5A4; border-color: %(line)s; background: #FBF9F5;
}
QPushButton:checked {
    background: #FDEBDD; border-color: %(accent)s; color: %(accent_pressed)s;
}
QPushButton[role="primary"] {
    background: %(accent)s; border: 1px solid %(accent)s;
    color: #FFFFFF; font-weight: bold;
}
QPushButton[role="primary"]:hover {
    background: %(accent_hover)s; border-color: %(accent_hover)s;
    color: #FFFFFF;
}
QPushButton[role="primary"]:pressed {
    background: %(accent_pressed)s; border-color: %(accent_pressed)s;
    color: #FFFFFF;
}
QPushButton[role="primary"]:disabled {
    background: #EFCDB2; border-color: #EFCDB2; color: #FFFFFF;
}
QPushButton[recording="true"] {
    background: %(rec_dark)s; border: 1px solid %(rec_dark)s;
    color: #FFFFFF; font-weight: bold;
}
QPushButton[recording="true"]:hover {
    background: %(rec)s; border-color: %(rec)s; color: #FFFFFF;
}

/* ---- inputs ---- */
QLineEdit, QPlainTextEdit {
    background: %(surface)s;
    border: 1px solid %(line_strong)s;
    border-radius: 8px;
    padding: 6px 10px;
    selection-background-color: #FBD9B8; selection-color: %(ink)s;
}
QLineEdit:hover, QPlainTextEdit:hover { border-color: #C9BBA3; }
QLineEdit:focus, QPlainTextEdit:focus { border: 1.5px solid %(accent)s; }
QComboBox {
    background: %(surface)s;
    border: 1px solid %(line_strong)s;
    border-radius: 8px;
    padding: 5px 10px;
    min-width: 108px;
}
QComboBox:hover { border-color: %(accent)s; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: %(surface)s; border: 1px solid %(line_strong)s;
    selection-background-color: #FDEBDD; selection-color: %(ink)s;
    outline: none; padding: 3px;
}
QCheckBox { spacing: 7px; }
QCheckBox::indicator { width: 16px; height: 16px; }

/* ---- step list: pages of a booklet ---- */
QListWidget {
    background: transparent; border: none; outline: none;
}
QListWidget::item {
    background: transparent; border: none; margin: 3px 2px; padding: 0;
}
QListWidget::item:selected { background: transparent; }
QListWidget::item:hover { background: rgba(232, 89, 12, 0.05); }
QListWidget::item:focus { outline: none; }
QFrame#stepCard {
    background: %(surface)s;
    border: 1px solid %(line)s;
    border-radius: 10px;
}
QFrame#stepCard:hover { border-color: #EEA26F; }
QFrame#stepCard[selected="true"] {
    background: %(accent_tint)s;
    border: 1.5px solid %(accent)s;
}
QLabel#stepNum { font-size: 25px; font-weight: bold; color: %(num_idle)s; }
QFrame#stepCard[selected="true"] QLabel#stepNum { color: %(accent)s; }
QLabel#stepText { font-size: 13px; color: %(ink)s; }
QLabel#stepMeta { font-size: 11px; color: #A3988A; }
QLabel#thumb {
    background: %(surface)s; border: 1px solid %(line)s; border-radius: 6px;
}

/* ---- preview sheet ---- */
QLabel#preview {
    background: %(surface)s;
    border: 1px solid %(line)s;
    border-radius: 12px;
}
QRubberBand {
    border: 1.5px solid %(accent)s;
    background: rgba(232, 89, 12, 0.15);
}

/* ---- mosaic candidate notice ---- */
QFrame#candidateBar {
    background: %(amber_bg)s;
    border: 1px solid %(amber_line)s;
    border-radius: 10px;
}
QLabel#candidateText { color: %(amber_ink)s; font-size: 12.5px; }

/* ---- recording panel ---- */
QFrame#panelCard {
    background: %(surface)s;
    border: 1.5px solid %(accent)s;
    border-radius: 14px;
}
QLabel#recStatus { font-size: 13px; font-weight: bold; color: %(ink)s; }
QLabel#recCount { font-size: 12px; color: %(muted)s; }
QLabel#recDot { background: %(rec)s; border-radius: 5px; }
QLabel#recDot[state="paused"] { background: %(pause)s; }
QLabel#recDot[state="off"] { background: transparent; }

/* ---- splitter & scrollbars ---- */
QSplitter::handle { background: transparent; }
QSplitter::handle:horizontal { width: 8px; }
QSplitter::handle:vertical { height: 8px; }
QScrollBar:vertical {
    background: transparent; width: 10px; margin: 2px 1px;
}
QScrollBar::handle:vertical {
    background: #D8CDBB; border-radius: 5px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: %(accent)s; }
QScrollBar:horizontal {
    background: transparent; height: 10px; margin: 1px 2px;
}
QScrollBar::handle:horizontal {
    background: #D8CDBB; border-radius: 5px; min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background: %(accent)s; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
""" % {
        "font": FONT_STACK, "bg": BG, "surface": SURFACE,
        "surface_soft": SURFACE_SOFT, "ink": INK, "ink_soft": INK_SOFT,
        "muted": MUTED, "line": LINE, "line_strong": LINE_STRONG,
        "accent": ACCENT, "accent_hover": ACCENT_HOVER,
        "accent_pressed": ACCENT_PRESSED, "accent_tint": ACCENT_TINT,
        "num_idle": NUM_IDLE, "amber_bg": AMBER_BG,
        "amber_line": AMBER_LINE, "amber_ink": AMBER_INK,
        "rec": REC_RED, "rec_dark": REC_RED_DARK, "pause": PAUSE_AMBER,
    }
