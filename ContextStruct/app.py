# -*- coding: utf-8 -*-
"""ContextStruct — 非構造化資料（PDF・画像）の文脈特化型・即時構造化アシスタント
Design: polished 3D cards / gradient header / circular icon badges (DropLauncher-level+)."""
import sys, os, json, csv, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import rc_assets  # noqa: F401  compiled arrow PNG resources for combo/spin/scrollbar
except Exception:
    pass
from PySide6.QtWidgets import *
from PySide6.QtGui import QColor, QPixmap, QShortcut, QKeySequence, QPainter, QLinearGradient, QPen, QBrush, QFont, QCursor
from PySide6.QtCore import Qt, QRectF, QThread, Signal, QTimer
from i18n_data import TRANSLATIONS, LANG_ORDER, LANG_NAMES, t as tr
from context_core import *
import vlm_local
import ensemble
import learning
import automation as automation_mod
import integrations as integrations_mod

def _under_wine():
    """True when running under Wine (ntdll exports wine_get_version only there).

    Used solely for Wine-only stability workarounds; on real Windows every
    code path behaves exactly as before.
    """
    if sys.platform != "win32":
        # Wine only ever presents as win32; other platforms (macOS/Linux)
        # have no WinDLL at all, so answer directly instead of relying on
        # the exception fallback below.
        return False
    try:
        import ctypes
        return hasattr(ctypes.WinDLL("ntdll"), "wine_get_version")
    except Exception:
        return False

_UNDER_WINE = _under_wine()

def ocr_missing_message(lang):
    """OCR-missing notice. On macOS, show the Homebrew install guidance
    (ocr_missing_mac) instead; on every other platform return the original
    ocr_missing message byte-for-byte, so Windows text is unchanged."""
    if sys.platform == "darwin":
        m = tr(lang, "ocr_missing_mac")
        if m and m != "ocr_missing_mac":
            return m
    return tr(lang, "ocr_missing")

STYLE = """
QWidget { background:#e8eff9; color:#16324f; font-size:13.5px; font-family:'Yu Gothic UI','Meiryo UI','Noto Sans CJK JP','Segoe UI',sans-serif; }
QLabel { background:transparent; }
QDialog { background:#eef3fb; }
QFrame#header { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1d46a8, stop:0.5 #2f7fd0, stop:1 #0fb0cb);
    border-radius:18px; border-bottom:4px solid #173a7d; }
QLabel#appTitle { background:transparent; color:#ffffff; font-size:20px; font-weight:bold; }
QLabel#appSub { background:transparent; color:#e2efff; font-size:12.5px; }
QLabel#headerLabel { background:transparent; color:#ffffff; font-size:12.5px; font-weight:bold; }
QFrame#langPill { background:rgba(255,255,255,0.20); border:1px solid rgba(255,255,255,0.45); border-radius:12px; }
QFrame#card { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #e6f0fd);
    border:1.5px solid #b9d2ee; border-bottom:4px solid #8fb4dd; border-radius:14px; }
QLabel#cardTitle { background:transparent; color:#12293f; font-size:14.5px; font-weight:bold; }
QLabel#sectionLabel { background:transparent; color:#486581; font-size:12px; font-weight:bold; }
QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6db3f2, stop:1 #2f66d0); color:white;
    border:1px solid #17497f; border-bottom:3px solid #17497f; border-radius:10px; padding:9px 16px; font-weight:bold; }
QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8cc4f7, stop:1 #4393dd); }
QPushButton:pressed { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2f7fd0, stop:1 #17497f); border-bottom:1px solid #17497f; }
QPushButton#secondary { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #dbeafe); color:#2456c8;
    border:1.5px solid #9dbede; border-bottom:3px solid #7ea6cf; }
QPushButton#secondary:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #eaf3ff); color:#1d46a8; }
QPushButton#secondary:pressed { background:#cfe2f7; border-bottom:1px solid #7ea6cf; }
QPushButton#headerBtn { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #dbeafe); color:#1d46a8;
    border:1px solid rgba(255,255,255,0.7); border-bottom:3px solid #b9d2ee; padding:7px 14px; }
QPushButton#headerBtn:hover { background:#ffffff; }
QPushButton#bigPrimary { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #22c55e, stop:1 #0ea5a5); color:white;
    border:1px solid #15803d; border-bottom:4px solid #14532d; border-radius:12px; padding:13px 22px; font-size:15.5px; font-weight:bold; }
QPushButton#bigPrimary:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4ade80, stop:1 #14b8a6); }
QPushButton#bigPrimary:pressed { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #16a34a, stop:1 #0f766e); border-bottom:1px solid #14532d; }
QPushButton#primaryBlue { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2456c8, stop:1 #12a5c4); color:white;
    border:1px solid #173a7d; border-bottom:4px solid #173a7d; border-radius:12px; padding:12px 22px; font-size:14.5px; font-weight:bold; }
QPushButton#primaryBlue:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b6fd4, stop:1 #22b8d4); }
QTextEdit, QLineEdit, QTableWidget { background:#ffffff; border:1.5px solid #b9d2ee; border-radius:10px; padding:6px; }
QTextEdit:focus, QLineEdit:focus { border:1.5px solid #2f7fd0; }
QTableWidget { gridline-color:#d9e5f3; selection-background-color:#bfdbfe; }
QHeaderView::section { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #dbeafe, stop:1 #bfdbfe); color:#173a7d;
    font-weight:bold; border:1px solid #b9d2ee; padding:6px 8px; }
QCheckBox { background:transparent; font-weight:bold; spacing:6px; }
/* ===== 立体スクロールバー（縦） ===== */
QScrollBar:vertical { border:none; background:#cfdff2; width:18px; border-radius:9px; margin:21px 1px 21px 1px; }
QScrollBar::handle:vertical { min-height:40px; border-radius:8px; border:1px solid #17497f;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6db3f2, stop:0.45 #2f7fd0, stop:1 #1d5fa8); }
QScrollBar::handle:vertical:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8cc4f7, stop:0.45 #4393dd, stop:1 #2569b5); }
QScrollBar::handle:vertical:pressed { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f7fd0, stop:1 #17497f); }
QScrollBar::add-line:vertical { height:20px; subcontrol-position:bottom; subcontrol-origin:margin; margin:0 1px 1px 1px;
    border:1px solid #17497f; border-radius:6px; background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6db3f2, stop:1 #2456c8); }
QScrollBar::sub-line:vertical { height:20px; subcontrol-position:top; subcontrol-origin:margin; margin:1px 1px 0 1px;
    border:1px solid #17497f; border-radius:6px; background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6db3f2, stop:1 #2456c8); }
QScrollBar::add-line:vertical:hover, QScrollBar::sub-line:vertical:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8cc4f7, stop:1 #2f66d0); }
QScrollBar::up-arrow:vertical { image: url(:/arrows/up_white.png); width:10px; height:10px; }
QScrollBar::down-arrow:vertical { image: url(:/arrows/down_white.png); width:10px; height:10px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
/* ===== 立体スクロールバー（横） ===== */
QScrollBar:horizontal { border:none; background:#cfdff2; height:18px; border-radius:9px; margin:1px 21px 1px 21px; }
QScrollBar::handle:horizontal { min-width:40px; border-radius:8px; border:1px solid #17497f;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6db3f2, stop:0.45 #2f7fd0, stop:1 #1d5fa8); }
QScrollBar::handle:horizontal:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8cc4f7, stop:0.45 #4393dd, stop:1 #2569b5); }
QScrollBar::add-line:horizontal { width:20px; subcontrol-position:right; subcontrol-origin:margin; margin:1px 1px 1px 0;
    border:1px solid #17497f; border-radius:6px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6db3f2, stop:1 #2456c8); }
QScrollBar::sub-line:horizontal { width:20px; subcontrol-position:left; subcontrol-origin:margin; margin:1px 0 1px 1px;
    border:1px solid #17497f; border-radius:6px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6db3f2, stop:1 #2456c8); }
QScrollBar::left-arrow:horizontal { image: url(:/arrows/left_white.png); width:10px; height:10px; }
QScrollBar::right-arrow:horizontal { image: url(:/arrows/right_white.png); width:10px; height:10px; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background:transparent; }
/* ===== コンボボックスの立体▼ボタン ===== */
QComboBox { background:#ffffff; border:1.5px solid #b9d2ee; border-radius:8px; padding:6px 8px; padding-right:32px; }
QComboBox::drop-down { subcontrol-origin:padding; subcontrol-position:center right; width:28px;
    border-left:1px solid #17497f; border-top-right-radius:7px; border-bottom-right-radius:7px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6db3f2, stop:1 #2456c8); }
QComboBox::drop-down:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8cc4f7, stop:1 #2f66d0); }
QComboBox::down-arrow { image: url(:/arrows/down_white.png); width:12px; height:12px; }
QComboBox QAbstractItemView { background:#ffffff; border:1px solid #9dbede; selection-background-color:#2f7fd0; selection-color:#ffffff; }
/* ===== スピンボックスの立体矢印ボタン ===== */
QSpinBox { background:#ffffff; border:1.5px solid #b9d2ee; border-radius:8px; padding:6px 8px; padding-right:26px; }
QSpinBox::up-button { subcontrol-origin:border; subcontrol-position:top right; width:22px;
    border-left:1px solid #17497f; border-bottom:1px solid #17497f; border-top-right-radius:7px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6db3f2, stop:1 #2f7fd0); }
QSpinBox::down-button { subcontrol-origin:border; subcontrol-position:bottom right; width:22px;
    border-left:1px solid #17497f; border-bottom-right-radius:7px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2f7fd0, stop:1 #2456c8); }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8cc4f7, stop:1 #4393dd); }
QSpinBox::up-arrow { image: url(:/arrows/up_white.png); width:8px; height:8px; }
QSpinBox::down-arrow { image: url(:/arrows/down_white.png); width:8px; height:8px; }
/* ===== v3 design pass: unified dialog system ===== */
QLabel#dlgTitle { background:transparent; color:#ffffff; font-size:17.5px; font-weight:bold; }
QLabel#noteInfo { background:#eaf6ff; border:1.5px solid #9ec7ee; border-radius:10px; padding:10px 13px; color:#1c4e79; font-size:12.5px; font-weight:bold; }
QLabel#noteWarn { background:#fff7e0; border:1.5px solid #f2c94c; border-radius:10px; padding:10px 13px; color:#6b5410; font-size:12.5px; font-weight:bold; }
QLabel#statusBar { background:#ffffff; border:1.5px solid #b9d2ee; border-bottom:3px solid #8fb4dd; border-radius:10px; padding:8px 12px; color:#24507e; font-weight:bold; }
QListWidget { background:#ffffff; border:1.5px solid #b9d2ee; border-radius:10px; padding:5px; }
QListWidget::item { padding:8px 10px; border-radius:7px; margin:2px 1px; }
QListWidget::item:selected { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f7fd0, stop:1 #1d46a8); color:#ffffff; font-weight:bold; }
QListWidget::item:hover:!selected { background:#eaf3ff; }
QProgressBar { background:#dbeafe; border:1.5px solid #9dbede; border-radius:9px; height:20px; text-align:center; font-weight:bold; color:#173a7d; }
QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2456c8, stop:1 #12c4a5); border-radius:8px; }
QMessageBox, QInputDialog, QProgressDialog { background:#eef3fb; }
QMessageBox QLabel, QProgressDialog QLabel { background:transparent; color:#16324f; font-size:13.5px; }
QStackedWidget { background:transparent; }
"""

def _lighten(hexcolor, factor=170):
    return QColor(hexcolor).lighter(factor).name()

def make_badge(icon, accent, size=44):
    b = QLabel(icon); b.setAlignment(Qt.AlignCenter); b.setFixedSize(size, size)
    b.setStyleSheet(f"font-size:{int(size*0.45)}px; border-radius:{size//2}px; color:white;"
                    f"background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {_lighten(accent,150)}, stop:1 {accent});"
                    f"border:2px solid rgba(255,255,255,0.9);")
    return b

def add_shadow(widget, blur=18, dy=5, alpha=55):
    try:
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        sh = QGraphicsDropShadowEffect(widget); sh.setBlurRadius(blur); sh.setOffset(0, dy)
        sh.setColor(QColor(31, 78, 140, alpha)); widget.setGraphicsEffect(sh); return sh
    except Exception:
        return None

def make_dialog_header(icon, accent, title_text):
    """Gradient header band shared by every dialog (same language as the main
    window header): circular badge + white bold title on a blue gradient."""
    fr = QFrame(); fr.setObjectName("header"); add_shadow(fr, 18, 5, 70)
    lay = QHBoxLayout(fr); lay.setContentsMargins(18, 13, 18, 13); lay.setSpacing(12)
    lay.addWidget(make_badge(icon, accent, 48))
    t = QLabel(title_text); t.setObjectName("dlgTitle"); t.setWordWrap(True); lay.addWidget(t, 1)
    return fr

def make_card(icon, accent, title=""):
    card = QFrame(); card.setObjectName("card"); add_shadow(card, 16, 4, 45)
    lay = QVBoxLayout(card); lay.setContentsMargins(14, 12, 14, 12); lay.setSpacing(9)
    head = QHBoxLayout(); head.setSpacing(10); head.addWidget(make_badge(icon, accent, 40))
    t = QLabel(title); t.setObjectName("cardTitle"); t.setWordWrap(True); head.addWidget(t, 1)
    lay.addLayout(head)
    card._title_label = t
    return card, lay

class DropZone(QWidget):
    """Large dashed drop zone: circular badge + big text; lifts & tints on drag/hover."""
    ACCENT = "#2563eb"
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True); self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(148); self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._active = False
        self._shadow = add_shadow(self, 20, 6, 58)
        lay = QVBoxLayout(self); lay.setContentsMargins(16, 14, 16, 12); lay.setSpacing(5)
        brow = QHBoxLayout(); brow.addStretch(); brow.addWidget(make_badge("📥", self.ACCENT, 58)); brow.addStretch(); lay.addLayout(brow)
        self.title_lbl = QLabel(); self.title_lbl.setAlignment(Qt.AlignCenter); self.title_lbl.setWordWrap(True)
        self.title_lbl.setStyleSheet("font-size:17px; font-weight:bold; color:#1e3a8a; background:transparent;")
        lay.addWidget(self.title_lbl)
        self.hint_lbl = QLabel(); self.hint_lbl.setAlignment(Qt.AlignCenter); self.hint_lbl.setWordWrap(True)
        self.hint_lbl.setStyleSheet("font-size:12px; color:#52687e; background:transparent;")
        lay.addWidget(self.hint_lbl)
        self.callback = None; self.click_select = None; self.callback_multi = None; self.want_multi = False
        if _UNDER_WINE:
            # Wine-only: the custom QPainter path (gradients + clip) can drive
            # runaway allocation in Wine's graphics stack; a stylesheet with
            # the same colours/dashed outline renders near-identically.
            self.setStyleSheet("background:#eef4ff; border:2px dashed #2563eb; border-radius:16px;")
    def set_texts(self, title, hint):
        self.title_lbl.setText(title); self.hint_lbl.setText(hint)
    def _set_active(self, on):
        self._active = on
        if self._shadow:
            self._shadow.setBlurRadius(30 if on else 20); self._shadow.setOffset(0, 10 if on else 6)
        self.update()
    def enterEvent(self, e): self._set_active(True); super().enterEvent(e)
    def leaveEvent(self, e):
        if not getattr(self, "_dragging", False): self._set_active(False)
        super().leaveEvent(e)
    def paintEvent(self, e):
        if _UNDER_WINE:
            return super().paintEvent(e)
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        accent = QColor(self.ACCENT); r = QRectF(self.rect()).adjusted(2, 2, -2, -6)
        grad = QLinearGradient(r.topLeft(), r.bottomLeft())
        if self._active:
            grad.setColorAt(0, accent.lighter(190)); grad.setColorAt(1, accent.lighter(168))
        else:
            grad.setColorAt(0, QColor("#ffffff")); grad.setColorAt(0.55, accent.lighter(216)); grad.setColorAt(1, accent.lighter(198))
        p.setBrush(QBrush(grad))
        pen = QPen(accent, 2.6 if self._active else 2.0); pen.setStyle(Qt.DashLine if not self._active else Qt.SolidLine)
        p.setPen(pen); p.drawRoundedRect(r, 16, 16)
        from PySide6.QtGui import QPainterPath
        p.save(); clip = QPainterPath(); clip.addRoundedRect(r, 16, 16); p.setClipPath(clip)
        p.setPen(Qt.NoPen); p.setBrush(accent); p.drawRect(QRectF(r.left(), r.bottom() - 3.5, r.width(), 5))
        p.setBrush(QColor(255, 255, 255, 110)); p.drawRect(QRectF(r.left() + 8, r.top() + 1.5, r.width() - 16, 2))
        p.restore(); super().paintEvent(e)
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): self._dragging = True; self._set_active(True); e.acceptProposedAction()
    def dragLeaveEvent(self, e): self._dragging = False; self._set_active(False)
    def dropEvent(self, e):
        self._dragging = False; self._set_active(False)
        urls = e.mimeData().urls()
        if not urls: return
        files = [u.toLocalFile() for u in urls]
        # v2: multiple files go to the batch handler (complete-auto mode)
        if getattr(self, "callback_multi", None) and len(files) > 1:
            self.callback_multi(files)
        elif getattr(self, "callback_multi", None) and getattr(self, "want_multi", False):
            self.callback_multi(files)
        elif self.callback: self.callback(files[0])
    def mousePressEvent(self, e):
        if self.click_select: self.click_select()

class ProfileEditor(QDialog):
    def __init__(self, profile, lang, parent=None):
        super().__init__(parent); self.lang = lang; self.profile = Profile.from_dict(profile.to_dict())
        self.setWindowTitle(tr(lang, "profile_editor_title")); self.setStyleSheet(STYLE); self.resize(920, 560)
        self.setMinimumSize(760, 480)
        lay = QVBoxLayout(self); lay.setContentsMargins(16, 14, 16, 14); lay.setSpacing(12)
        lay.addWidget(make_dialog_header("🗂", "#38bdf8", tr(lang, "profile_editor_title")))
        card, cl = make_card("✎", "#7c3aed", tr(lang, "profile_name"))
        top = QHBoxLayout(); self.name_edit = QLineEdit(self.profile.name); self.name_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); top.addWidget(self.name_edit); cl.addLayout(top)
        self.table = QTableWidget(0, 5); self.table.setHorizontalHeaderLabels([tr(lang, "field_display"), tr(lang, "target_column"), tr(lang, "keywords"), tr(lang, "field_type"), tr(lang, "required_col")])
        _hh = self.table.horizontalHeader(); _hh.setSectionResizeMode(QHeaderView.Interactive); _hh.setStretchLastSection(True)
        self.table.setColumnWidth(0, 130); self.table.setColumnWidth(1, 130); self.table.setColumnWidth(2, 330); self.table.setColumnWidth(3, 140); self.table.setColumnWidth(4, 60)
        self.table.setMinimumHeight(240); cl.addWidget(self.table)
        lay.addWidget(card, 1)
        for f in self.profile.fields: self._add_row(f)
        btns = QGridLayout(); btns.setSpacing(9)
        for i, (txt, fn, sec) in enumerate([(tr(lang, "add_btn"), self.add_row_btn, False), (tr(lang, "delete_btn"), self.del_row, True), (tr(lang, "up_btn"), lambda: self.move(-1), True), (tr(lang, "down_btn"), lambda: self.move(1), True), (tr(lang, "export_profile"), self.export_p, True), (tr(lang, "import_profile"), self.import_p, True)]):
            b = QPushButton(txt); b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); b.setMinimumHeight(40)
            if sec: b.setObjectName("secondary")
            b.clicked.connect(fn); btns.addWidget(b, i // 3, i % 3)
        lay.addLayout(btns)
        bb = QHBoxLayout(); sb = QPushButton("✓ " + tr(lang, "save_btn")); sb.setObjectName("bigPrimary"); sb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); sb.clicked.connect(self.accept)
        cb = QPushButton(tr(lang, "cancel_btn")); cb.setObjectName("secondary"); cb.clicked.connect(self.reject); bb.addWidget(sb, 2); bb.addWidget(cb, 1); lay.addLayout(bb)
    def _add_row(self, f):
        r = self.table.rowCount(); self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(f.display_name)); self.table.setItem(r, 1, QTableWidgetItem(f.target_column)); self.table.setItem(r, 2, QTableWidgetItem(f.keywords))
        combo = QComboBox(); combo.addItems(["text", "number", "date", "amount"]); combo.setCurrentText(f.field_type); self.table.setCellWidget(r, 3, combo)
        chk = QCheckBox(); chk.setChecked(f.required); self.table.setCellWidget(r, 4, chk)
    def add_row_btn(self): self._add_row(FieldDef("新しい項目", "新しい列", "", "text", False))
    def del_row(self):
        r = self.table.currentRow()
        if r >= 0: self.table.removeRow(r)
    def move(self, d):
        r = self.table.currentRow(); nr = r + d
        if r < 0 or nr < 0 or nr >= self.table.rowCount(): return
        def vals(rr): return (self.table.item(rr, 0).text(), self.table.item(rr, 1).text(), self.table.item(rr, 2).text(), self.table.cellWidget(rr, 3).currentText(), self.table.cellWidget(rr, 4).isChecked())
        a, b = vals(r), vals(nr)
        for rr, v in [(r, b), (nr, a)]:
            self.table.item(rr, 0).setText(v[0]); self.table.item(rr, 1).setText(v[1]); self.table.item(rr, 2).setText(v[2]); self.table.cellWidget(rr, 3).setCurrentText(v[3]); self.table.cellWidget(rr, 4).setChecked(v[4])
        self.table.setCurrentCell(nr, 0)
    def get_profile(self):
        fields = []
        for r in range(self.table.rowCount()):
            fields.append(FieldDef(self.table.item(r, 0).text() if self.table.item(r, 0) else "", self.table.item(r, 1).text() if self.table.item(r, 1) else "", self.table.item(r, 2).text() if self.table.item(r, 2) else "", self.table.cellWidget(r, 3).currentText(), self.table.cellWidget(r, 4).isChecked()))
        return Profile(self.name_edit.text(), fields)
    def export_p(self):
        p, _ = QFileDialog.getSaveFileName(self, tr(self.lang, "export_profile"), "", "JSON (*.json)")
        if p: save_profile(self.get_profile(), p)
    def import_p(self):
        p, _ = QFileDialog.getOpenFileName(self, tr(self.lang, "import_profile"), "", "JSON (*.json)")
        if p:
            prof = load_profile(p); self.name_edit.setText(prof.name); self.table.setRowCount(0)
            for f in prof.fields: self._add_row(f)

class SettingsDialog(QDialog):
    def __init__(self, settings, lang, parent=None):
        super().__init__(parent); self.lang = lang; self.setWindowTitle(tr(lang, "settings_title")); self.setStyleSheet(STYLE)
        self.resize(780, 900); self.setMinimumSize(600, 640); self.settings = dict(settings)
        lay = QVBoxLayout(self); lay.setContentsMargins(16, 14, 16, 14); lay.setSpacing(12)
        lay.addWidget(make_dialog_header("⚙", "#38bdf8", tr(lang, "settings_title")))
        _container = QWidget(); _container.setStyleSheet("background:transparent;")
        body = QVBoxLayout(_container); body.setContentsMargins(2, 2, 2, 2); body.setSpacing(12)
        _scroll = QScrollArea(); _scroll.setWidgetResizable(True); _scroll.setWidget(_container); _scroll.setFrameShape(QFrame.NoFrame)
        lay.addWidget(_scroll, 1)
        card, cl = make_card("⚙", "#0ea5e9", tr(lang, "card_general")); body.addWidget(card)
        form = QFormLayout(); form.setSpacing(11); form.setLabelAlignment(Qt.AlignLeft); cl.addLayout(form)
        self.lang_combo = QComboBox()
        for code in LANG_ORDER: self.lang_combo.addItem(LANG_NAMES[code], code)
        self.lang_combo.setCurrentIndex(LANG_ORDER.index(settings.get("language", "ja")) if settings.get("language", "ja") in LANG_ORDER else 0)
        form.addRow(tr(lang, "language_label"), self.lang_combo)
        self.ocr_edit = QLineEdit(settings.get("ocr_lang", "")); form.addRow(tr(lang, "ocr_lang_label"), self.ocr_edit)
        self.dpi_spin = QSpinBox(); self.dpi_spin.setRange(72, 400); self.dpi_spin.setValue(int(settings.get("ocr_dpi", 200) or 200)); self.dpi_spin.setSuffix(" DPI")
        form.addRow(tr(lang, "ocr_dpi_label"), self.dpi_spin)
        self.hotkey_edit = QLineEdit(settings.get("hotkey", "Ctrl+Shift+S")); form.addRow(tr(lang, "hotkey_label"), self.hotkey_edit)
        self.out_combo = QComboBox(); self.out_combo.addItems(["tsv", "xlsx", "csv", "json"]); self.out_combo.setCurrentText(settings.get("default_output", "tsv")); form.addRow(tr(lang, "default_output"), self.out_combo)
        # --- Built-in local VLM (llama.cpp + Qwen2.5-VL-3B, offline, no API key) ---
        vcard, vl = make_card("🤖", "#2563eb", tr(lang, "mode_local_vlm")); body.addWidget(vcard)
        vform = QFormLayout(); vform.setSpacing(11); vform.setLabelAlignment(Qt.AlignLeft); vl.addLayout(vform)
        self.ep_edit = QLineEdit(settings.get("vlm_endpoint", "")); vform.addRow(tr(lang, "vlm_endpoint"), self.ep_edit)
        self.key_edit = QLineEdit(settings.get("vlm_key", "")); self.key_edit.setEchoMode(QLineEdit.Password); vform.addRow(tr(lang, "vlm_key"), self.key_edit)
        self.model_edit = QLineEdit(settings.get("vlm_model", "")); vform.addRow(tr(lang, "vlm_model"), self.model_edit)
        _st = vlm_local.model_status(model_key=settings.get("vlm_model_size", "3b"))
        _bin = vlm_local.find_runtime_binary()
        self.vlm_status_lbl = QLabel("Local VLM: " + (tr(lang, "vlm_ready_msg") if _st["complete"] else "—") + f"  |  llama-mtmd-cli: {'OK' if _bin else 'missing'}")
        self.vlm_status_lbl.setWordWrap(True); self.vlm_status_lbl.setStyleSheet("font-weight:bold; color:#24507e;")
        vl.addWidget(self.vlm_status_lbl)
        self.vlm_note_lbl = QLabel(tr(lang, "vlm_image_note") + " " + tr(lang, "vlm_slow_note")); self.vlm_note_lbl.setWordWrap(True); self.vlm_note_lbl.setStyleSheet("color:#486581; font-size:12px;")
        vl.addWidget(self.vlm_note_lbl)
        self.dl_btn = QPushButton("⬇ " + tr(lang, "vlm_download_generic") + f" ({vlm_local.model_spec(settings.get('vlm_model_size', '3b'))['approx_gb']}GB)"); self.dl_btn.setObjectName("secondary"); self.dl_btn.setMinimumHeight(38)
        self.download_requested = False
        def _req():
            self.download_requested = True; self.accept()
        self.dl_btn.clicked.connect(_req); vl.addWidget(self.dl_btn)
        self.use_api_chk = QCheckBox(tr(lang, "vlm_use_api_label")); self.use_api_chk.setChecked(bool(settings.get("vlm_use_api", False))); vl.addWidget(self.use_api_chk)
        # --- v2 H: GPU runtime (optional download; CPU is the default) ---
        gcard, gl = make_card("🎮", "#8b5cf6", tr(lang, "gpu_title")); body.addWidget(gcard)
        _bin, _mode = vlm_local.best_runtime()
        _mode_key = {"gpu_cuda": "gpu_cuda", "gpu_vulkan": "gpu_vulkan"}.get(_mode, "gpu_cpu")
        self.gpu_mode_lbl = QLabel(tr(lang, "gpu_mode_is") + tr(lang, _mode_key) + f"  (detect: {vlm_local.detect_gpu()['recommended']})")
        self.gpu_mode_lbl.setStyleSheet("font-weight:bold; color:#24507e;"); gl.addWidget(self.gpu_mode_lbl)
        self.gpu_note_lbl = QLabel(tr(lang, "gpu_note")); self.gpu_note_lbl.setWordWrap(True); self.gpu_note_lbl.setStyleSheet("color:#486581; font-size:12px;"); gl.addWidget(self.gpu_note_lbl)
        self.gpu_flavor = None
        grow = QHBoxLayout()
        for _fl, _key in (("vulkan", "gpu_dl_vulkan_btn"), ("cuda", "gpu_dl_cuda_btn")):
            b = QPushButton("⬇ " + tr(lang, _key)); b.setObjectName("secondary")
            b.clicked.connect(lambda _=None, _f=_fl: self._req_gpu(_f)); grow.addWidget(b, 1)
        gl.addLayout(grow)
        self.cloud_lbl = QLabel("☁ " + tr(lang, "cloud_max_label")); self.cloud_lbl.setStyleSheet("color:#24507e; font-size:12px; font-weight:bold;"); vl.addWidget(self.cloud_lbl)
        # --- v2: model size (3B light / 7B high accuracy), master CSV, learning ---
        v2form = QFormLayout(); v2form.setSpacing(11); v2form.setLabelAlignment(Qt.AlignLeft); vl.addLayout(v2form)
        self.size_combo = QComboBox(); self.size_combo.addItem(tr(lang, "vlm_size_3b"), "3b"); self.size_combo.addItem(tr(lang, "vlm_size_7b"), "7b")
        self.size_combo.setCurrentIndex(1 if settings.get("vlm_model_size", "3b") == "7b" else 0)
        v2form.addRow(tr(lang, "vlm_model_size"), self.size_combo)
        mrow = QHBoxLayout(); self.master_edit = QLineEdit(settings.get("master_csv", "")); mrow.addWidget(self.master_edit, 1)
        mb = QPushButton(tr(lang, "browse_btn")); mb.setObjectName("secondary"); mb.clicked.connect(lambda: self._browse_into(self.master_edit, "file")); mrow.addWidget(mb); v2form.addRow(tr(lang, "master_csv"), mrow)
        self.optocr_chk = QCheckBox(tr(lang, "optional_ocr_label")); self.optocr_chk.setChecked(bool(settings.get("optional_ocr", False))); vl.addWidget(self.optocr_chk)
        self.learn_chk = QCheckBox(tr(lang, "learning_enable")); self.learn_chk.setChecked(bool(settings.get("learning_enabled", True))); vl.addWidget(self.learn_chk)
        # --- v2: complete automation (watch folder) ---
        acard, al2 = make_card("🤖", "#f59e0b", tr(lang, "auto_title")); body.addWidget(acard)
        self.watch_chk = QCheckBox(tr(lang, "watch_enable")); self.watch_chk.setChecked(bool(settings.get("watch_enabled", False))); al2.addWidget(self.watch_chk)
        aform = QFormLayout(); aform.setSpacing(11); aform.setLabelAlignment(Qt.AlignLeft); al2.addLayout(aform)
        def _path_row(edit_attr, key, kind):
            row = QHBoxLayout(); e = QLineEdit(settings.get(key, "")); row.addWidget(e, 1)
            b = QPushButton(tr(lang, "browse_btn")); b.setObjectName("secondary"); b.clicked.connect(lambda _=None, _e=e, _k=kind: self._browse_into(_e, _k)); row.addWidget(b)
            setattr(self, edit_attr, e); return row
        aform.addRow(tr(lang, "watch_folder"), _path_row("watch_edit", "watch_folder", "dir"))
        aform.addRow(tr(lang, "auto_output"), _path_row("aout_edit", "auto_output_path", "save"))
        aform.addRow(tr(lang, "auto_done"), _path_row("adone_edit", "auto_done_folder", "dir"))
        aform.addRow(tr(lang, "auto_review"), _path_row("areview_edit", "auto_review_folder", "dir"))
        self.th_spin = QSpinBox(); self.th_spin.setRange(50, 100); self.th_spin.setValue(int(settings.get("auto_threshold", 90) or 90)); self.th_spin.setSuffix(" %")
        aform.addRow(tr(lang, "auto_threshold"), self.th_spin)
        self.dest_combo = QComboBox(); self.dest_combo.addItem(tr(lang, "auto_dest_file"), "file"); self.dest_combo.addItem(tr(lang, "auto_dest_intfile"), "intfile"); self.dest_combo.addItem(tr(lang, "auto_dest_intdb"), "intdb")
        self.dest_combo.setCurrentIndex({"file": 0, "intfile": 1, "intdb": 2}.get(settings.get("auto_dest", "file"), 0))
        aform.addRow(tr(lang, "auto_dest"), self.dest_combo)
        self.auto_note_lbl = QLabel(tr(lang, "auto_note")); self.auto_note_lbl.setWordWrap(True)
        self.auto_note_lbl.setObjectName("noteWarn")
        al2.addWidget(self.auto_note_lbl)
        bb = QHBoxLayout(); sb = QPushButton("✓ " + tr(lang, "save_btn")); sb.setObjectName("bigPrimary"); sb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); sb.clicked.connect(self.accept)
        cb = QPushButton(tr(lang, "cancel_btn")); cb.setObjectName("secondary"); cb.clicked.connect(self.reject); bb.addWidget(sb, 2); bb.addWidget(cb, 1); lay.addLayout(bb)
    def _req_gpu(self, flavor):
        self.gpu_flavor = flavor; self.accept()
    def _browse_into(self, edit, kind):
        if kind == "dir":
            p = QFileDialog.getExistingDirectory(self, tr(self.lang, "browse_btn"))
        elif kind == "save":
            p, _ = QFileDialog.getSaveFileName(self, tr(self.lang, "browse_btn"), edit.text() or "auto_output.xlsx", "Excel/CSV (*.xlsx *.csv)")
        else:
            p, _ = QFileDialog.getOpenFileName(self, tr(self.lang, "browse_btn"), "", "CSV (*.csv)")
        if p: edit.setText(p)
    def get_settings(self):
        s = {"language": self.lang_combo.currentData(), "ocr_lang": self.ocr_edit.text(), "ocr_dpi": self.dpi_spin.value(), "hotkey": self.hotkey_edit.text(), "vlm_endpoint": self.ep_edit.text(), "vlm_key": self.key_edit.text(), "vlm_model": self.model_edit.text(), "default_output": self.out_combo.currentText(), "vlm_use_api": self.use_api_chk.isChecked(),
             "vlm_model_size": self.size_combo.currentData(), "master_csv": self.master_edit.text(),
             "optional_ocr": self.optocr_chk.isChecked(), "learning_enabled": self.learn_chk.isChecked(),
             "watch_enabled": self.watch_chk.isChecked(), "watch_folder": self.watch_edit.text(),
             "auto_output_path": self.aout_edit.text(), "auto_done_folder": self.adone_edit.text(),
             "auto_review_folder": self.areview_edit.text(), "auto_threshold": self.th_spin.value(),
             "auto_dest": self.dest_combo.currentData()}
        s["extract_mode"] = self.settings.get("extract_mode", "auto")
        return s

class DownloadWorker(QThread):
    progress = Signal(str, int)
    finished_ok = Signal(bool, str)
    def __init__(self, model_key="3b"):
        super().__init__(); self.model_key = model_key or "3b"
    def run(self):
        try:
            if not vlm_local.find_runtime_binary():
                vlm_local.download_runtime(lambda d, t, f: self.progress.emit(f, int(d * 100 / t) if t else 0))
            vlm_local.download_models(lambda d, t, f: self.progress.emit(f, int(d * 100 / t) if t else 0), model_key=self.model_key)
            self.finished_ok.emit(True, "")
        except Exception as e:
            self.finished_ok.emit(False, str(e))

class GpuDownloadWorker(QThread):
    progress = Signal(str, int)
    finished_ok = Signal(bool, str)
    def __init__(self, flavor):
        super().__init__(); self.flavor = flavor
    def run(self):
        try:
            vlm_local.download_gpu_runtime(self.flavor, lambda d, t, f: self.progress.emit(f, int(d * 100 / t) if t else 0))
            self.finished_ok.emit(True, "")
        except Exception as e:
            self.finished_ok.emit(False, str(e))

class VlmWorker(QThread):
    """v2: full ensemble around the local VLM — self-consistency double read
    (two prompt phrasings), OCR voters when available, merger, arithmetic
    verification and targeted re-read of disputed fields."""
    done_rows = Signal(object)
    failed = Signal(str)
    def __init__(self, image_path, profile, settings=None, few_shot=None, master=None):
        super().__init__(); self.image_path = image_path; self.profile = profile
        self.settings = settings or {}; self.few_shot = few_shot; self.master = master
    def run(self):
        try:
            rows, info = ensemble.run_pipeline(
                self.profile, text="", image_path=self.image_path, settings=self.settings,
                use_vlm=True, few_shot=self.few_shot, master=self.master, verify=True)
            if not any(fr.value for row in rows for fr in row.values()):
                # ensemble produced nothing readable (e.g. VLM unavailable): fall back to a plain read
                rows = vlm_local.run_local_vlm(self.image_path, self.profile,
                                               model_key=self.settings.get("vlm_model_size") or None,
                                               few_shot=self.few_shot)
                info = {"engines": ["vlm"], "arithmetic": {"passed": True, "checks": []}}
            self.done_rows.emit((rows, info))
        except Exception as e:
            self.failed.emit(str(e))

class AutoWorker(QThread):
    """Complete-automation worker: processes files sequentially, unattended."""
    file_done = Signal(object)
    all_done = Signal(object)
    def __init__(self, paths, profile, cfg):
        super().__init__(); self.paths = paths; self.profile = profile; self.cfg = cfg
    def run(self):
        results = []
        for p in self.paths:
            try:
                r = automation_mod.process_file_auto(p, self.profile, self.cfg)
            except Exception as e:
                r = {"decision": "error", "source": os.path.basename(p), "error": str(e), "moved_to": ""}
            results.append(r); self.file_done.emit(r)
        self.all_done.emit(results)

class IntegrationsDialog(QDialog):
    """Core-system integrations (v2, user point I): 4 methods, per-system
    profiles saved as JSON. Data = the rows currently confirmed in the main
    window. Honest note is always visible: using a method needs that
    system's own selectors / import spec / DB details and permission."""
    def __init__(self, mainwin, parent=None):
        super().__init__(parent or mainwin)
        self.mw = mainwin; self.lang = mainwin.lang
        self.setWindowTitle(tr(self.lang, "integration_title")); self.setStyleSheet(STYLE)
        self.resize(1160, 860); self.setMinimumSize(980, 680)
        self.items = integrations_mod.load_integrations()
        if not self.items:
            self.items = [integrations_mod.IntegrationProfile(tr(self.lang, "method_file"), "file", {})]
        self.current = -1
        lay = QVBoxLayout(self); lay.setContentsMargins(16, 14, 16, 14); lay.setSpacing(12)
        lay.addWidget(make_dialog_header("🔗", "#38bdf8", tr(self.lang, "integration_title")))
        opt = QLabel(tr(self.lang, "int_optional_note")); opt.setWordWrap(True)
        opt.setObjectName("noteInfo")
        lay.addWidget(opt)
        self.setAcceptDrops(True)
        note = QLabel(tr(self.lang, "int_honest")); note.setWordWrap(True)
        note.setObjectName("noteWarn")
        lay.addWidget(note)
        body = QHBoxLayout(); body.setSpacing(12); lay.addLayout(body, 1)
        left_card, left = make_card("🗂", "#2563eb", tr(self.lang, "int_profiles")); left_card.setMinimumWidth(300)
        self.listw = QListWidget(); self.listw.setMinimumWidth(230); self.listw.currentRowChanged.connect(self._on_select); left.addWidget(self.listw, 1)
        lgrid = QGridLayout(); lgrid.setSpacing(8)
        for i, (txt, fn) in enumerate([(tr(self.lang, "int_new"), self._new_item), (tr(self.lang, "int_delete"), self._del_item), (tr(self.lang, "export_profile"), self._export_profile), (tr(self.lang, "import_profile"), self._import_profiles)]):
            b = QPushButton(txt); b.setObjectName("secondary"); b.setMinimumHeight(38); b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.clicked.connect(fn); lgrid.addWidget(b, i, 0)
        left.addLayout(lgrid); body.addWidget(left_card)
        right_card, right = make_card("⚙", "#0ea5e9", tr(self.lang, "int_method")); body.addWidget(right_card, 1)
        form = QFormLayout(); form.setSpacing(10); form.setLabelAlignment(Qt.AlignLeft); right.addLayout(form)
        self.name_edit = QLineEdit(); form.addRow(tr(self.lang, "int_name"), self.name_edit)
        self.method_combo = QComboBox()
        for mkey, tkey in (("rpa", "method_rpa"), ("webform", "method_web"), ("file", "method_file"), ("db", "method_db")):
            self.method_combo.addItem(tr(self.lang, tkey), mkey)
        self.method_combo.currentIndexChanged.connect(lambda _i: self.stack.setCurrentIndex(_i))
        form.addRow(tr(self.lang, "int_method"), self.method_combo)
        self.stack = QStackedWidget(); right.addWidget(self.stack, 1)
        self._build_rpa_page(); self._build_web_page(); self._build_file_page(); self._build_db_page()
        self.status_lbl = QLabel(); self.status_lbl.setWordWrap(True); self.status_lbl.setObjectName("statusBar"); self.status_lbl.setMinimumHeight(40); right.addWidget(self.status_lbl)
        bb = QHBoxLayout(); sb = QPushButton("✓ " + tr(self.lang, "save_btn")); sb.setObjectName("bigPrimary"); sb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); sb.clicked.connect(self._save_all)
        cb = QPushButton(tr(self.lang, "cancel_btn")); cb.setObjectName("secondary"); cb.clicked.connect(self.reject); bb.addWidget(sb, 2); bb.addWidget(cb, 1); lay.addLayout(bb)
        self._refresh_list(); self.listw.setCurrentRow(0)
    # ------------------------------------------------------------ pages ----
    def _page(self):
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background:transparent;")
        w = QWidget(); w.setStyleSheet("background:transparent;")
        l = QVBoxLayout(w); l.setContentsMargins(4, 4, 4, 4); l.setSpacing(10)
        scroll.setWidget(w); self.stack.addWidget(scroll); return l
    def _build_rpa_page(self):
        l = self._page()
        hint = QLabel(tr(self.lang, "rpa_hint")); hint.setWordWrap(True); hint.setStyleSheet("color:#486581; font-size:12px;"); l.addWidget(hint)
        f = QFormLayout(); f.setSpacing(10); l.addLayout(f)
        self.rpa_interval = QSpinBox(); self.rpa_interval.setRange(0, 2000); self.rpa_interval.setValue(150); self.rpa_interval.setSuffix(" ms")
        f.addRow(tr(self.lang, "rpa_interval"), self.rpa_interval)
        self.rpa_click_chk = QCheckBox(tr(self.lang, "rpa_click_enable")); l.addWidget(self.rpa_click_chk)
        row = QHBoxLayout(); self.rpa_pos_lbl = QLabel(tr(self.lang, "rpa_pos_none")); row.addWidget(self.rpa_pos_lbl, 1)
        rb = QPushButton(tr(self.lang, "rpa_record")); rb.setObjectName("secondary"); rb.clicked.connect(self._record_pos); row.addWidget(rb); l.addLayout(row)
        self._rec_timer = None; self._rec_ticks = 0
        eb = QPushButton("⌨ " + tr(self.lang, "rpa_execute")); eb.setObjectName("primaryBlue"); eb.clicked.connect(self._execute_rpa); l.addWidget(eb)
        l.addStretch()
    def _build_web_page(self):
        l = self._page()
        f = QFormLayout(); f.setSpacing(10); l.addLayout(f)
        self.web_url = QLineEdit(); f.addRow(tr(self.lang, "web_url"), self.web_url)
        self.web_table = QTableWidget(0, 2); self.web_table.setHorizontalHeaderLabels([tr(self.lang, "target_column"), tr(self.lang, "web_selector")])
        self.web_table.horizontalHeader().setStretchLastSection(True); self.web_table.setMinimumHeight(150); l.addWidget(self.web_table, 1)
        row = QHBoxLayout()
        for txt, fn in ((tr(self.lang, "web_copy"), self._copy_bookmarklet), (tr(self.lang, "web_save"), self._save_bookmarklet)):
            b = QPushButton(txt); b.setObjectName("secondary"); b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); b.clicked.connect(fn); row.addWidget(b)
        l.addLayout(row)
        sb2 = QPushButton(tr(self.lang, "web_selenium")); sb2.setObjectName("secondary"); sb2.clicked.connect(self._selenium_fill); l.addWidget(sb2)
        row2 = QHBoxLayout()
        lb = QPushButton("🎓 " + tr(self.lang, "web_learn_copy")); lb.setObjectName("secondary"); lb.setMinimumHeight(40); lb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); lb.clicked.connect(self._copy_learn); row2.addWidget(lb)
        mb = QPushButton("📥 " + tr(self.lang, "web_import_map")); mb.setObjectName("secondary"); mb.setMinimumHeight(40); mb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); mb.clicked.connect(self._import_map); row2.addWidget(mb)
        l.addLayout(row2)
    def _build_file_page(self):
        l = self._page()
        f = QFormLayout(); f.setSpacing(10); l.addLayout(f)
        self.file_format = QComboBox(); self.file_format.addItems(["csv", "tsv", "xlsx"]); f.addRow(tr(self.lang, "file_format"), self.file_format)
        self.file_enc = QComboBox(); self.file_enc.addItems(["utf-8", "shift_jis"]); f.addRow(tr(self.lang, "file_encoding"), self.file_enc)
        self.file_nl = QComboBox(); self.file_nl.addItems(["crlf", "lf"]); f.addRow(tr(self.lang, "file_newline"), self.file_nl)
        self.file_datefmt = QLineEdit(); f.addRow(tr(self.lang, "file_date_format"), self.file_datefmt)
        self.file_pattern = QLineEdit("export_{date}.csv"); f.addRow(tr(self.lang, "file_pattern"), self.file_pattern)
        self.file_header = QCheckBox(tr(self.lang, "file_header")); self.file_header.setChecked(True); l.addWidget(self.file_header)
        lbl = QLabel(tr(self.lang, "file_columns")); lbl.setObjectName("sectionLabel"); l.addWidget(lbl)
        crow = QHBoxLayout(); self.file_cols = QListWidget(); self.file_cols.setMinimumHeight(110); crow.addWidget(self.file_cols, 1)
        mv = QVBoxLayout(); ub = QPushButton(tr(self.lang, "up_btn")); ub.setObjectName("secondary"); ub.clicked.connect(lambda: self._move_col(-1)); mv.addWidget(ub)
        dbn = QPushButton(tr(self.lang, "down_btn")); dbn.setObjectName("secondary"); dbn.clicked.connect(lambda: self._move_col(1)); mv.addWidget(dbn); crow.addLayout(mv); l.addLayout(crow)
        eb = QPushButton("📤 " + tr(self.lang, "file_export")); eb.setObjectName("primaryBlue"); eb.clicked.connect(self._export_file); l.addWidget(eb)
        ib2 = QPushButton("🔍 " + tr(self.lang, "file_infer")); ib2.setObjectName("secondary"); ib2.clicked.connect(self._infer_btn); l.addWidget(ib2)
    def _build_db_page(self):
        l = self._page()
        f = QFormLayout(); f.setSpacing(10); l.addLayout(f)
        self.db_kind = QComboBox(); self.db_kind.addItems(["sqlite", "odbc"]); f.addRow(tr(self.lang, "db_kind"), self.db_kind)
        self.db_conn = QLineEdit(); f.addRow(tr(self.lang, "db_conn"), self.db_conn)
        self.db_table_combo = QComboBox(); self.db_table_combo.setEditable(True); f.addRow(tr(self.lang, "db_table"), self.db_table_combo)
        alab = QLabel(tr(self.lang, "db_assist")); alab.setObjectName("sectionLabel"); l.addWidget(alab)
        af = QFormLayout(); af.setSpacing(10); l.addLayout(af)
        self.db_server = QLineEdit(); af.addRow(tr(self.lang, "db_server"), self.db_server)
        self.db_database = QLineEdit(); af.addRow(tr(self.lang, "db_database"), self.db_database)
        arow = QHBoxLayout()
        sbf = QPushButton(tr(self.lang, "db_browse_sqlite")); sbf.setObjectName("secondary"); sbf.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); sbf.clicked.connect(self._db_browse_sqlite); arow.addWidget(sbf)
        tbf = QPushButton(tr(self.lang, "db_test")); tbf.setObjectName("secondary"); tbf.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); tbf.clicked.connect(self._db_test); arow.addWidget(tbf)
        l.addLayout(arow)
        self.db_test_lbl = QLabel(); self.db_test_lbl.setWordWrap(True); self.db_test_lbl.setStyleSheet("color:#24507e; font-weight:bold;"); l.addWidget(self.db_test_lbl)
        self.db_table = QTableWidget(0, 2); self.db_table.setHorizontalHeaderLabels([tr(self.lang, "target_column"), tr(self.lang, "db_column")])
        self.db_table.horizontalHeader().setStretchLastSection(True); self.db_table.setMinimumHeight(150); l.addWidget(self.db_table, 1)
        self.db_enable = QCheckBox(tr(self.lang, "db_enable")); l.addWidget(self.db_enable)
        row = QHBoxLayout()
        pb = QPushButton(tr(self.lang, "db_dryrun")); pb.setObjectName("secondary"); pb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); pb.clicked.connect(self._db_dryrun); row.addWidget(pb)
        wb = QPushButton(tr(self.lang, "db_write")); wb.setObjectName("primaryBlue"); wb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); wb.clicked.connect(self._db_write); row.addWidget(wb)
        l.addLayout(row)
        pl = QLabel(tr(self.lang, "db_preview")); pl.setObjectName("sectionLabel"); l.addWidget(pl)
        self.db_preview_txt = QTextEdit(); self.db_preview_txt.setReadOnly(True); self.db_preview_txt.setMinimumHeight(90); l.addWidget(self.db_preview_txt)
    # ------------------------------------------------------------- state ----
    def _cols(self):
        return [f.target_column for f in self.mw.current_profile.fields]
    def _rows_dicts(self):
        if not self.mw.rows: self.mw.run_extract()
        return rows_to_dicts(self.mw.rows, self.mw.current_profile)
    def _refresh_list(self):
        self.listw.blockSignals(True); self.listw.clear()
        for ip in self.items: self.listw.addItem(ip.name or ip.method)
        self.listw.blockSignals(False)
    def _on_select(self, idx):
        if self.current >= 0 and self.current < len(self.items) and idx != self.current:
            self._save_form(self.items[self.current])
        self.current = idx
        if 0 <= idx < len(self.items): self._load_form(self.items[idx])
    def _new_item(self):
        self.items.append(integrations_mod.IntegrationProfile(tr(self.lang, "method_file") + f" {len(self.items)+1}", "file", {}))
        self._refresh_list(); self.listw.setCurrentRow(len(self.items) - 1)
    def _del_item(self):
        if 0 <= self.current < len(self.items):
            del self.items[self.current]; self.current = -1; self._refresh_list()
            if self.items: self.listw.setCurrentRow(0)
    def _fill_map_table(self, table, mapping):
        cols = self._cols(); table.setRowCount(len(cols))
        for r, c in enumerate(cols):
            it = QTableWidgetItem(c); it.setFlags(it.flags() & ~Qt.ItemIsEditable); table.setItem(r, 0, it)
            table.removeCellWidget(r, 1)
            table.setItem(r, 1, QTableWidgetItem((mapping or {}).get(c, "")))
    def _read_map_table(self, table):
        out = {}
        for r in range(table.rowCount()):
            k = table.item(r, 0).text() if table.item(r, 0) else ""
            w = table.cellWidget(r, 1)
            if isinstance(w, QComboBox):
                v = w.currentText().strip()
            else:
                v = table.item(r, 1).text().strip() if table.item(r, 1) else ""
            if k and v: out[k] = v
        return out
    def _load_form(self, ip):
        cfg = ip.config
        self.name_edit.setText(ip.name)
        self.method_combo.setCurrentIndex(["rpa", "webform", "file", "db"].index(ip.method)); self.stack.setCurrentIndex(self.method_combo.currentIndex())
        self.rpa_interval.setValue(int(cfg.get("rpa_interval_ms", 150) or 150))
        self.rpa_click_chk.setChecked(bool(cfg.get("rpa_click_enabled", False)))
        if cfg.get("rpa_click_x") is not None:
            self.rpa_pos_lbl.setText(f"({cfg.get('rpa_click_x')}, {cfg.get('rpa_click_y')})")
        else:
            self.rpa_pos_lbl.setText(tr(self.lang, "rpa_pos_none"))
        self.web_url.setText(cfg.get("web_url", ""))
        self._fill_map_table(self.web_table, cfg.get("web_mapping") or {})
        self.file_format.setCurrentText(cfg.get("format", "csv")); self.file_enc.setCurrentText(cfg.get("encoding", "utf-8"))
        self.file_nl.setCurrentText(cfg.get("newline", "crlf")); self.file_datefmt.setText(cfg.get("date_format", ""))
        self.file_pattern.setText(cfg.get("filename_pattern", "export_{date}.csv")); self.file_header.setChecked(bool(cfg.get("header", True)))
        self.file_cols.clear(); self.file_cols.addItems(integrations_mod.ordered_columns(cfg, self._cols()))
        self.db_kind.setCurrentText(cfg.get("db_kind", "sqlite")); self.db_conn.setText(cfg.get("connection", "")); self.db_table_combo.setCurrentText(cfg.get("table", ""))
        self.db_server.setText(cfg.get("db_server", "")); self.db_database.setText(cfg.get("db_database", ""))
        self._fill_map_table(self.db_table, cfg.get("column_mapping") or {})
        self.db_enable.setChecked(bool(cfg.get("db_write_enabled", False)))
    def _save_form(self, ip):
        cfg = dict(ip.config)
        cfg.update({"rpa_interval_ms": self.rpa_interval.value(), "rpa_click_enabled": self.rpa_click_chk.isChecked(),
                    "web_url": self.web_url.text(), "web_mapping": self._read_map_table(self.web_table),
                    "format": self.file_format.currentText(), "encoding": self.file_enc.currentText(), "newline": self.file_nl.currentText(),
                    "date_format": self.file_datefmt.text(), "filename_pattern": self.file_pattern.text(), "header": self.file_header.isChecked(),
                    "column_order": [self.file_cols.item(i).text() for i in range(self.file_cols.count())],
                    "db_kind": self.db_kind.currentText(), "connection": self.db_conn.text(), "table": self.db_table_combo.currentText(),
                    "db_server": self.db_server.text(), "db_database": self.db_database.text(),
                    "column_mapping": self._read_map_table(self.db_table), "db_write_enabled": self.db_enable.isChecked()})
        if cfg.get("db_kind") == "odbc" and cfg.get("db_server"):
            cfg["connection"] = integrations_mod.build_odbc_connection(cfg.get("db_server", ""), cfg.get("db_database", ""))
        ip.config = cfg; ip.name = self.name_edit.text(); ip.method = self.method_combo.currentData()
    def _save_all(self):
        if 0 <= self.current < len(self.items): self._save_form(self.items[self.current])
        integrations_mod.save_integrations(self.items); self.accept()
    def _cur(self):
        if 0 <= self.current < len(self.items):
            self._save_form(self.items[self.current]); return self.items[self.current]
        return None
    # ------------------------------------------------------- setup assist ----
    def _export_profile(self):
        ip = self._cur()
        if ip is None: return
        p, _ = QFileDialog.getSaveFileName(self, tr(self.lang, "export_profile"), "integration_profile.json", "JSON (*.json)")
        if p:
            integrations_mod.export_integration_profile(ip, p)
            self.status_lbl.setText("✓ " + tr(self.lang, "exported_msg") + f": {p}")
    def _import_profiles(self):
        p, _ = QFileDialog.getOpenFileName(self, tr(self.lang, "import_profile"), "", "JSON (*.json)")
        if not p: return
        try:
            new = integrations_mod.import_integration_profiles(p)
        except Exception as e:
            self.status_lbl.setText(str(e)); return
        self.items.extend(new); self._refresh_list()
        if new: self.listw.setCurrentRow(len(self.items) - 1)
    def _copy_learn(self):
        js = integrations_mod.generate_learn_bookmarklet(self._cols())
        QApplication.clipboard().setText(js); self.status_lbl.setText("✓ " + tr(self.lang, "copied_msg"))
    def _import_map(self):
        text, ok = QInputDialog.getMultiLineText(self, tr(self.lang, "web_import_map"), "JSON", QApplication.clipboard().text())
        if not ok: return
        mapping = integrations_mod.parse_mapping_json(text)
        if mapping:
            self._fill_map_table(self.web_table, mapping)
            self.status_lbl.setText("✓ " + tr(self.lang, "web_map_imported"))
    def _infer_btn(self):
        p, _ = QFileDialog.getOpenFileName(self, tr(self.lang, "file_infer"), "", "CSV/TSV/Text (*.csv *.tsv *.txt)")
        if p: self._infer_from_path(p)
    def _infer_from_path(self, path):
        try:
            with open(path, "rb") as f: data = f.read()
            spec = integrations_mod.infer_import_spec(data)
        except Exception as e:
            self.status_lbl.setText(str(e)); return
        self.file_format.setCurrentText(spec["format"]); self.file_enc.setCurrentText(spec["encoding"])
        self.file_nl.setCurrentText(spec["newline"]); self.file_header.setChecked(bool(spec["header"]))
        if spec.get("columns"):
            cols = [c for c in spec["columns"] if c in self._cols()] + [c for c in self._cols() if c not in spec["columns"]]
            self.file_cols.clear(); self.file_cols.addItems(cols)
        self.stack.setCurrentIndex(2); self.method_combo.setCurrentIndex(2)
        self.status_lbl.setText("✓ " + tr(self.lang, "file_infer_done"))
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
    def dropEvent(self, e):
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if os.path.splitext(p)[1].lower() in (".csv", ".tsv", ".txt"):
                self._infer_from_path(p); return
    def _db_browse_sqlite(self):
        p, _ = QFileDialog.getOpenFileName(self, tr(self.lang, "db_browse_sqlite"), "", "SQLite (*.db *.sqlite *.sqlite3);;All (*.*)")
        if p:
            self.db_kind.setCurrentText("sqlite"); self.db_conn.setText(p)
    def _db_test(self):
        ip = self._cur()
        if ip is None: return
        cfg = dict(ip.config)
        if cfg.get("db_kind") == "odbc" and cfg.get("db_server"):
            cfg["connection"] = integrations_mod.build_odbc_connection(cfg.get("db_server", ""), cfg.get("db_database", ""))
        ok, msg, tables = integrations_mod.test_connection(cfg)
        if ok:
            self.db_test_lbl.setText("✓ " + tr(self.lang, "db_test_ok") + f" ({len(tables)})")
            cur = self.db_table_combo.currentText()
            self.db_table_combo.clear(); self.db_table_combo.addItems(tables); self.db_table_combo.setCurrentText(cur)
            table = self.db_table_combo.currentText()
            if table:
                try:
                    cols = integrations_mod.list_db_columns(cfg, table)
                    if cols: self._fill_db_columns(cols)
                except Exception: pass
        else:
            self.db_test_lbl.setText("✗ " + tr(self.lang, "db_test_ng") + f": {msg}")
    def _fill_db_columns(self, columns):
        mapping = self._read_map_table(self.db_table)
        cols = self._cols(); self.db_table.setRowCount(len(cols))
        for r, c in enumerate(cols):
            it = QTableWidgetItem(c); it.setFlags(it.flags() & ~Qt.ItemIsEditable); self.db_table.setItem(r, 0, it)
            combo = QComboBox(); combo.setEditable(True); combo.addItem(""); combo.addItems(columns)
            combo.setCurrentText(mapping.get(c, ""))
            self.db_table.setCellWidget(r, 1, combo)
        # ---------------------------------------------------------------- RPA ----
    def _record_pos(self):
        # Poll for the user's real click on the target app's register button
        # (win32: left-button state via GetAsyncKeyState; elsewhere: cursor
        # position after 3 s). The recorded point is the ONLY point the
        # optional final click will ever use.
        self.status_lbl.setText(tr(self.lang, "rpa_record") + " …")
        self._rec_ticks = 0
        self._rec_timer = QTimer(self); self._rec_timer.setInterval(100); self._rec_timer.timeout.connect(self._rec_poll); self._rec_timer.start()
    def _rec_poll(self):
        self._rec_ticks += 1
        clicked = False
        if sys.platform.startswith("win"):
            try:
                import ctypes
                clicked = bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
            except Exception: pass
        if clicked or self._rec_ticks >= 30:
            self._rec_timer.stop()
            pos = QCursor.pos()
            ip = self.items[self.current] if 0 <= self.current < len(self.items) else None
            if ip is not None:
                ip.config["rpa_click_x"] = pos.x(); ip.config["rpa_click_y"] = pos.y()
            self.rpa_pos_lbl.setText(f"({pos.x()}, {pos.y()})")
            self.status_lbl.setText(tr(self.lang, "rpa_record") + f": ({pos.x()}, {pos.y()})")
    def _execute_rpa(self):
        ip = self._cur()
        if ip is None: return
        dicts = self._rows_dicts()
        cols = self._cols()
        values = [d.get(c, "") for d in dicts for c in cols]
        if not values: return
        # 3-second countdown dialog; Esc cancels.
        dlg = QDialog(self); dlg.setWindowTitle(tr(self.lang, "rpa_execute")); dlg.setStyleSheet(STYLE); dlg.resize(420, 230)
        ll = QVBoxLayout(dlg); ll.setContentsMargins(16, 14, 16, 14); ll.setSpacing(12)
        ll.addWidget(make_dialog_header("⌨", "#38bdf8", tr(self.lang, "rpa_execute")))
        lab = QLabel(); lab.setAlignment(Qt.AlignCenter); lab.setWordWrap(True); lab.setStyleSheet("font-size:20px; font-weight:bold; color:#173a7d;"); ll.addWidget(lab, 1)
        state = {"n": 3, "cancel": False}
        def _tick():
            if state["n"] <= 0:
                timer.stop(); dlg.accept(); return
            lab.setText(f"{state['n']} " + tr(self.lang, "rpa_countdown")); state["n"] -= 1
        timer = QTimer(dlg); timer.setInterval(1000); timer.timeout.connect(_tick)
        dlg.keyPressEvent = lambda e: (state.update(cancel=True), timer.stop(), dlg.reject()) if e.key() == Qt.Key_Escape else None
        _tick(); timer.start()
        if dlg.exec() != QDialog.Accepted or state["cancel"]:
            self.status_lbl.setText(tr(self.lang, "rpa_aborted")); return
        try:
            sender = integrations_mod.make_sender()
        except Exception as e:
            self.status_lbl.setText(str(e)); return
        res = integrations_mod.rpa_type_values(values, sender, interval_ms=int(ip.config.get("rpa_interval_ms", 150) or 150),
                                               should_abort=integrations_mod.esc_pressed)
        if res["aborted"]:
            self.status_lbl.setText(tr(self.lang, "rpa_aborted")); return
        clicked = integrations_mod.rpa_finish_click(ip.config, sender)
        self.status_lbl.setText("✓ " + tr(self.lang, "rpa_done") + (f" + click({ip.config.get('rpa_click_x')},{ip.config.get('rpa_click_y')})" if clicked else ""))
    # ---------------------------------------------------------------- Web ----
    def _web_row(self):
        dicts = self._rows_dicts()
        return dicts[0] if dicts else {c: "" for c in self._cols()}
    def _copy_bookmarklet(self):
        ip = self._cur()
        js = integrations_mod.generate_bookmarklet(self._read_map_table(self.web_table), self._web_row())
        QApplication.clipboard().setText(js); self.status_lbl.setText("✓ " + tr(self.lang, "copied_msg"))
    def _save_bookmarklet(self):
        js = integrations_mod.generate_bookmarklet(self._read_map_table(self.web_table), self._web_row())
        p, _ = QFileDialog.getSaveFileName(self, tr(self.lang, "web_save"), "bookmarklet.txt", "Text (*.txt)")
        if p:
            with open(p, "w", encoding="utf-8") as f: f.write(js)
            self.status_lbl.setText("✓ " + tr(self.lang, "exported_msg") + f": {p}")
    def _selenium_fill(self):
        try:
            integrations_mod.fill_form_selenium(self.web_url.text(), self._read_map_table(self.web_table), self._web_row())
            self.status_lbl.setText("✓ selenium")
        except Exception:
            self.status_lbl.setText(tr(self.lang, "web_selenium_na"))
    # --------------------------------------------------------------- File ----
    def _move_col(self, d):
        r = self.file_cols.currentRow(); nr = r + d
        if r < 0 or nr < 0 or nr >= self.file_cols.count(): return
        it = self.file_cols.takeItem(r); self.file_cols.insertItem(nr, it); self.file_cols.setCurrentRow(nr)
    def _export_file(self):
        ip = self._cur()
        if ip is None: return
        fname = integrations_mod.resolve_filename(ip.config.get("filename_pattern") or "export_{date}.csv", self.mw.current_profile.name)
        p, _ = QFileDialog.getSaveFileName(self, tr(self.lang, "file_export"), fname, "CSV/TSV/Excel (*.csv *.tsv *.xlsx)")
        if not p: return
        integrations_mod.export_import_file(self._rows_dicts(), self._cols(), ip.config, p)
        self.status_lbl.setText("✓ " + tr(self.lang, "file_exported") + p)
    # ----------------------------------------------------------------- DB ----
    def _db_cfg(self):
        ip = self._cur()
        return dict(ip.config) if ip else {}
    def _db_dryrun(self):
        try:
            preview = integrations_mod.db_preview(self._db_cfg(), self._rows_dicts())
            self.db_preview_txt.setPlainText("\n".join(f"{sql}  -- {params}" for sql, params in preview))
        except Exception as e:
            self.db_preview_txt.setPlainText(str(e))
    def _db_write(self):
        cfg = self._db_cfg()
        try:
            res = integrations_mod.db_write(cfg, self._rows_dicts())
        except Exception as e:
            self.db_preview_txt.setPlainText(str(e)); return
        if res["dry_run"]:
            self.db_preview_txt.setPlainText("\n".join(f"{sql}  -- {params}" for sql, params in res["preview"]))
            self.status_lbl.setText(tr(self.lang, "db_dryrun"))
        else:
            try:
                automation_mod.write_audit({"timestamp": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
                                            "decision": "db_write", "profile": self.mw.current_profile.name,
                                            "table": cfg.get("table", ""), "written": res["written"],
                                            "values": self._rows_dicts()})
            except Exception: pass
            self.status_lbl.setText(f"✓ {res['written']} " + tr(self.lang, "db_written"))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings(); self.lang = self.settings.get("language", "ja")
        self.profiles = preset_profiles()
        try:
            d = get_app_dir()
            for fn in os.listdir(d):
                if fn.endswith(".json") and fn != "settings.json":
                    try:
                        p = load_profile(os.path.join(d, fn))
                        if p.name not in [x.name for x in self.profiles]: self.profiles.append(p)
                    except Exception: pass
        except Exception: pass
        self.current_profile = self.profiles[0]
        self.rows = []; self.current_file = None; self.current_image_path = None
        self.source_kind = "none"; self._vlm_worker = None; self._dl_worker = None; self._pending_vlm = False
        self._orig_snapshot = {}; self._last_info = None; self._auto_worker = None
        self._watch_seen = set(); self._vendor_checked = False
        self.setWindowTitle(tr(self.lang, "app_title")); self.resize(1320, 980); self.setMinimumSize(1040, 760); self.setStyleSheet(STYLE)
        self._build_ui(); self.retranslate()
        # v2: watch-folder automation (poll every 3 seconds)
        self._watch_timer = QTimer(self); self._watch_timer.setInterval(3000); self._watch_timer.timeout.connect(self._watch_tick); self._watch_timer.start()
        self.shortcut = QShortcut(QKeySequence(self.settings.get("hotkey", "Ctrl+Shift+S")), self); self.shortcut.activated.connect(self.capture_screen)
        self._try_global_hotkey()
    def _try_global_hotkey(self):
        if sys.platform != "win32": return
        try:
            import ctypes
            ctypes.windll.user32.RegisterHotKey(None, 1, 0x0002 | 0x0004, 0x53)
        except Exception: pass
    def _build_ui(self):
        # Whole content lives in a scroll area: at short window heights the
        # page scrolls instead of squeezing cards until labels overlap.
        _scroll = QScrollArea(); _scroll.setWidgetResizable(True); _scroll.setFrameShape(QFrame.NoFrame)
        self.setCentralWidget(_scroll)
        central = QWidget(); _scroll.setWidget(central)
        main = QVBoxLayout(central); main.setContentsMargins(16, 14, 16, 14); main.setSpacing(12)
        # ---- header ----
        header = QFrame(); header.setObjectName("header"); add_shadow(header, 22, 6, 90)
        hl = QVBoxLayout(header); hl.setContentsMargins(20, 16, 20, 16); hl.setSpacing(10)
        top = QHBoxLayout(); top.setSpacing(14)
        top.addWidget(make_badge("🧾", "#38bdf8", 56))
        tv = QVBoxLayout(); tv.setSpacing(2)
        self.title_lbl = QLabel(); self.title_lbl.setObjectName("appTitle"); self.title_lbl.setWordWrap(True); tv.addWidget(self.title_lbl)
        self.sub_lbl = QLabel(); self.sub_lbl.setObjectName("appSub"); self.sub_lbl.setWordWrap(True); tv.addWidget(self.sub_lbl)
        top.addLayout(tv, 1)
        pill = QFrame(); pill.setObjectName("langPill"); pl = QHBoxLayout(pill); pl.setContentsMargins(12, 8, 12, 8); pl.setSpacing(8)
        self.lang_lbl = QLabel(); self.lang_lbl.setObjectName("headerLabel"); pl.addWidget(self.lang_lbl)
        self.lang_combo = QComboBox(); self.lang_combo.setMinimumWidth(150); self.lang_combo.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        for code in LANG_ORDER: self.lang_combo.addItem(LANG_NAMES[code], code)
        self.lang_combo.setCurrentIndex(LANG_ORDER.index(self.lang) if self.lang in LANG_ORDER else 0); self.lang_combo.currentIndexChanged.connect(self.on_lang_change); pl.addWidget(self.lang_combo)
        top.addWidget(pill, 0, Qt.AlignTop)
        hl.addLayout(top)
        prow = QHBoxLayout(); prow.setSpacing(9)
        self.profile_lbl = QLabel(); self.profile_lbl.setObjectName("headerLabel"); prow.addWidget(self.profile_lbl)
        self.profile_combo = QComboBox(); self.profile_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); self.profile_combo.addItems([p.name for p in self.profiles]); self.profile_combo.currentIndexChanged.connect(self.on_profile_change); prow.addWidget(self.profile_combo, 1)
        self.edit_profile_btn = QPushButton(); self.edit_profile_btn.setObjectName("headerBtn"); self.edit_profile_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed); self.edit_profile_btn.clicked.connect(self.edit_profile); prow.addWidget(self.edit_profile_btn)
        self.settings_btn = QPushButton(); self.settings_btn.setObjectName("headerBtn"); self.settings_btn.clicked.connect(self.open_settings); prow.addWidget(self.settings_btn)
        self.int_btn = QPushButton(); self.int_btn.setObjectName("headerBtn"); self.int_btn.clicked.connect(self.open_integrations); prow.addWidget(self.int_btn)
        hl.addLayout(prow); main.addWidget(header)
        # ---- drop zone ----
        self.drop = DropZone(); self.drop.callback = self.load_file; self.drop.click_select = self.select_file
        self.drop.callback_multi = self.load_files; self.drop.want_multi = True; main.addWidget(self.drop)
        # ---- extraction mode bar (rules / auto / local VLM image understanding) ----
        mode_frame = QFrame(); mode_frame.setObjectName("card"); add_shadow(mode_frame, 16, 4, 45)
        ml = QVBoxLayout(mode_frame); ml.setContentsMargins(14, 10, 14, 10); ml.setSpacing(6)
        mrow = QHBoxLayout(); mrow.setSpacing(9)
        self.mode_lbl = QLabel(); self.mode_lbl.setObjectName("cardTitle"); mrow.addWidget(self.mode_lbl)
        self.mode_combo = QComboBox(); self.mode_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.mode_combo.addItem("", "auto"); self.mode_combo.addItem("", "rules"); self.mode_combo.addItem("", "local_vlm")
        _mi = {"auto": 0, "rules": 1, "local_vlm": 2}.get(self.settings.get("extract_mode", "auto"), 0); self.mode_combo.setCurrentIndex(_mi)
        self.mode_combo.currentIndexChanged.connect(self.on_mode_change); mrow.addWidget(self.mode_combo, 1)
        self.vlm_dl_btn = QPushButton(); self.vlm_dl_btn.setObjectName("secondary"); self.vlm_dl_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed); self.vlm_dl_btn.clicked.connect(self.start_model_download); mrow.addWidget(self.vlm_dl_btn)
        ml.addLayout(mrow)
        self.vlm_note = QLabel(); self.vlm_note.setWordWrap(True); self.vlm_note.setStyleSheet("color:#486581; font-size:12px;"); ml.addWidget(self.vlm_note)
        main.addWidget(mode_frame)
        # ---- action row ----
        brow = QHBoxLayout(); brow.setSpacing(10)
        self.select_btn = QPushButton(); self.select_btn.setObjectName("secondary"); self.select_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); self.select_btn.clicked.connect(self.select_file); brow.addWidget(self.select_btn, 1)
        self.capture_btn = QPushButton(); self.capture_btn.setObjectName("secondary"); self.capture_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); self.capture_btn.clicked.connect(self.capture_screen); brow.addWidget(self.capture_btn, 1)
        self.extract_btn = QPushButton(); self.extract_btn.setObjectName("primaryBlue"); self.extract_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); self.extract_btn.clicked.connect(self.run_extract); brow.addWidget(self.extract_btn, 2)
        self.vlm_btn = QPushButton(); self.vlm_btn.setObjectName("secondary"); self.vlm_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); self.vlm_btn.clicked.connect(self.run_vlm); brow.addWidget(self.vlm_btn, 1)
        main.addLayout(brow)
        # ---- cards splitter ----
        splitter = QSplitter(Qt.Horizontal); splitter.setHandleWidth(10)
        self.src_card, sl = make_card("📄", "#2563eb", "")
        self.text_edit = QTextEdit(); self.text_edit.setMinimumHeight(110); sl.addWidget(self.text_edit, 1)
        self.img_lbl = QLabel(); self.img_lbl.setAlignment(Qt.AlignCenter); self.img_lbl.setMinimumHeight(70)
        self.img_lbl.setStyleSheet("background:#f4f8ff; border:1.5px dashed #b9d2ee; border-radius:10px; color:#7c93ad;")
        sl.addWidget(self.img_lbl)
        splitter.addWidget(self.src_card)
        self.prev_card, pv = make_card("✓", "#16a34a", "")
        legend = QHBoxLayout(); legend.setSpacing(8)
        self.legend_labels = []
        for key, col in [("legend_high", "#86d97a"), ("legend_mid", "#ffe066"), ("legend_low", "#ff9d9d")]:
            lab = QLabel(); lab.setWordWrap(True); lab.setStyleSheet(f"background:{col}; color:#243b1e; border:1px solid rgba(0,0,0,0.12); border-radius:9px; padding:5px 9px; font-size:12px; font-weight:bold;")
            lab.setProperty("i18n_key", key); self.legend_labels.append(lab); legend.addWidget(lab, 1)
        pv.addLayout(legend)
        self.table = QTableWidget(); self.table.setMinimumHeight(130); self.table.itemChanged.connect(self.on_cell_changed); pv.addWidget(self.table, 1)
        splitter.addWidget(self.prev_card); splitter.setSizes([540, 720]); main.addWidget(splitter, 1)
        # ---- v2: complete automation panel ----
        self.auto_card, al = make_card("🤖", "#f59e0b", "")
        arow0 = QHBoxLayout(); arow0.setSpacing(10)
        self.auto_chk = QCheckBox(); self.auto_chk.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); arow0.addWidget(self.auto_chk, 1)
        self.watch_status_lbl = QLabel(); self.watch_status_lbl.setStyleSheet("color:#486581; font-size:12px; font-weight:bold;"); arow0.addWidget(self.watch_status_lbl)
        al.addLayout(arow0)
        self.auto_hint_lbl = QLabel(); self.auto_hint_lbl.setWordWrap(True); self.auto_hint_lbl.setStyleSheet("color:#486581; font-size:12px;"); al.addWidget(self.auto_hint_lbl)
        self.auto_note2_lbl = QLabel(); self.auto_note2_lbl.setWordWrap(True)
        self.auto_note2_lbl.setObjectName("noteWarn"); self.auto_note2_lbl.setMinimumHeight(46)
        al.addWidget(self.auto_note2_lbl)
        self.review_title_lbl = QLabel(); self.review_title_lbl.setObjectName("sectionLabel"); al.addWidget(self.review_title_lbl)
        self.review_list = QListWidget(); self.review_list.setMinimumHeight(44); self.review_list.setMaximumHeight(80)
        self.review_list.itemClicked.connect(self._open_review_item); al.addWidget(self.review_list)
        self.auto_result_lbl = QLabel(); self.auto_result_lbl.setWordWrap(True); self.auto_result_lbl.setStyleSheet("color:#24507e; font-weight:bold;"); al.addWidget(self.auto_result_lbl)
        main.addWidget(self.auto_card)
        # ---- confirm row ----
        arow = QHBoxLayout(); arow.setSpacing(10)
        self.copy_btn = QPushButton(); self.copy_btn.setObjectName("bigPrimary"); self.copy_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); self.copy_btn.clicked.connect(self.copy_tsv); arow.addWidget(self.copy_btn, 2)
        self.xlsx_btn = QPushButton(); self.xlsx_btn.setObjectName("secondary"); self.xlsx_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); self.xlsx_btn.clicked.connect(self.export_xlsx); arow.addWidget(self.xlsx_btn, 1)
        self.csv_btn = QPushButton(); self.csv_btn.setObjectName("secondary"); self.csv_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); self.csv_btn.clicked.connect(self.export_csv_file); arow.addWidget(self.csv_btn, 1)
        self.json_btn = QPushButton(); self.json_btn.setObjectName("secondary"); self.json_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); self.json_btn.clicked.connect(self.copy_json); arow.addWidget(self.json_btn, 1)
        main.addLayout(arow)
        self.status_lbl = QLabel(); self.status_lbl.setWordWrap(True)
        self.status_lbl.setStyleSheet("background:#ffffff; border:1.5px solid #b9d2ee; border-bottom:3px solid #8fb4dd; border-radius:10px; padding:8px 12px; color:#24507e; font-weight:bold;")
        main.addWidget(self.status_lbl)
    def retranslate(self):
        L = self.lang
        self.setWindowTitle(tr(L, "app_title")); self.title_lbl.setText(tr(L, "app_title")); self.sub_lbl.setText(tr(L, "subtitle"))
        self.lang_lbl.setText("🌐 " + tr(L, "language_label")); self.profile_lbl.setText(tr(L, "profile_label")); self.edit_profile_btn.setText("✎ " + tr(L, "edit_profile")); self.settings_btn.setText("⚙ " + tr(L, "settings_btn")); self.int_btn.setText("🔗 " + tr(L, "integration_btn"))
        self.drop.set_texts("📥  " + tr(L, "drop_here"), tr(L, "drop_hint"))
        self.select_btn.setText("📂 " + tr(L, "click_select")); self.capture_btn.setText("📷 " + tr(L, "capture")); self.extract_btn.setText("✨ " + tr(L, "extract_btn")); self.vlm_btn.setText("🤖 " + tr(L, "vlm_run_btn"))
        self.src_card._title_label.setText(tr(L, "extracted_text") + "  ·  " + tr(L, "preview_image")); self.prev_card._title_label.setText(tr(L, "preview_title"))
        for lab in self.legend_labels: lab.setText(tr(L, lab.property("i18n_key")))
        self.mode_lbl.setText(tr(L, "mode_label"))
        self.mode_combo.setItemText(0, tr(L, "mode_auto")); self.mode_combo.setItemText(1, tr(L, "mode_rules")); self.mode_combo.setItemText(2, tr(L, "mode_local_vlm"))
        self.vlm_dl_btn.setText("⬇ " + tr(L, "vlm_download_generic") + f" ({vlm_local.model_spec(self.settings.get('vlm_model_size', '3b'))['approx_gb']}GB)")
        _st = vlm_local.model_status(model_key=self.settings.get("vlm_model_size", "3b"))
        self.vlm_note.setText(tr(L, "vlm_image_note") + "  " + (tr(L, "vlm_ready_msg") if _st["complete"] else tr(L, "vlm_slow_note")))
        self.copy_btn.setText("✓ " + tr(L, "confirm_copy")); self.xlsx_btn.setText(tr(L, "export_excel")); self.csv_btn.setText(tr(L, "export_csv")); self.json_btn.setText(tr(L, "copy_json"))
        self.auto_card._title_label.setText(tr(L, "auto_title")); self.auto_chk.setText(tr(L, "auto_enable"))
        self.auto_hint_lbl.setText(tr(L, "auto_mode_hint")); self.auto_note2_lbl.setText(tr(L, "auto_note")); self.review_title_lbl.setText(tr(L, "review_queue"))
        if self.settings.get("watch_enabled") and self.settings.get("watch_folder"):
            self.watch_status_lbl.setText("👁 " + tr(L, "auto_watch_on") + self.settings.get("watch_folder", ""))
        else:
            self.watch_status_lbl.setText("")
        self.status_lbl.setText("● " + tr(L, "status_ready"))
        app = QApplication.instance()
        if app: app.setLayoutDirection(Qt.RightToLeft if self.lang == "ar" else Qt.LeftToRight)
    def on_lang_change(self):
        self.lang = self.lang_combo.currentData(); self.settings["language"] = self.lang; save_settings(self.settings); self.retranslate()
        if self.rows: self.populate_table()
    def on_profile_change(self, idx):
        if 0 <= idx < len(self.profiles): self.current_profile = self.profiles[idx]
    def on_mode_change(self):
        self.settings["extract_mode"] = self.mode_combo.currentData(); save_settings(self.settings)
    def select_file(self):
        p, _ = QFileDialog.getOpenFileName(self, tr(self.lang, "select_files"), "", "PDF/Image/Text (*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.txt *.csv)")
        if p: self.load_file(p)
    def load_files(self, files):
        """v2: multiple dropped files — with 完全自動 ON they are processed
        sequentially unattended; otherwise the first file opens normally."""
        files = [f for f in files if f]
        if not files: return
        if len(files) > 1 and self.auto_chk.isChecked():
            self._start_auto(files); return
        if len(files) == 1 and self.auto_chk.isChecked():
            self._start_auto(files); return
        self.load_file(files[0])
    def _auto_cfg(self):
        d = get_app_dir()
        cfg = {"output_path": self.settings.get("auto_output_path") or os.path.join(d, "auto_output.xlsx"),
                "done_folder": self.settings.get("auto_done_folder") or os.path.join(d, "done"),
                "review_folder": self.settings.get("auto_review_folder") or os.path.join(d, "review"),
                "threshold": int(self.settings.get("auto_threshold", 90) or 90),
                "settings": self.settings}
        # v2 I: unattended destinations may be an integration file (method 3)
        # or an ENABLED integration DB (method 4). RPA/web-form stay manual.
        dest = self.settings.get("auto_dest", "file")
        if dest in ("intfile", "intdb"):
            try:
                for ip in integrations_mod.load_integrations():
                    if dest == "intfile" and ip.method == "file":
                        cfg["integration_file"] = ip.config
                        cfg["integration_file_dir"] = os.path.join(d, "integration_exports")
                        break
                    if dest == "intdb" and ip.method == "db" and ip.config.get("db_write_enabled"):
                        cfg["integration_db"] = ip.config
                        break
            except Exception:
                pass
        return cfg
    def _start_auto(self, paths):
        if self._auto_worker and self._auto_worker.isRunning(): return
        self.auto_result_lbl.setText(tr(self.lang, "auto_processing") + f" ({len(paths)})")
        self.status_lbl.setText(tr(self.lang, "auto_processing"))
        self._auto_worker = AutoWorker(list(paths), self.current_profile, self._auto_cfg())
        self._auto_worker.file_done.connect(self._on_auto_file_done)
        self._auto_worker.all_done.connect(self._on_auto_all_done)
        self._auto_worker.start()
    def _on_auto_file_done(self, r):
        if r.get("decision") == "review" and r.get("moved_to"):
            item = QListWidgetItem("⚠ " + r.get("source", "") + "  →  " + r["moved_to"])
            item.setData(Qt.UserRole, r["moved_to"]); self.review_list.addItem(item)
    def _on_auto_all_done(self, results):
        acc = sum(1 for r in results if r.get("decision") == "accepted")
        rev = sum(1 for r in results if r.get("decision") != "accepted")
        msg = f"{tr(self.lang, 'auto_result')}: {tr(self.lang, 'auto_accepted')} {acc} / {tr(self.lang, 'auto_needs_review')} {rev}"
        self.auto_result_lbl.setText(msg); self.status_lbl.setText("✓ " + msg)
    def _open_review_item(self, item):
        p = item.data(Qt.UserRole)
        if p and os.path.isfile(p):
            self.auto_chk.setChecked(False)
            self.load_file(p)
    def _watch_tick(self):
        if not self.settings.get("watch_enabled"): return
        folder = self.settings.get("watch_folder") or ""
        if not folder or (self._auto_worker and self._auto_worker.isRunning()): return
        files = automation_mod.scan_watch_folder(folder)
        fresh = []
        for f in files:
            try:
                sig = (f, os.path.getmtime(f), os.path.getsize(f))
            except OSError:
                continue
            if sig not in self._watch_seen:
                self._watch_seen.add(sig); fresh.append(f)
        if fresh: self._start_auto(fresh)
    def load_file(self, path):
        self._vendor_checked = False
        self.current_file = path
        ext = os.path.splitext(path)[1].lower(); text = ""
        if ext == ".pdf":
            text, _ocr = extract_text_from_pdf(path)
            self.source_kind = "pdf_digital" if text.strip() else "pdf_scan"
            try:
                import fitz; doc = fitz.open(path); pix = doc[0].get_pixmap(dpi=110); tmp = os.path.join(tempfile.gettempdir(), "contextstruct_preview.png"); pix.save(tmp); self._show_image(tmp); doc.close()
            except Exception: pass
            if not text.strip() and not ocr_available(): self.status_lbl.setText("⚠ " + ocr_missing_message(self.lang))
        elif ext in (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"):
            self.source_kind = "image"
            self.current_image_path = path; self._show_image(path)
            o = extract_text_from_image_file(path)
            if o is None: self.status_lbl.setText("⚠ " + ocr_missing_message(self.lang)); text = ""
            else: text = o
        elif ext in (".txt", ".csv"):
            self.source_kind = "text"
            with open(path, encoding="utf-8", errors="ignore") as f: text = f.read()
        else:
            with open(path, encoding="utf-8", errors="ignore") as f: text = f.read()
        self.text_edit.setPlainText(text)
        if text.strip(): self.run_extract()
    def _show_image(self, path):
        pix = QPixmap(path)
        if not pix.isNull(): self.img_lbl.setPixmap(pix.scaled(500, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.current_image_path = path
    def capture_screen(self):
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            tmp = os.path.join(tempfile.gettempdir(), "contextstruct_capture.png"); img.save(tmp); self.source_kind = "image"; self.current_file = None; self._show_image(tmp)
            o = ocr_image(img, self.settings.get("ocr_lang", "jpn+eng"))
            if o: self.text_edit.setPlainText(o); self.run_extract()
            elif o is None: self.status_lbl.setText("⚠ " + ocr_missing_message(self.lang))
        except Exception as e:
            self.status_lbl.setText(tr(self.lang, "capture_failed") + f": {e}")
            QMessageBox.information(self, tr(self.lang, "capture"), tr(self.lang, "capture_failed"))
    def run_extract(self):
        mode = self.settings.get("extract_mode", "auto")
        if mode == "local_vlm":
            self.run_local_vlm_gui(); return
        if mode == "auto" and self.source_kind in ("image", "pdf_scan"):
            # images & scanned PDFs: image understanding (VLM) is the primary path
            self.run_local_vlm_gui(); return
        if mode == "auto" and self.source_kind == "pdf_digital" and not self.text_edit.toPlainText().strip():
            self.run_local_vlm_gui(); return
        self.run_rules()
    def _master_entries(self):
        p = self.settings.get("master_csv") or ""
        return ensemble.load_master(p) if p else None
    def _few_shot(self):
        if not self.settings.get("learning_enabled", True): return None
        try:
            return learning.recent_corrections(self.current_profile.name, 5) or None
        except Exception:
            return None
    def run_rules(self):
        text = self.text_edit.toPlainText()
        if not text.strip():
            if not ocr_available(): self.status_lbl.setText("⚠ " + ocr_missing_message(self.lang))
            return
        # v2 ensemble: text rules + (for images) OCR voters over the original and
        # preprocessed variants, merged with agreement scoring, then master
        # matching + arithmetic verification. Falls back to plain rules on error.
        img = self.current_image_path if self.source_kind == "image" else None
        try:
            self.rows, self._last_info = ensemble.run_pipeline(
                self.current_profile, text=text, image_path=img, settings=self.settings,
                use_vlm=False, master=self._master_entries(), verify=False,
                text_engine_name="pdf_text" if self.source_kind == "pdf_digital" else "text_rules")
        except Exception:
            self.rows = extract_document(text, self.current_profile); self._last_info = None
        self.populate_table()
        note = "✓ " + tr(self.lang, "status_done")
        if self._last_info and self._last_info.get("engines"):
            note += "  |  " + tr(self.lang, "engines_used") + ", ".join(self._last_info["engines"])
        self.status_lbl.setText(note)
        self._vendor_hook()
    def _vendor_hook(self):
        """Per-vendor memory: if a remembered vendor appears under a different
        profile, switch to it once per file (text/rule path only)."""
        if self._vendor_checked: return
        self._vendor_checked = True
        try:
            vendor = learning.detect_vendor(self.rows, self.current_profile)
            if not vendor: return
            remembered = learning.profile_for_vendor(vendor)
            if remembered and remembered != self.current_profile.name:
                names = [p.name for p in self.profiles]
                if remembered in names:
                    self.profile_combo.setCurrentIndex(names.index(remembered))
                    self.current_profile = self.profiles[names.index(remembered)]
                    self._vendor_checked = True
                    if self.text_edit.toPlainText().strip():
                        self.rows, self._last_info = ensemble.run_pipeline(
                            self.current_profile, text=self.text_edit.toPlainText(), settings=self.settings,
                            use_vlm=False, master=self._master_entries(), verify=False)
                        self.populate_table()
        except Exception:
            pass
    def _vlm_image_path(self):
        # VLM receives the IMAGE itself: image file / capture as-is, PDF rendered at high resolution
        if self.current_file and os.path.splitext(self.current_file)[1].lower() == ".pdf":
            dpi = max(200, int(self.settings.get("ocr_dpi", 200) or 200))
            return vlm_local.prepare_vlm_image(self.current_file, dpi=dpi)
        if self.current_image_path and os.path.isfile(self.current_image_path):
            return self.current_image_path
        if self.current_file:
            return vlm_local.prepare_vlm_image(self.current_file)
        return None
    def run_local_vlm_gui(self):
        img = self._vlm_image_path()
        if not img:
            self.status_lbl.setText("⚠ " + tr(self.lang, "vlm_image_note")); self.run_rules(); return
        st = vlm_local.model_status(model_key=self.settings.get("vlm_model_size", "3b"))
        if not st["complete"]:
            ans = QMessageBox.question(self, tr(self.lang, "mode_local_vlm"), tr(self.lang, "vlm_missing_msg"))
            if ans == QMessageBox.Yes:
                self._pending_vlm = True; self.start_model_download()
            return
        self.status_lbl.setText(tr(self.lang, "vlm_processing"))
        self.extract_btn.setEnabled(False)
        self._vlm_worker = VlmWorker(img, self.current_profile, settings=self.settings,
                                     few_shot=self._few_shot(), master=self._master_entries())
        self._vlm_worker.done_rows.connect(self._on_vlm_done); self._vlm_worker.failed.connect(self._on_vlm_failed)
        self._vlm_worker.start()
    def _on_vlm_done(self, payload):
        self.extract_btn.setEnabled(True)
        if isinstance(payload, tuple):
            self.rows, self._last_info = payload
        else:
            self.rows, self._last_info = payload, None
        self.populate_table()
        note = "✓ " + tr(self.lang, "status_done")
        if self._last_info and self._last_info.get("engines"):
            note += "  |  " + tr(self.lang, "engines_used") + ", ".join(self._last_info["engines"]) + "  |  " + tr(self.lang, "verify_note")
        self.status_lbl.setText(note)
        self._vendor_checked = True  # VLM path: do not re-run rules after vendor switch
    def _on_vlm_failed(self, msg):
        self.extract_btn.setEnabled(True); self.status_lbl.setText("⚠ VLM: " + msg); QMessageBox.warning(self, tr(self.lang, "error"), msg)
    def start_model_download(self):
        if self._dl_worker and self._dl_worker.isRunning(): return
        self._progress = QProgressDialog(tr(self.lang, "vlm_downloading"), None, 0, 100, self); self._progress.setStyleSheet(STYLE)
        self._progress.setWindowTitle(tr(self.lang, "vlm_download_btn")); self._progress.setCancelButton(None); self._progress.show()
        self._dl_worker = DownloadWorker(self.settings.get("vlm_model_size", "3b"))
        self._dl_worker.progress.connect(lambda f, pct: (self._progress.setLabelText(f"{f}  {pct}%"), self._progress.setValue(pct)))
        self._dl_worker.finished_ok.connect(self._on_download_done); self._dl_worker.start()
    def _on_download_done(self, ok, msg):
        if hasattr(self, "_progress"): self._progress.close()
        if ok:
            self.status_lbl.setText("✓ " + tr(self.lang, "vlm_ready_msg")); self.retranslate()
            if self._pending_vlm:
                self._pending_vlm = False; self.run_local_vlm_gui()
        else:
            self._pending_vlm = False; QMessageBox.warning(self, tr(self.lang, "error"), msg)
    def run_vlm(self):
        # Default: built-in LOCAL VLM (image understanding, offline, no API key).
        # External API is used only when the user explicitly enabled it in Settings.
        if not (self.settings.get("vlm_use_api") and self.settings.get("vlm_endpoint") and self.settings.get("vlm_model")):
            self.run_local_vlm_gui(); return
        if not self.current_image_path:
            QMessageBox.information(self, tr(self.lang, "vlm_run_btn"), ocr_missing_message(self.lang)); return
        try:
            result = call_vlm(self.current_image_path, self.current_profile, self.settings)
            if result:
                row = {}
                for f in self.current_profile.fields:
                    v = str(result.get(f.target_column, "")); v = format_value(v, f.field_type) if f.field_type != "text" else v
                    row[f.target_column] = FieldResult(v, 85 if v else 0, "VLM", "")
                self.rows = [row]; self.populate_table()
        except Exception as e:
            QMessageBox.warning(self, tr(self.lang, "error"), str(e))
    def populate_table(self):
        self.table.blockSignals(True)
        cols = [f.target_column for f in self.current_profile.fields]
        self.table.setColumnCount(len(cols)); self.table.setHorizontalHeaderLabels(cols); self.table.setRowCount(len(self.rows))
        colors = {"green": QColor("#c9edc0"), "yellow": QColor("#ffefa6"), "red": QColor("#ffc9c9")}
        for ri, row in enumerate(self.rows):
            self.table.setRowHeight(ri, 34)
            for ci, col in enumerate(cols):
                fr = row.get(col, FieldResult())
                item = QTableWidgetItem(fr.value); item.setBackground(colors[confidence_category(fr.confidence)])
                tip = f"{fr.confidence} / {fr.reason} / {fr.snippet}" if fr.snippet else f"{fr.confidence} / {fr.reason}"
                item.setToolTip(tip); self.table.setItem(ri, ci, item)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents); self.table.horizontalHeader().setStretchLastSection(True)
        self.table.blockSignals(False)
        # v2 learning: snapshot the extracted values so confirmed edits can be recorded
        self._orig_snapshot = {}
        for ri, row in enumerate(self.rows):
            for f in self.current_profile.fields:
                fr = row.get(f.target_column)
                self._orig_snapshot[(ri, f.target_column)] = fr.value if fr else ""
    def _record_corrections(self):
        """On confirm (copy/export): store confirmed edits, learn keyword
        aliases, remember the vendor->profile pairing. Returns learned words."""
        learned = []
        if not self.rows: return learned
        try:
            vendor = learning.detect_vendor(self.rows, self.current_profile)
            if vendor: learning.remember_vendor_profile(vendor, self.current_profile.name)
        except Exception: pass
        if not self.settings.get("learning_enabled", True): return learned
        src = self.text_edit.toPlainText()
        try:
            for (ri, col), orig in list(self._orig_snapshot.items()):
                if ri >= len(self.rows): continue
                fr = self.rows[ri].get(col)
                if fr is None: continue
                cur = fr.value or ""
                if cur != (orig or ""):
                    learning.save_correction(self.current_profile.name, col, orig or "", cur, source_snippet=fr.snippet or "")
                    tok = learning.learn_alias(self.current_profile, col, cur, source_text=src)
                    if tok: learned.append(tok)
            if learned:
                save_profile(self.current_profile)
        except Exception: pass
        self._orig_snapshot = {(ri, f.target_column): (self.rows[ri][f.target_column].value if self.rows[ri].get(f.target_column) else "")
                               for ri in range(len(self.rows)) for f in self.current_profile.fields}
        return learned
    def _learned_suffix(self, learned):
        return ("  |  " + tr(self.lang, "learned_msg") + ", ".join(learned)) if learned else ""
    def on_cell_changed(self, item):
        if not self.rows: return
        cols = [f.target_column for f in self.current_profile.fields]; col = cols[item.column()]
        fr = self.rows[item.row()][col]; fr.value = item.text(); fr.confidence = 100; fr.reason = tr(self.lang, "manual_label")
        item.setBackground(QColor("#c9edc0")); item.setToolTip(fr.reason)
    def copy_tsv(self):
        if not self.rows: self.run_extract()
        learned = self._record_corrections()
        QApplication.clipboard().setText(rows_to_tsv(self.rows, self.current_profile, include_header=False)); self.status_lbl.setText("✓ " + tr(self.lang, "copied_msg") + self._learned_suffix(learned))
    def copy_json(self):
        if not self.rows: self.run_extract()
        learned = self._record_corrections()
        QApplication.clipboard().setText(json.dumps(rows_to_dicts(self.rows, self.current_profile), ensure_ascii=False, indent=2)); self.status_lbl.setText("✓ " + tr(self.lang, "copied_msg") + self._learned_suffix(learned))
    def export_xlsx(self):
        if not self.rows: self.run_extract()
        p, _ = QFileDialog.getSaveFileName(self, tr(self.lang, "export_excel"), "contextstruct.xlsx", "Excel (*.xlsx)")
        if not p: return
        learned = self._record_corrections()
        from openpyxl import Workbook; wb = Workbook(); ws = wb.active; ws.append([f.target_column for f in self.current_profile.fields])
        for d in rows_to_dicts(self.rows, self.current_profile): ws.append([d[f.target_column] for f in self.current_profile.fields])
        wb.save(p); self.status_lbl.setText("✓ " + tr(self.lang, "exported_msg") + f": {p}" + self._learned_suffix(learned))
    def export_csv_file(self):
        if not self.rows: self.run_extract()
        p, _ = QFileDialog.getSaveFileName(self, tr(self.lang, "export_csv"), "contextstruct.csv", "CSV (*.csv)")
        if not p: return
        learned = self._record_corrections()
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=[x.target_column for x in self.current_profile.fields]); w.writeheader(); w.writerows(rows_to_dicts(self.rows, self.current_profile))
        self.status_lbl.setText("✓ " + tr(self.lang, "exported_msg") + f": {p}" + self._learned_suffix(learned))
    def edit_profile(self):
        dlg = ProfileEditor(self.current_profile, self.lang, self)
        if dlg.exec():
            prof = dlg.get_profile(); save_profile(prof)
            idx = self.profile_combo.currentIndex(); self.profiles[idx] = prof; self.current_profile = prof
            self.profile_combo.setItemText(idx, prof.name)
            if self.text_edit.toPlainText().strip(): self.run_extract()
    def open_integrations(self):
        dlg = IntegrationsDialog(self, self)
        dlg.exec()
    def start_gpu_download(self, flavor):
        if getattr(self, "_gpu_worker", None) and self._gpu_worker.isRunning(): return
        self._gprogress = QProgressDialog(tr(self.lang, "vlm_downloading"), None, 0, 100, self); self._gprogress.setStyleSheet(STYLE)
        self._gprogress.setWindowTitle(tr(self.lang, "gpu_title")); self._gprogress.setCancelButton(None); self._gprogress.show()
        self._gpu_worker = GpuDownloadWorker(flavor)
        self._gpu_worker.progress.connect(lambda f, pct: (self._gprogress.setLabelText(f"{f}  {pct}%"), self._gprogress.setValue(pct)))
        self._gpu_worker.finished_ok.connect(lambda ok, msg: (self._gprogress.close(), self.status_lbl.setText("✓ GPU: " + vlm_local.effective_mode()) if ok else QMessageBox.warning(self, tr(self.lang, "error"), msg)))
        self._gpu_worker.start()
    def open_settings(self):
        dlg = SettingsDialog(self.settings, self.lang, self)
        if dlg.exec():
            self.settings = dlg.get_settings(); save_settings(self.settings)
            if getattr(dlg, "gpu_flavor", None):
                self.start_gpu_download(dlg.gpu_flavor)
            if getattr(dlg, "download_requested", False):
                self.start_model_download()
            self.lang = self.settings["language"]
            self.lang_combo.setCurrentIndex(LANG_ORDER.index(self.lang)); self.retranslate()
            try: self.shortcut.setKey(QKeySequence(self.settings.get("hotkey", "Ctrl+Shift+S")))
            except Exception: pass
    def load_demo(self):
        self.source_kind = "text"; self.settings["extract_mode"] = "rules"
        sample = "納品書\n納品書番号: DN-2026-001\n納品日: 2026年11月12日\n取引先: 株式会社サンプル\n商品名: りんごジュース 1L\n数量: 24\n単価: 800円\n卸値: 800円\n売価: 1200円\n合計: 19200円\n"
        # add a low-confidence / missing feel: remove one field value? Keep full demo but 合計 mismatch is fine.
        self.text_edit.setPlainText(sample); self.run_extract()

def _fixed_style():
    """Return STYLE unchanged when a preferred UI font exists on this system.

    On systems with none of the preferred families (e.g. Wine), Qt's font
    fallback can crash while polishing styled widgets; in that case swap the
    font stack for an actually installed family. Real Windows installs have
    Yu Gothic UI / Segoe UI, so their rendering is identical to before.
    """
    try:
        from PySide6.QtGui import QFontDatabase
        available = set(QFontDatabase.families())
    except Exception:
        return STYLE
    # Real Windows always has Yu Gothic UI (JP) or Segoe UI: keep STYLE as-is.
    # Other environments (e.g. Wine) have neither, and Qt font fallback over
    # the missing names can crash there, so fall back to an installed font.
    if "Yu Gothic UI" in available or "Segoe UI" in available:
        return STYLE
    fallback = "Tahoma" if "Tahoma" in available else (sorted(available)[0] if available else "sans-serif")
    return STYLE.replace("'Yu Gothic UI','Meiryo UI','Noto Sans CJK JP','Segoe UI',sans-serif",
                         "'%s'" % fallback)

def main():
    _args = list(sys.argv)
    if _UNDER_WINE:
        # Wine-only: Qt's native (DirectWrite) font engine intermittently
        # dereferences bogus UTF-16 pointers in Wine 9.0 while doing font
        # fallback for emoji glyphs (page faults inside QtPrivate::qustrlen).
        # The FreeType engine avoids that path entirely. No effect on real
        # Windows, where this branch never runs.
        _args += ["-platform", "windows:fontengine=freetype"]
    app = QApplication(_args)
    try:
        import os as _os, sys as _sys
        from PySide6.QtGui import QIcon as _QIcon
        _ib = getattr(_sys, "_MEIPASS", None) or _os.path.dirname(_os.path.abspath(__file__))
        _ip = _os.path.join(_ib, "assets", "icon.png")
        if _os.path.exists(_ip):
            app.setWindowIcon(_QIcon(_ip))
    except Exception:
        pass
    globals()["STYLE"] = _fixed_style()
    app.setStyleSheet(STYLE)
    w = MainWindow(); w.show()
    if "--sample-demo" in sys.argv: w.load_demo()
    sys.exit(app.exec())
if __name__ == "__main__": main()
