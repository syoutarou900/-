# -*- coding: utf-8 -*-
"""超特化型ドロップランチャー - DropLauncher
小さな常駐フローティングパネル。ファイルをゾーンへドラッグ＆ドロップで自動処理。
デザイン刷新版：明るいカード型UI（機能は従来版と同一）。
"""
import subprocess, sys, threading, traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
from i18n_data import t as _t, LANG_ORDER, LANG_NAMES
try:
    import rc_assets  # noqa: F401  矢印画像などのQtリソース
except Exception:
    pass

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QGuiApplication, QFont
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                               QLabel, QPushButton, QCheckBox, QComboBox, QTextEdit, QDialog,
                               QFormLayout, QLineEdit, QSpinBox, QFileDialog, QMessageBox, QFrame)
from PySide6.QtWidgets import QGraphicsDropShadowEffect
from PySide6.QtGui import QColor

APP_STYLE = """
QWidget { background:#e8eff9; color:#16324f; font-size:13.5px; }
QLabel { background:transparent; }
QFrame#header { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
    stop:0 #1d46a8, stop:0.5 #2f7fd0, stop:1 #0fb0cb); border-radius:18px;
    border-bottom:4px solid #173a7d; }
QLabel#appTitle { background:transparent; color:#ffffff; font-size:21px; font-weight:bold; }
QLabel#appSub { background:transparent; color:#e2efff; font-size:12.5px; }
QLabel#appBadge { background:rgba(255,255,255,0.22); color:#ffffff; font-size:11px;
    border-radius:8px; padding:3px 8px; }
QFrame#toolbar { background:#ffffff; border:1px solid #d9e5f3; border-radius:12px; }
QPushButton { background:#2f7fd0; color:white; border:none; border-radius:8px; padding:7px 14px; font-weight:bold; }
QPushButton:hover { background:#1f66ad; }
QPushButton#secondary { background:#ffffff; color:#2456c8; border:1.5px solid #9dbede; }
QPushButton#secondary:hover { background:#eaf3ff; }
QPushButton#bigPrimary { background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
    stop:0 #2456c8, stop:1 #12a5c4); color:white; border:none; border-radius:10px;
    padding:11px; font-size:14px; font-weight:bold; }
QPushButton#bigPrimary:hover { background:#2456c8; }
QCheckBox { background:transparent; font-weight:bold; }
QComboBox { background:#ffffff; border:1px solid #b9d2ee; border-radius:6px; padding:4px 6px; }
QLabel#sectionLabel { background:transparent; color:#486581; font-size:12px; font-weight:bold; }
QTextEdit { background:#ffffff; border:1px solid #cfdff2; border-radius:10px; padding:6px;
    font-family:Consolas, Menlo, monospace; font-size:12px; }
QLineEdit, QSpinBox { background:#ffffff; border:1px solid #b9d2ee; border-radius:6px; padding:5px; }
QDialog { background:#f2f6fc; }
QComboBox#langCombo { background:rgba(255,255,255,0.30); color:#ffffff; border:1.5px solid rgba(255,255,255,0.75); border-radius:13px; padding:4px 10px; font-weight:bold; }
QComboBox#langCombo::drop-down { border:none; background:transparent; width:22px; }
QComboBox#langCombo::down-arrow { image: url(:/arrows/down_white.png); width:11px; height:11px; }
QLabel#langLabel { background:transparent; color:#e2efff; font-size:12px; font-weight:bold; }

/* ===== 立体スクロールバー（縦） ===== */
QScrollBar:vertical { border:none; background:#cfdff2; width:18px; border-radius:9px; margin:21px 1px 21px 1px; }
QScrollBar::handle:vertical { min-height:40px; border-radius:8px; border:1px solid #17497f;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6db3f2, stop:0.45 #2f7fd0, stop:1 #1d5fa8); }
QScrollBar::handle:vertical:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8cc4f7, stop:0.45 #4393dd, stop:1 #2569b5); }
QScrollBar::handle:vertical:pressed { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f7fd0, stop:1 #17497f); }
QScrollBar::add-line:vertical { height:20px; subcontrol-position:bottom; subcontrol-origin:margin; margin:0 1px 1px 1px;
    border:1px solid #17497f; border-radius:6px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6db3f2, stop:1 #2456c8); }
QScrollBar::sub-line:vertical { height:20px; subcontrol-position:top; subcontrol-origin:margin; margin:1px 1px 0 1px;
    border:1px solid #17497f; border-radius:6px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6db3f2, stop:1 #2456c8); }
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
    border:1px solid #17497f; border-radius:6px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6db3f2, stop:1 #2456c8); }
QScrollBar::sub-line:horizontal { width:20px; subcontrol-position:left; subcontrol-origin:margin; margin:1px 0 1px 1px;
    border:1px solid #17497f; border-radius:6px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6db3f2, stop:1 #2456c8); }
QScrollBar::left-arrow:horizontal { image: url(:/arrows/left_white.png); width:10px; height:10px; }
QScrollBar::right-arrow:horizontal { image: url(:/arrows/right_white.png); width:10px; height:10px; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background:transparent; }
/* ===== 選択リスト（コンボボックス）の立体矢印ボタン ===== */
QComboBox { padding-right:30px; }
QComboBox::drop-down { subcontrol-origin:padding; subcontrol-position:center right; width:28px;
    border-left:1px solid #17497f; border-top-right-radius:6px; border-bottom-right-radius:6px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6db3f2, stop:1 #2456c8); }
QComboBox::drop-down:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8cc4f7, stop:1 #2f66d0); }
QComboBox::down-arrow { image: url(:/arrows/down_white.png); width:12px; height:12px; }
QComboBox QAbstractItemView { background:#ffffff; border:1px solid #9dbede; selection-background-color:#2f7fd0; selection-color:#ffffff; }
/* ===== 数値入力（スピンボックス）の立体矢印ボタン ===== */
QSpinBox { padding-right:24px; }
QSpinBox::up-button { subcontrol-origin:border; subcontrol-position:top right; width:21px;
    border-left:1px solid #17497f; border-bottom:1px solid #17497f; border-top-right-radius:6px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6db3f2, stop:1 #2f7fd0); }
QSpinBox::down-button { subcontrol-origin:border; subcontrol-position:bottom right; width:21px;
    border-left:1px solid #17497f; border-bottom-right-radius:6px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2f7fd0, stop:1 #2456c8); }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8cc4f7, stop:1 #4393dd); }
QSpinBox::up-arrow { image: url(:/arrows/up_white.png); width:8px; height:8px; }
QSpinBox::down-arrow { image: url(:/arrows/down_white.png); width:8px; height:8px; }
"""

def _lighten(hexcolor, factor=182):
    c = QColor(hexcolor)
    return c.lighter(factor).name()

class Bridge(QObject):
    log = Signal(str)
    done = Signal(str)

class DropZone(QWidget):
    """立体カード型ドロップ枠。大きなアイコンバッジ＋太い下縁＋影で奥行きを出す。
    ドロップだけでなく、クリックでファイル選択ダイアログからも処理できる。"""
    def __init__(self, icon, title, subtitle, accent, handler, parent=None, hint="", lang="ja"):
        super().__init__(parent)
        self.setObjectName("zone")
        self.accent = accent
        self.title = title
        self.handler = handler
        self.lang = lang
        self.setAcceptDrops(True)
        self.setMinimumHeight(144)
        self.setMaximumHeight(170)
        self.setCursor(Qt.PointingHandCursor)
        self._active = False
        self.setStyleSheet("QWidget#zone { background:transparent; }")
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(20); self._shadow.setOffset(0, 6)
        self._shadow.setColor(QColor(31, 78, 140, 58))
        self.setGraphicsEffect(self._shadow)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 8); lay.setSpacing(3)
        badge = QLabel(icon); badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(52, 52)
        badge.setStyleSheet(
            f"font-size:19px; border-radius:26px;"
            f"background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            f" stop:0 {_lighten(accent, 165)}, stop:1 {accent});"
            f" border:2px solid rgba(255,255,255,0.85);")
        brow = QHBoxLayout(); brow.addStretch(); brow.addWidget(badge); brow.addStretch()
        lay.addLayout(brow)
        lay.addSpacing(5)
        ti = QLabel(title); ti.setAlignment(Qt.AlignCenter); self._title_lbl = ti
        ti.setStyleSheet("font-size:15.5px; font-weight:bold; color:#12293f; background:transparent;")
        lay.addWidget(ti)
        self._sub_lbls = []
        for line in subtitle.split("\n"):
            su = QLabel(line); su.setAlignment(Qt.AlignCenter)
            su.setStyleSheet("font-size:12px; color:#52687e; background:transparent;")
            lay.addWidget(su); self._sub_lbls.append(su)
        self._hint_lbl = QLabel(hint)
        self._hint_lbl.setAlignment(Qt.AlignCenter)
        self._hint_lbl.setStyleSheet(f"font-size:10.5px; font-weight:bold; color:{accent}; background:transparent;")
        lay.addWidget(self._hint_lbl)
    def set_texts(self, title, subtitle, hint, lang):
        self.title = title; self.lang = lang
        self._title_lbl.setText(title)
        lines = subtitle.split("\n")
        for i, lb in enumerate(self._sub_lbls):
            lb.setText(lines[i] if i < len(lines) else "")
        self._hint_lbl.setText(hint)
    def _set_active(self, on):
        self._active = on
        self._shadow.setBlurRadius(30 if on else 20)
        self._shadow.setOffset(0, 9 if on else 6)
        self.update()
    def paintEvent(self, e):
        # 立体カードを直接描く：白→淡色グラデーション、太い下縁、上面の光沢ライン
        from PySide6.QtGui import QPainter, QLinearGradient, QPen, QBrush
        from PySide6.QtCore import QRectF
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        accent = QColor(self.accent)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -5.5)
        grad = QLinearGradient(r.topLeft(), r.bottomLeft())
        if self._active:
            grad.setColorAt(0, accent.lighter(185)); grad.setColorAt(1, accent.lighter(160))
        else:
            grad.setColorAt(0, QColor("#ffffff")); grad.setColorAt(0.55, accent.lighter(214)); grad.setColorAt(1, accent.lighter(196))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(accent, 2.5 if self._active else 1.6))
        p.drawRoundedRect(r, 16, 16)
        # 太い下縁（カードの厚み）
        p.save()
        from PySide6.QtGui import QPainterPath
        clip = QPainterPath(); clip.addRoundedRect(r, 16, 16); p.setClipPath(clip)
        p.setPen(Qt.NoPen); p.setBrush(accent)
        p.drawRect(QRectF(r.left(), r.bottom() - 3.5, r.width(), 5))
        # 上面ハイライト
        p.setBrush(QColor(255, 255, 255, 110))
        p.drawRect(QRectF(r.left() + 8, r.top() + 1.5, r.width() - 16, 2))
        p.restore()
        super().paintEvent(e)
    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            files, _ = QFileDialog.getOpenFileNames(self, _t(self.lang, "select_files_title", title=self.title))
            if files:
                self.handler(files)
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            self._set_active(True); e.acceptProposedAction()
    def dragLeaveEvent(self, e):
        self._set_active(False)
    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
    def dropEvent(self, e):
        self._set_active(False)
        files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if files:
            self.handler(files)
        e.acceptProposedAction()

class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.lang = settings.get("language", "ja")
        self.setWindowTitle(_t(self.lang, "settings_win_title"))
        self.setStyleSheet(APP_STYLE)
        self.resize(560, 430)
        self.settings = dict(settings)
        outer = QVBoxLayout(self)
        head = QLabel(_t(self.lang, "settings_head")); head.setStyleSheet("font-size:16px; font-weight:bold; background:transparent;")
        outer.addWidget(head)
        formw = QWidget(); form = QFormLayout(formw)
        self.output = QLineEdit(settings["output_base"])
        row = QHBoxLayout(); row.addWidget(self.output)
        btn = QPushButton(_t(self.lang, "browse_btn")); btn.clicked.connect(self._browse); row.addWidget(btn)
        form.addRow(_t(self.lang, "set_output"), row)
        self.project = QLineEdit(settings["project"]); form.addRow(_t(self.lang, "set_project"), self.project)
        self.sort_mode = QComboBox()
        for _val, _key in (("move", "disp_move"), ("copy", "disp_copy")):
            self.sort_mode.addItem(_t(self.lang, _key), _val)
        self.sort_mode.setCurrentIndex(max(self.sort_mode.findData(settings["sort_mode"]), 0))
        form.addRow(_t(self.lang, "set_sort_mode"), self.sort_mode)
        self.sort_sub = QComboBox()
        for _val, _key in (("ext_date", "disp_sub_ext_date"), ("ext", "disp_sub_ext"), ("date", "disp_sub_date"), ("none", "disp_sub_none")):
            self.sort_sub.addItem(_t(self.lang, _key), _val)
        self.sort_sub.setCurrentIndex(max(self.sort_sub.findData(settings["sort_subfolder"]), 0))
        form.addRow(_t(self.lang, "set_sort_sub"), self.sort_sub)
        self.img_w = QSpinBox(); self.img_w.setRange(100, 8000); self.img_w.setValue(int(settings["image_max_width"]))
        form.addRow(_t(self.lang, "set_img_width"), self.img_w)
        self.img_kb = QSpinBox(); self.img_kb.setRange(10, 20000); self.img_kb.setValue(int(settings["image_target_kb"]))
        form.addRow(_t(self.lang, "set_img_kb"), self.img_kb)
        self.img_fmt = QComboBox(); self.img_fmt.addItems(["JPG", "WebP", "PNG"])
        self.img_fmt.setCurrentText(settings["image_format"]); form.addRow(_t(self.lang, "set_img_fmt"), self.img_fmt)
        self.soffice = QLineEdit(settings["soffice_path"]); form.addRow(_t(self.lang, "set_soffice"), self.soffice)
        outer.addWidget(formw)
        ok = QPushButton(_t(self.lang, "save_btn")); ok.setObjectName("bigPrimary"); ok.clicked.connect(self.accept)
        outer.addWidget(ok)
    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, _t(self.lang, "browse_title"))
        if d:
            self.output.setText(d)
    def result_settings(self):
        s = self.settings
        s.update({"output_base": self.output.text().strip() or core.default_output_base(),
                  "project": self.project.text().strip() or "作業",
                  "sort_mode": self.sort_mode.currentData(),
                  "sort_subfolder": self.sort_sub.currentData(),
                  "image_max_width": self.img_w.value(),
                  "image_target_kb": self.img_kb.value(),
                  "image_format": self.img_fmt.currentText(),
                  "soffice_path": self.soffice.text().strip()})
        return s

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = core.load_settings()
        _lang = self.settings.get("language")
        self.lang = _lang if _lang in LANG_ORDER else "ja"
        self.bridge = Bridge()
        self.bridge.log.connect(self._append_log)
        self.bridge.done.connect(self._append_log)
        self.setWindowTitle(_t(self.lang, "app_title"))
        self.setStyleSheet(APP_STYLE)
        self.resize(680, 960)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14); root.setSpacing(10)

        # ---- header ----
        header = QFrame(); header.setObjectName("header")
        hshadow = QGraphicsDropShadowEffect(header)
        hshadow.setBlurRadius(22); hshadow.setOffset(0, 6); hshadow.setColor(QColor(23, 58, 125, 90))
        header.setGraphicsEffect(hshadow)
        hl = QHBoxLayout(header); hl.setContentsMargins(20, 16, 20, 16)
        icon = QLabel("📂"); icon.setStyleSheet("font-size:40px; background:transparent;")
        hl.addWidget(icon)
        texts = QVBoxLayout()
        self.title_lbl = QLabel(_t(self.lang, "app_title")); self.title_lbl.setObjectName("appTitle"); texts.addWidget(self.title_lbl)
        self.sub_lbl = QLabel(_t(self.lang, "app_subtitle"))
        self.sub_lbl.setObjectName("appSub"); self.sub_lbl.setWordWrap(True); texts.addWidget(self.sub_lbl)
        hl.addLayout(texts); hl.addStretch()
        badge = QLabel("macOS 11+" if sys.platform == "darwin" else "Windows 10 / 11"); badge.setObjectName("appBadge")
        rightcol = QVBoxLayout(); rightcol.setSpacing(6)
        rightcol.addWidget(badge, 0, Qt.AlignRight)
        langrow = QHBoxLayout(); langrow.setSpacing(6)
        self.lang_label = QLabel(_t(self.lang, "lang_label")); self.lang_label.setObjectName("langLabel")
        langrow.addWidget(self.lang_label)
        self.lang_combo = QComboBox(); self.lang_combo.setObjectName("langCombo")
        for _code in LANG_ORDER:
            self.lang_combo.addItem(LANG_NAMES[_code], _code)
        self.lang_combo.setCurrentIndex(LANG_ORDER.index(self.lang))
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        langrow.addWidget(self.lang_combo)
        rightcol.addLayout(langrow)
        hl.addLayout(rightcol)
        root.addWidget(header)

        # ---- toolbar ----
        toolbar = QFrame(); toolbar.setObjectName("toolbar")
        top = QHBoxLayout(toolbar); top.setContentsMargins(12, 8, 12, 8)
        self.top_check = QCheckBox(_t(self.lang, "always_on_top")); self.top_check.setChecked(bool(self.settings.get("always_on_top", True)))
        self.top_check.stateChanged.connect(self._apply_top)
        top.addWidget(self.top_check)
        top.addStretch()
        self.preset_lbl = QLabel(_t(self.lang, "video_preset_label")); top.addWidget(self.preset_lbl)
        self.video_preset = QComboBox()
        for _val, _disp in (("mp4", "MP4"), ("compress", _t(self.lang, "disp_preset_compress")), ("mp3", _t(self.lang, "disp_preset_mp3")), ("gif", "GIF")):
            self.video_preset.addItem(_disp, _val)
        self.video_preset.setCurrentIndex(max(self.video_preset.findData(self.settings.get("video_preset", "mp4")), 0))
        self.video_preset.currentIndexChanged.connect(self._on_preset_changed)
        top.addWidget(self.video_preset)
        self.set_btn = QPushButton(_t(self.lang, "settings_btn")); self.set_btn.clicked.connect(self._open_settings); top.addWidget(self.set_btn)
        self.undo_btn = QPushButton(_t(self.lang, "undo_btn")); self.undo_btn.setObjectName("secondary")
        self.undo_btn.clicked.connect(lambda: self._run("undo", [])); top.addWidget(self.undo_btn)
        root.addWidget(toolbar)

        # ---- zones ----
        self.zones_lbl = QLabel(_t(self.lang, "zones_label"))
        self.zones_lbl.setObjectName("sectionLabel"); root.addWidget(self.zones_lbl)
        grid = QGridLayout(); grid.setSpacing(10)
        zone_defs = [
            ("📝", "transcribe", "#7c5cff"), ("🗂", "sort", "#2f7fd0"), ("📊", "report", "#e8930c"),
            ("🖼", "image", "#e05299"), ("📄", "pdf_merge", "#e05252"), ("✂", "pdf_split", "#f07316"),
            ("🎬", "video", "#8b5cf6"), ("📗", "excel", "#1f9d63"), ("🗜", "zip", "#64748b"),
            ("📦", "unzip", "#0e9fd8"),
        ]
        self.zone_widgets = []
        for i, (icon, key, accent) in enumerate(zone_defs):
            z = DropZone(icon, _t(self.lang, f"zone_{key}_title"), _t(self.lang, f"zone_{key}_sub"), accent,
                         (lambda k: (lambda files: self._run(k, files)))(key),
                         hint=_t(self.lang, "zone_hint"), lang=self.lang)
            self.zone_widgets.append((key, z))
            grid.addWidget(z, i // 2, i % 2)
        root.addLayout(grid)

        # ---- log ----
        self.log_lbl = QLabel(_t(self.lang, "log_label")); self.log_lbl.setObjectName("sectionLabel"); root.addWidget(self.log_lbl)
        self.log_view = QTextEdit(); self.log_view.setReadOnly(True); self.log_view.setMinimumHeight(110)
        root.addWidget(self.log_view, 1)
        self.out_btn = QPushButton(_t(self.lang, "open_output_btn")); self.out_btn.setObjectName("bigPrimary")
        self.out_btn.clicked.connect(self._open_output)
        root.addWidget(self.out_btn)
        self._apply_top()
        self._append_log(_t(self.lang, "startup_output", path=self.settings["output_base"]))
        ff = core.find_ffmpeg(self.settings)
        self._append_log(_t(self.lang, "log_ffmpeg", value=(ff if ff else _t(self.lang, "value_not_found"))))
        so = core.find_soffice(self.settings)
        self._append_log(_t(self.lang, "log_libre", value=(so if so else _t(self.lang, "libre_not_found"))))

    # ---------- helpers ----------
    def _apply_top(self):
        on = self.top_check.isChecked()
        self.settings["always_on_top"] = on
        flags = self.windowFlags()
        if on:
            self.setWindowFlags(flags | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(flags & ~Qt.WindowStaysOnTopHint)
        self.show()
    def _append_log(self, msg):
        self.log_view.append(str(msg))
    def _open_output(self):
        p = Path(self.settings["output_base"]); p.mkdir(parents=True, exist_ok=True)
        import os
        if sys.platform == "darwin":
            try:
                subprocess.run(["open", str(p)], check=False)
                return
            except Exception:
                pass
        try:
            os.startfile(str(p))  # Windows
        except Exception:
            QGuiApplication.clipboard().setText(str(p))
            self._append_log(_t(self.lang, "copied_output_path", path=p))
    def _open_settings(self):
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec():
            self.settings = dlg.result_settings()
            core.save_settings(self.settings)
            self._append_log(_t(self.lang, "settings_saved"))

    # ---------- processing (also used by tests via process_files) ----------
    def process_files(self, key, files, log=None):
        log = log or (lambda m: None)
        s = self.settings
        files = [str(f) for f in files]
        if key == "undo":
            return core.undo_last(s, log)
        if key == "transcribe":
            outs = []
            for f in files: outs += core.transcribe_file(f, s, log)
            return outs
        if key == "sort":
            return core.sort_rename_files(files, s, log)
        if key == "report":
            res = []
            for f in files:
                r = core.aggregate_report(f, s, log)
                res.append(r)
                if QGuiApplication.instance():
                    QGuiApplication.clipboard().setText(r["report_text"])
                    log(_t(self.lang, "report_copied"))
            return res
        if key == "image":
            return [core.convert_image(f, s, log) for f in files
                    if Path(f).suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff")]
        if key == "pdf_merge":
            pdfs = [f for f in files if f.lower().endswith(".pdf")]
            return core.pdf_merge(pdfs, s, log) if pdfs else []
        if key == "pdf_split":
            outs = []
            for f in files:
                if f.lower().endswith(".pdf"):
                    outs += core.pdf_split(f, s, log); outs.append(core.pdf_extract_text(f, s, log))
            return outs
        if key == "video":
            return [core.convert_video(f, s, log, preset=s.get("video_preset", "mp4")) for f in files]
        if key == "excel":
            outs = []
            for f in files: outs += core.excel_convert(f, s, log)
            return outs
        if key == "zip":
            zips = [f for f in files if f.lower().endswith(".zip")]
            normal = [f for f in files if not f.lower().endswith(".zip")]
            outs = []
            if normal: outs.append(core.archive_zip(normal, s, log))
            return outs
        if key == "unzip":
            return [core.archive_extract(f, s, log) for f in files if f.lower().endswith(".zip")]
        raise ValueError(f"unknown zone: {key}")

    def _on_preset_changed(self, *a):
        v = self.video_preset.currentData()
        if v:
            self.settings.update({"video_preset": v})

    def _on_language_changed(self, *a):
        code = self.lang_combo.currentData()
        if not code or code == self.lang:
            return
        self.lang = code
        self.settings["language"] = code
        core.save_settings(self.settings)
        self.apply_language()

    def apply_language(self):
        lang = self.lang
        self.setWindowTitle(_t(lang, "app_title"))
        self.title_lbl.setText(_t(lang, "app_title"))
        self.sub_lbl.setText(_t(lang, "app_subtitle"))
        self.lang_label.setText(_t(lang, "lang_label"))
        self.top_check.setText(_t(lang, "always_on_top"))
        self.preset_lbl.setText(_t(lang, "video_preset_label"))
        cur = self.video_preset.currentData()
        self.video_preset.blockSignals(True)
        self.video_preset.clear()
        for _val, _disp in (("mp4", "MP4"), ("compress", _t(lang, "disp_preset_compress")), ("mp3", _t(lang, "disp_preset_mp3")), ("gif", "GIF")):
            self.video_preset.addItem(_disp, _val)
        self.video_preset.setCurrentIndex(max(self.video_preset.findData(cur), 0))
        self.video_preset.blockSignals(False)
        self.set_btn.setText(_t(lang, "settings_btn"))
        self.undo_btn.setText(_t(lang, "undo_btn"))
        self.zones_lbl.setText(_t(lang, "zones_label"))
        for key, z in self.zone_widgets:
            z.set_texts(_t(lang, f"zone_{key}_title"), _t(lang, f"zone_{key}_sub"), _t(lang, "zone_hint"), lang)
        self.log_lbl.setText(_t(lang, "log_label"))
        self.out_btn.setText(_t(lang, "open_output_btn"))
        direction = Qt.RightToLeft if lang == "ar" else Qt.LeftToRight
        app = QApplication.instance()
        if app is not None:
            app.setLayoutDirection(direction)
        self.setLayoutDirection(direction)

    def _run(self, key, files):
        lang = self.lang
        log = lambda m: self.bridge.log.emit(str(m))
        def work():
            try:
                log(_t(lang, "run_start", zone=key, count=len(files)))
                self.process_files(key, files, log=log)
                log(_t(lang, "run_done", zone=key))
            except Exception as e:
                core.log_error(f"{key}: {e}\n{traceback.format_exc()}")
                log(_t(lang, "run_error", error=e))
        threading.Thread(target=work, daemon=True).start()

def main():
    app = QApplication(sys.argv)
    try:
        import os as _os, sys as _sys
        from PySide6.QtGui import QIcon as _QIcon
        _ib = getattr(_sys, "_MEIPASS", None) or _os.path.dirname(_os.path.abspath(__file__))
        _ip = _os.path.join(_ib, "assets", "icon.png")
        if _os.path.exists(_ip):
            app.setWindowIcon(_QIcon(_ip))
    except Exception:
        pass
    if sys.platform == "darwin":
        app.setFont(QFont("Hiragino Sans", 10))
    else:
        app.setFont(QFont("Yu Gothic UI", 10))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
