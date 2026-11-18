# -*- coding: utf-8 -*-
"""StepOnce - main GUI.

Record a task once, as usual, and get a draft manual in 13 languages.

Language switching follows the same pattern as the user's other apps: a
language label + combo box at the right end of the top header, instant
retranslation of the whole window without a restart, the choice is saved
and restored on the next launch, and Arabic switches the whole layout to
right-to-left. The recording panel follows the current language too.
"""

import json
import os
import sys

from PIL import Image, ImageDraw

import core
import exporter
import icons
import recorder as recorder_mod
import theme
from appinfo import APP_ID, display_name
from i18n import LANG_NAMES, LANG_ORDER, RTL_LANGS, tr

from PySide6.QtCore import Qt, QObject, QRect, QSize, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QRubberBand,
    QSplitter, QVBoxLayout, QWidget,
)


def _repolish(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)


# ----------------------------------------------------------------------
# Settings (language + optional DeepL key), stored per-OS like the
# user's other apps.
# ----------------------------------------------------------------------

def data_dir():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"),
                            "Library", "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share")
    path = os.path.join(base, APP_ID)
    os.makedirs(path, exist_ok=True)
    return path


def load_settings():
    try:
        with open(os.path.join(data_dir(), "settings.json"),
                  encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(settings):
    try:
        with open(os.path.join(data_dir(), "settings.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(settings, fh, ensure_ascii=False, indent=1)
    except Exception:
        pass


def pil_to_pixmap(img):
    if img.mode != "RGB":
        img = img.convert("RGB")
    data = img.tobytes("raw", "RGB")
    qimg = QImage(data, img.width, img.height, img.width * 3,
                  QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())


# ----------------------------------------------------------------------
# Image view with mosaic-drag support
# ----------------------------------------------------------------------

class ImageView(QLabel):
    """Shows the step image scaled to fit; in mosaic mode, dragging
    emits rect_dragged with image-relative coordinates."""

    rect_dragged = Signal(float, float, float, float)

    def __init__(self):
        super().__init__()
        self.setObjectName("preview")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(320, 170)
        self._pixmap = None
        self._drag_start = None
        self._drag_origin = None
        self._rubber = None
        self._mosaic_mode = False

    @property
    def mosaic_mode(self):
        return self._mosaic_mode

    @mosaic_mode.setter
    def mosaic_mode(self, on):
        self._mosaic_mode = bool(on)
        self.setCursor(Qt.CursorShape.CrossCursor if on
                       else Qt.CursorShape.ArrowCursor)

    def set_image(self, pixmap):
        self._pixmap = pixmap
        self._update_shown()

    def _shown_rect(self):
        if not self._pixmap:
            return None
        lw, lh = self.width(), self.height()
        pw, ph = self._pixmap.width(), self._pixmap.height()
        scale = min(lw / pw, lh / ph)
        w, h = int(pw * scale), int(ph * scale)
        return ((lw - w) // 2, (lh - h) // 2, w, h)

    def _update_shown(self):
        if not self._pixmap:
            super().setPixmap(QPixmap())
            return
        rect = self._shown_rect()
        if rect:
            scaled = self._pixmap.scaled(
                rect[2], rect[3], Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            super().setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_shown()

    def _to_relative(self, pos):
        rect = self._shown_rect()
        if not rect or not self._pixmap:
            return None
        x = (pos.x() - rect[0]) / rect[2]
        y = (pos.y() - rect[1]) / rect[3]
        if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
            return (x, y)
        return (min(1.0, max(0.0, x)), min(1.0, max(0.0, y)))

    def mousePressEvent(self, event):
        if self.mosaic_mode and event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = self._to_relative(event.pos())
            self._drag_origin = event.pos()
            if self._rubber is None:
                self._rubber = QRubberBand(
                    QRubberBand.Shape.Rectangle, self)
            self._rubber.setGeometry(QRect(self._drag_origin, QSize()))
            self._rubber.show()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.mosaic_mode and self._drag_origin is not None \
                and self._rubber is not None:
            self._rubber.setGeometry(
                QRect(self._drag_origin, event.pos()).normalized())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._rubber is not None:
            self._rubber.hide()
        if self.mosaic_mode and self._drag_start is not None:
            end = self._to_relative(event.pos())
            if end is not None:
                x = min(self._drag_start[0], end[0])
                y = min(self._drag_start[1], end[1])
                w = abs(end[0] - self._drag_start[0])
                h = abs(end[1] - self._drag_start[1])
                if w > 0.005 and h > 0.005:
                    self.rect_dragged.emit(x, y, w, h)
            self._drag_start = None
            self._drag_origin = None
        super().mouseReleaseEvent(event)


# ----------------------------------------------------------------------
# Recording panel (always on top, small)
# ----------------------------------------------------------------------

class RecordPanel(QWidget):
    pause_toggled = Signal(bool)
    finish_clicked = Signal()
    capture_clicked = Signal()

    def __init__(self, lang, manual_mode):
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.lang = lang
        self.manual_mode = manual_mode
        self.paused = False
        self._dot_on = True
        self.setStyleSheet(theme.stylesheet())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.lbl_dot = QLabel()
        self.lbl_dot.setObjectName("recDot")
        self.lbl_dot.setFixedSize(10, 10)
        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("recStatus")
        self.lbl_count = QLabel()
        self.lbl_count.setObjectName("recCount")
        self.btn_pause = QPushButton()
        self.btn_capture = QPushButton()
        self.btn_finish = QPushButton()
        self.btn_finish.setProperty("role", "primary")
        card = QFrame()
        card.setObjectName("panelCard")
        card.setFrameShape(QFrame.Shape.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.addWidget(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        srow = QHBoxLayout()
        srow.setSpacing(8)
        srow.addWidget(self.lbl_dot)
        srow.addWidget(self.lbl_status)
        srow.addStretch(1)
        layout.addLayout(srow)
        layout.addWidget(self.lbl_count)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.btn_pause)
        row.addWidget(self.btn_capture)
        row.addWidget(self.btn_finish)
        layout.addLayout(row)
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_finish.clicked.connect(self.finish_clicked.emit)
        self.btn_capture.clicked.connect(self.capture_clicked.emit)
        self._dot_timer = QTimer(self)
        self._dot_timer.setInterval(560)
        self._dot_timer.timeout.connect(self._blink_dot)
        self.retranslate(lang)
        self.resize(380, 150)

    def _toggle_pause(self):
        self.paused = not self.paused
        self.pause_toggled.emit(self.paused)
        self._refresh_status()

    def set_count(self, count):
        self.lbl_count.setText(tr(self.lang, "rec_count", count=count))

    def _blink_dot(self):
        self._dot_on = not self._dot_on
        self.lbl_dot.setProperty(
            "state", "" if self._dot_on else "off")
        _repolish(self.lbl_dot)

    def closeEvent(self, event):
        self._dot_timer.stop()
        super().closeEvent(event)

    def _refresh_status(self):
        if self.paused:
            self.lbl_status.setText(tr(self.lang, "rec_paused"))
            self._dot_timer.stop()
            self.lbl_dot.setProperty("state", "paused")
        else:
            self.lbl_status.setText(tr(self.lang, "rec_recording"))
            self._dot_on = True
            self.lbl_dot.setProperty("state", "")
            self._dot_timer.start()
        _repolish(self.lbl_dot)
        self.btn_pause.setText(
            tr(self.lang, "btn_resume" if self.paused else "btn_pause"))

    def retranslate(self, lang):
        self.lang = lang
        self.setWindowTitle(tr(lang, "rec_title"))
        self.btn_capture.setIcon(icons.icon("camera", theme.INK))
        self.btn_capture.setIconSize(QSize(16, 16))
        self.btn_capture.setText(tr(lang, "btn_capture_now"))
        self.btn_finish.setText(tr(lang, "btn_finish"))
        self._refresh_status()


# ----------------------------------------------------------------------
# Dialogs
# ----------------------------------------------------------------------

class SettingsDialog(QDialog):
    def __init__(self, parent, lang, deepl_key):
        super().__init__(parent)
        self.lang = lang
        self.setWindowTitle(tr(lang, "set_title"))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr(lang, "set_deepl_key")))
        self.edit_key = QLineEdit(deepl_key)
        self.edit_key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.edit_key)
        note = QLabel(tr(lang, "set_deepl_note"))
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        btn_ok = QPushButton(tr(lang, "btn_ok"))
        btn_ok.setProperty("role", "primary")
        btn_cancel = QPushButton(tr(lang, "btn_cancel"))
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        row.addWidget(btn_ok)
        row.addWidget(btn_cancel)
        layout.addLayout(row)
        self.resize(440, 200)


class ExportDialog(QDialog):
    def __init__(self, parent, lang, has_deepl_key):
        super().__init__(parent)
        self.lang = lang
        self.setWindowTitle(tr(lang, "exp_title"))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr(lang, "exp_out_dir")))
        row = QHBoxLayout()
        self.edit_dir = QLineEdit()
        btn_browse = QPushButton(tr(lang, "btn_browse"))
        btn_browse.clicked.connect(self._browse)
        row.addWidget(self.edit_dir)
        row.addWidget(btn_browse)
        layout.addLayout(row)
        layout.addWidget(QLabel(tr(lang, "exp_languages")))
        self.lang_checks = {}
        grid = QWidget()
        grid_layout = QVBoxLayout(grid)
        for code in LANG_ORDER:
            chk = QCheckBox(LANG_NAMES[code])
            chk.setChecked(True)
            self.lang_checks[code] = chk
            grid_layout.addWidget(chk)
        layout.addWidget(grid)
        layout.addWidget(QLabel(tr(lang, "exp_formats")))
        self.chk_pdf = QCheckBox(tr(lang, "exp_pdf"))
        self.chk_pdf.setChecked(True)
        self.chk_docx = QCheckBox(tr(lang, "exp_word"))
        self.chk_docx.setChecked(True)
        layout.addWidget(self.chk_pdf)
        layout.addWidget(self.chk_docx)
        self.chk_marker = QCheckBox(tr(lang, "exp_marker"))
        self.chk_marker.setChecked(True)
        layout.addWidget(self.chk_marker)
        self.chk_deepl = QCheckBox(tr(lang, "exp_deepl"))
        self.chk_deepl.setEnabled(has_deepl_key)
        layout.addWidget(self.chk_deepl)
        if not has_deepl_key:
            layout.addWidget(QLabel(tr(lang, "exp_deepl_no_key")))
        row2 = QHBoxLayout()
        self.btn_export = QPushButton(tr(lang, "btn_do_export"))
        self.btn_export.setProperty("role", "primary")
        btn_close = QPushButton(tr(lang, "btn_close"))
        self.btn_export.clicked.connect(self.accept)
        btn_close.clicked.connect(self.reject)
        row2.addWidget(self.btn_export)
        row2.addWidget(btn_close)
        layout.addLayout(row2)
        self.resize(420, 560)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(
            self, tr(self.lang, "dlg_out_dir"))
        if path:
            self.edit_dir.setText(path)

    def options(self):
        langs = [c for c, chk in self.lang_checks.items() if chk.isChecked()]
        formats = []
        if self.chk_pdf.isChecked():
            formats.append("pdf")
        if self.chk_docx.isChecked():
            formats.append("docx")
        return {
            "out_dir": self.edit_dir.text().strip(),
            "langs": langs,
            "formats": formats,
            "show_marker": self.chk_marker.isChecked(),
            "use_deepl": self.chk_deepl.isChecked(),
        }


# ----------------------------------------------------------------------
# Step card (one "page" in the booklet-style step list)
# ----------------------------------------------------------------------

class StepCard(QFrame):
    """A step shown as a page of a booklet: a large page number, the
    thumbnail and the first lines of its text."""

    def __init__(self):
        super().__init__()
        self.setObjectName("stepCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_num = QLabel()
        self.lbl_num.setObjectName("stepNum")
        self.lbl_num.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.lbl_num.setFixedWidth(44)
        self.lbl_thumb = QLabel()
        self.lbl_thumb.setObjectName("thumb")
        self.lbl_thumb.setFixedSize(122, 76)
        self.lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_text = QLabel()
        self.lbl_text.setObjectName("stepText")
        self.lbl_text.setWordWrap(True)
        self.lbl_text.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.lbl_meta = QLabel()
        self.lbl_meta.setObjectName("stepMeta")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 9, 12, 9)
        layout.setSpacing(10)
        layout.addWidget(self.lbl_num)
        layout.addWidget(self.lbl_thumb)
        texts = QVBoxLayout()
        texts.setSpacing(3)
        texts.addWidget(self.lbl_text)
        texts.addWidget(self.lbl_meta)
        texts.addStretch(1)
        layout.addLayout(texts, 1)

    def set_content(self, number, pixmap, text, meta):
        self.lbl_num.setText(str(number))
        if pixmap is not None:
            self.lbl_thumb.setPixmap(pixmap)
        else:
            self.lbl_thumb.setPixmap(QPixmap())
        self.lbl_text.setText(text)
        self.lbl_meta.setText(meta)
        self.lbl_meta.setVisible(bool(meta))

    def set_text(self, text):
        self.lbl_text.setText(text)

    def set_selected(self, selected):
        self.setProperty("selected", "true" if selected else "false")
        _repolish(self)


# ----------------------------------------------------------------------
# Main window
# ----------------------------------------------------------------------

class RecorderBridge(QObject):
    step_captured = Signal(object, object)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setStyleSheet(theme.stylesheet())
        self.settings = load_settings()
        self.lang = self.settings.get("lang", "ja")
        if self.lang not in LANG_ORDER:
            self.lang = "ja"
        self.project = core.Project()
        self.current_step = None
        self._loaded_text = None

        self.bridge = RecorderBridge()
        self.bridge.step_captured.connect(self._on_step_captured)
        self.recorder = recorder_mod.create_recorder(
            lambda step, img: self.bridge.step_captured.emit(step, img))
        self.capturer = recorder_mod.ManualCapturer(
            lambda step, img: self.bridge.step_captured.emit(step, img))
        self.panel = None

        self._build_ui()
        self._apply_button_icons()
        self.retranslate()
        self._refresh_steps()
        self.resize(1220, 800)

    # -- button icons: drawn with QPainter (icons.py), never font glyphs,
    # so rendering cannot fall back to a colour emoji font.
    def _apply_button_icons(self):
        ink = theme.INK
        for btn, kind, color, size in (
                (self.btn_capture, "camera", ink, 18),
                (self.btn_export, "book", "#FFFFFF", 18),
                (self.btn_mosaic_mode, "brush", ink, 18),
                (self.btn_up, "up", ink, 14),
                (self.btn_down, "down", ink, 14)):
            btn.setIcon(icons.icon(kind, color))
            btn.setIconSize(QSize(size, size))
        self._sync_record_icon()

    def _sync_record_icon(self):
        running = bool(getattr(self.recorder, "running", False))
        self.btn_record.setIcon(
            icons.icon("stop" if running else "record", "#FFFFFF"))
        self.btn_record.setIconSize(QSize(15, 15))

    # -- UI construction --------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header: thin white band with one orange rule under it; the
        # language label + combo stay at the right end, as before.
        header = QFrame()
        header.setObjectName("appHeader")
        header.setFrameShape(QFrame.Shape.NoFrame)
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(18, 12, 18, 12)
        hlayout.setSpacing(12)
        self.lbl_logo = QLabel("1")
        self.lbl_logo.setObjectName("logoMark")
        self.lbl_logo.setFixedSize(34, 34)
        self.lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hlayout.addWidget(self.lbl_logo)
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        self.lbl_title = QLabel()
        self.lbl_title.setObjectName("appTitle")
        self.lbl_subtitle = QLabel()
        self.lbl_subtitle.setObjectName("appSubtitle")
        title_box.addWidget(self.lbl_title)
        title_box.addWidget(self.lbl_subtitle)
        hlayout.addLayout(title_box)
        hlayout.addStretch(1)
        self.lbl_lang = QLabel()
        self.lbl_lang.setObjectName("langLabel")
        hlayout.addWidget(self.lbl_lang)
        self.combo_lang = QComboBox()
        for code in LANG_ORDER:
            self.combo_lang.addItem(LANG_NAMES[code], code)
        self.combo_lang.setCurrentIndex(LANG_ORDER.index(self.lang))
        self.combo_lang.currentIndexChanged.connect(self._on_lang_changed)
        hlayout.addWidget(self.combo_lang)
        root.addWidget(header)

        body = QWidget()
        root.addWidget(body, 1)
        root = QVBoxLayout(body)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # Project title row
        trow = QHBoxLayout()
        self.lbl_proj_title = QLabel()
        self.lbl_proj_title.setObjectName("sectionTitle")
        trow.addWidget(self.lbl_proj_title)
        self.edit_proj_title = QLineEdit()
        self.edit_proj_title.textChanged.connect(
            lambda t: setattr(self.project, "title", t))
        trow.addWidget(self.edit_proj_title)
        root.addLayout(trow)

        # Toolbar (record / export are the primary orange actions)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_new = QPushButton()
        self.btn_open = QPushButton()
        self.btn_save = QPushButton()
        self.btn_zip_export = QPushButton()
        self.btn_zip_import = QPushButton()
        self.btn_record = QPushButton()
        self.btn_record.setProperty("role", "primary")
        self.btn_record.setProperty("recording", "false")
        self.btn_capture = QPushButton()
        self.btn_export = QPushButton()
        self.btn_export.setProperty("role", "primary")
        self.btn_settings = QPushButton()
        for btn in (self.btn_new, self.btn_open, self.btn_save,
                    self.btn_zip_export, self.btn_zip_import,
                    self.btn_record, self.btn_capture, self.btn_export,
                    self.btn_settings):
            bar.addWidget(btn)
        bar.addStretch(1)
        root.addLayout(bar)
        self.btn_new.clicked.connect(self.new_project)
        self.btn_open.clicked.connect(self.open_project)
        self.btn_save.clicked.connect(self.save_project)
        self.btn_zip_export.clicked.connect(self.export_zip)
        self.btn_zip_import.clicked.connect(self.import_zip)
        self.btn_record.clicked.connect(self.toggle_recording)
        self.btn_capture.clicked.connect(lambda: self.manual_capture("main"))
        self.btn_export.clicked.connect(self.export_manuals)
        self.btn_settings.clicked.connect(self.open_settings)

        self.lbl_mode_note = QLabel()
        self.lbl_mode_note.setObjectName("modeNote")
        self.lbl_mode_note.setWordWrap(True)
        root.addWidget(self.lbl_mode_note)

        # Main split: booklet page cards (left) | preview + editor (right)
        split = QSplitter()
        split.setChildrenCollapsible(False)
        left = QWidget()
        llayout = QVBoxLayout(left)
        llayout.setContentsMargins(0, 0, 0, 0)
        llayout.setSpacing(8)
        self.lbl_steps_hdr = QLabel()
        self.lbl_steps_hdr.setObjectName("sectionTitle")
        llayout.addWidget(self.lbl_steps_hdr)
        self.list_steps = QListWidget()
        self.list_steps.setMinimumWidth(340)
        self.list_steps.setVerticalScrollMode(
            QListWidget.ScrollMode.ScrollPerPixel)
        self.list_steps.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_steps.currentRowChanged.connect(self._on_row_changed)
        llayout.addWidget(self.list_steps, 10)
        self.lbl_no_steps = QLabel()
        self.lbl_no_steps.setObjectName("emptyState")
        self.lbl_no_steps.setWordWrap(True)
        llayout.addWidget(self.lbl_no_steps)
        llayout.addStretch(1)
        srow = QHBoxLayout()
        srow.setSpacing(6)
        self.btn_up = QPushButton()
        self.btn_down = QPushButton()
        self.btn_delete = QPushButton()
        self.btn_duplicate = QPushButton()
        self.btn_add_image = QPushButton()
        for btn in (self.btn_up, self.btn_down, self.btn_delete,
                    self.btn_duplicate, self.btn_add_image):
            srow.addWidget(btn)
        llayout.addLayout(srow)
        self.btn_up.clicked.connect(lambda: self.move_step(-1))
        self.btn_down.clicked.connect(lambda: self.move_step(1))
        self.btn_delete.clicked.connect(self.delete_step)
        self.btn_duplicate.clicked.connect(self.duplicate_step)
        self.btn_add_image.clicked.connect(self.add_step_from_image)
        split.addWidget(left)

        right = QWidget()
        rlayout = QVBoxLayout(right)
        rlayout.setContentsMargins(0, 0, 0, 0)
        rlayout.setSpacing(8)
        self.image_view = ImageView()
        self.image_view.rect_dragged.connect(self._on_mosaic_dragged)
        rlayout.addWidget(self.image_view, 1)
        self.lbl_pick = QLabel()
        self.lbl_pick.setObjectName("mutedNote")
        self.lbl_pick.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rlayout.addWidget(self.lbl_pick)

        self.candidate_bar = QFrame()
        self.candidate_bar.setObjectName("candidateBar")
        self.candidate_bar.setFrameShape(QFrame.Shape.NoFrame)
        crow = QHBoxLayout(self.candidate_bar)
        crow.setContentsMargins(12, 8, 12, 8)
        crow.setSpacing(8)
        self.lbl_candidate = QLabel()
        self.lbl_candidate.setObjectName("candidateText")
        self.btn_candidate_apply = QPushButton()
        self.btn_candidate_dismiss = QPushButton()
        crow.addWidget(self.lbl_candidate)
        crow.addWidget(self.btn_candidate_apply)
        crow.addWidget(self.btn_candidate_dismiss)
        crow.addStretch(1)
        self.candidate_bar.setVisible(False)
        rlayout.addWidget(self.candidate_bar)
        self.btn_candidate_apply.clicked.connect(self.apply_candidates)
        self.btn_candidate_dismiss.clicked.connect(self.dismiss_candidates)

        mrow = QHBoxLayout()
        mrow.setSpacing(8)
        self.btn_mosaic_mode = QPushButton()
        self.btn_mosaic_mode.setCheckable(True)
        self.btn_mosaic_clear = QPushButton()
        mrow.addWidget(self.btn_mosaic_mode)
        mrow.addWidget(self.btn_mosaic_clear)
        mrow.addStretch(1)
        rlayout.addLayout(mrow)
        self.btn_mosaic_mode.toggled.connect(
            lambda on: setattr(self.image_view, "mosaic_mode", on))
        self.btn_mosaic_clear.clicked.connect(self.clear_mosaics)

        self.lbl_text = QLabel()
        self.lbl_text.setObjectName("sectionTitle")
        rlayout.addWidget(self.lbl_text)
        self.edit_text = QPlainTextEdit()
        self.edit_text.setMaximumHeight(76)
        rlayout.addWidget(self.edit_text)
        self.lbl_draft_note = QLabel()
        self.lbl_draft_note.setWordWrap(True)
        self.lbl_draft_note.setObjectName("draftNote")
        rlayout.addWidget(self.lbl_draft_note)
        self.lbl_memo = QLabel()
        self.lbl_memo.setObjectName("sectionTitle")
        rlayout.addWidget(self.lbl_memo)
        self.edit_memo = QPlainTextEdit()
        self.edit_memo.setMaximumHeight(40)
        self.edit_memo.textChanged.connect(self._on_memo_changed)
        rlayout.addWidget(self.edit_memo)
        self.lbl_target = QLabel()
        self.lbl_target.setObjectName("mutedNote")
        self.lbl_window = QLabel()
        self.lbl_window.setObjectName("mutedNote")
        rlayout.addWidget(self.lbl_target)
        rlayout.addWidget(self.lbl_window)
        split.addWidget(right)
        split.setSizes([410, 740])
        root.addWidget(split, 1)

        self.lbl_keyboard_note = QLabel()
        self.lbl_keyboard_note.setWordWrap(True)
        self.lbl_keyboard_note.setObjectName("draftNote")
        root.addWidget(self.lbl_keyboard_note)

        self.shortcut_capture = QShortcut(QKeySequence("F8"), self)
        self.shortcut_capture.setContext(
            Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut_capture.activated.connect(
            lambda: self.manual_capture("hotkey"))

    # -- language ---------------------------------------------------------
    def _on_lang_changed(self, index):
        code = self.combo_lang.itemData(index)
        if not code or code == self.lang:
            return
        self.lang = code
        self.settings["lang"] = code
        save_settings(self.settings)
        self.retranslate()
        self._refresh_steps()
        if self.current_step is not None:
            self._load_detail(self.current_step)

    def retranslate(self):
        lang = self.lang
        direction = (Qt.LayoutDirection.RightToLeft if lang in RTL_LANGS
                     else Qt.LayoutDirection.LeftToRight)
        QApplication.instance().setLayoutDirection(direction)
        self.setLayoutDirection(direction)
        name = display_name(lang)
        self.setWindowTitle(name)
        self.lbl_title.setText(name)
        self.lbl_subtitle.setText(tr(lang, "app_subtitle"))
        self.lbl_lang.setText(tr(lang, "lang_label"))
        self.lbl_proj_title.setText(tr(lang, "lbl_project_title"))
        self.btn_new.setText(tr(lang, "btn_new"))
        self.btn_open.setText(tr(lang, "btn_open"))
        self.btn_save.setText(tr(lang, "btn_save"))
        self.btn_zip_export.setText(tr(lang, "btn_zip_export"))
        self.btn_zip_import.setText(tr(lang, "btn_zip_import"))
        self.btn_record.setText(tr(lang, "btn_record_stop")
                                if self.recorder.running
                                else tr(lang, "btn_record_start"))
        self._sync_record_icon()
        self.btn_capture.setText(tr(lang, "btn_capture"))
        self.btn_export.setText(tr(lang, "btn_export"))
        self.btn_settings.setText(tr(lang, "btn_settings"))
        self.lbl_mode_note.setText(
            tr(lang, "lbl_mac_mode") if self.recorder.mode == "manual"
            else "")
        self.lbl_steps_hdr.setText(tr(lang, "hdr_steps"))
        self.lbl_no_steps.setText(tr(lang, "lbl_no_steps"))
        self.btn_up.setText(tr(lang, "btn_up"))
        self.btn_down.setText(tr(lang, "btn_down"))
        self.btn_delete.setText(tr(lang, "btn_delete"))
        self.btn_duplicate.setText(tr(lang, "btn_duplicate"))
        self.btn_add_image.setText(tr(lang, "btn_add_image"))
        self.lbl_pick.setText(tr(lang, "lbl_pick_step"))
        self.lbl_candidate.setText(tr(lang, "lbl_mosaic_candidate"))
        self.btn_candidate_apply.setText(tr(lang, "btn_candidate_apply"))
        self.btn_candidate_dismiss.setText(
            tr(lang, "btn_candidate_dismiss"))
        self.btn_mosaic_mode.setText(tr(lang, "btn_mosaic_mode"))
        self.btn_mosaic_clear.setText(tr(lang, "btn_mosaic_clear"))
        self.lbl_text.setText(tr(lang, "lbl_text"))
        self.lbl_draft_note.setText(tr(lang, "txt_draft_note"))
        self.lbl_memo.setText(tr(lang, "lbl_memo"))
        self.lbl_keyboard_note.setText(tr(lang, "lbl_keyboard_note"))
        if self.panel is not None:
            self.panel.setLayoutDirection(direction)
            self.panel.retranslate(lang)

    # -- step list ----------------------------------------------------------
    def _step_label(self, idx, step):
        text = step.effective_text(self.lang).replace("\n", " ")
        return "%d. %s" % (idx + 1, text[:36])

    def _refresh_steps(self):
        self.list_steps.blockSignals(True)
        self.list_steps.clear()
        for idx, step in enumerate(self.project.steps):
            item = QListWidgetItem(self._step_label(idx, step))
            item.setSizeHint(QSize(0, 100))
            card = StepCard()
            text = step.effective_text(self.lang).replace("\n", " ")
            meta = step.window_title or step.target_name
            card.set_content(idx + 1, self._thumbnail(step), text, meta)
            self.list_steps.addItem(item)
            self.list_steps.setItemWidget(item, card)
        self.list_steps.blockSignals(False)
        self.lbl_no_steps.setVisible(not self.project.steps)
        self.list_steps.setVisible(bool(self.project.steps))
        self._sync_card_selection()

    def _sync_card_selection(self):
        current = self.list_steps.currentRow()
        for row in range(self.list_steps.count()):
            card = self.list_steps.itemWidget(self.list_steps.item(row))
            if card is not None:
                card.set_selected(row == current)

    def _thumbnail(self, step):
        img = self.project.open_image(step)
        if img is None:
            return None
        img = img.resize((118, max(1, int(img.height * 118 / img.width))))
        return pil_to_pixmap(img)

    def _on_row_changed(self, row):
        self._commit_editor()
        if 0 <= row < len(self.project.steps):
            self.current_step = self.project.steps[row]
            self._load_detail(self.current_step)
        else:
            self.current_step = None
            self.lbl_pick.setVisible(True)
        self._sync_card_selection()

    def _load_detail(self, step):
        self.current_step = step
        self.lbl_pick.setVisible(False)
        text = step.effective_text(self.lang)
        self._loaded_text = text
        self.edit_text.blockSignals(True)
        self.edit_text.setPlainText(text)
        self.edit_text.blockSignals(False)
        self.edit_memo.blockSignals(True)
        self.edit_memo.setPlainText(step.memo)
        self.edit_memo.blockSignals(False)
        self.lbl_target.setText("%s %s" % (tr(self.lang, "lbl_target"),
                                           step.target_name))
        self.lbl_window.setText("%s %s" % (tr(self.lang, "lbl_window"),
                                           step.window_title))
        self.candidate_bar.setVisible(bool(step.mosaic_candidates))
        self._refresh_preview()

    def _refresh_preview(self):
        step = self.current_step
        if step is None:
            self.image_view.set_image(None)
            return
        img = self.project.open_image(step)
        if img is None:
            return
        if step.mosaics:
            img = core.apply_mosaics(img, step.mosaics)
        if step.mosaic_candidates:
            draw = ImageDraw.Draw(img)
            w, h = img.size
            for rect in step.mosaic_candidates:
                x0, y0, x1, y1 = rect.to_pixels(w, h)
                for off in range(3):
                    draw.rectangle([x0 - off, y0 - off, x1 + off, y1 + off],
                                   outline=(255, 200, 0))
        img = core.draw_marker(img, step.click)
        self.image_view.set_image(pil_to_pixmap(img))

    def _commit_editor(self):
        step = self.current_step
        if step is None or self._loaded_text is None:
            return
        text = self.edit_text.toPlainText()
        if text != self._loaded_text:
            step.text_override = text
            self._loaded_text = text
            row = self.project.steps.index(step)
            item = self.list_steps.item(row)
            if item:
                item.setText(self._step_label(row, step))
                card = self.list_steps.itemWidget(item)
                if card is not None:
                    card.set_text(text.replace("\n", " "))

    def _on_memo_changed(self):
        if self.current_step is not None:
            self.current_step.memo = self.edit_memo.toPlainText()

    # -- step operations ----------------------------------------------------
    def _selected_row(self):
        return self.list_steps.currentRow()

    def move_step(self, delta):
        self._commit_editor()
        row = self._selected_row()
        other = row + delta
        if row < 0 or other < 0 or other >= len(self.project.steps):
            return
        steps = self.project.steps
        steps[row], steps[other] = steps[other], steps[row]
        self._refresh_steps()
        self.list_steps.setCurrentRow(other)

    def delete_step(self):
        row = self._selected_row()
        if row < 0:
            return
        self.current_step = None
        self._loaded_text = None
        del self.project.steps[row]
        self._refresh_steps()
        if self.project.steps:
            self.list_steps.setCurrentRow(
                min(row, len(self.project.steps) - 1))

    def duplicate_step(self):
        row = self._selected_row()
        if row < 0:
            return
        import copy as _copy
        src = self.project.steps[row]
        dup = _copy.deepcopy(src)
        dup.image_file = self.project._new_image_name()
        pil = self.project.open_image(src)
        self.project.steps.insert(row + 1, dup)
        if pil is not None:
            dup._pil = pil
        self._refresh_steps()
        self.list_steps.setCurrentRow(row + 1)

    def add_step_from_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr(self.lang, "dlg_add_image"), "",
            tr(self.lang, "filter_images"))
        if not path:
            return
        try:
            with Image.open(path) as im:
                img = im.convert("RGB")
        except Exception as exc:
            self._error(exc)
            return
        step = core.Step(kind=core.KIND_MANUAL)
        self.project.add_step(step, img)
        self._after_step_added()

    # -- mosaic ---------------------------------------------------------------
    def _on_mosaic_dragged(self, x, y, w, h):
        if self.current_step is None:
            return
        self.current_step.mosaics.append(core.Rect(x, y, w, h))
        self._refresh_preview()

    def apply_candidates(self):
        step = self.current_step
        if step is None:
            return
        step.mosaics.extend(step.mosaic_candidates)
        step.mosaic_candidates = []
        self.candidate_bar.setVisible(False)
        self._refresh_preview()

    def dismiss_candidates(self):
        step = self.current_step
        if step is None:
            return
        step.mosaic_candidates = []
        self.candidate_bar.setVisible(False)
        self._refresh_preview()

    def clear_mosaics(self):
        if self.current_step is None:
            return
        self.current_step.mosaics = []
        self._refresh_preview()

    # -- recording ------------------------------------------------------------
    def toggle_recording(self):
        if self.recorder.running:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        try:
            self.recorder.start()
        except Exception as exc:
            self._error(exc)
            return
        self.btn_record.setText(tr(self.lang, "btn_record_stop"))
        self._sync_record_icon()
        self.btn_record.setProperty("recording", "true")
        _repolish(self.btn_record)
        self.panel = RecordPanel(self.lang,
                                 manual_mode=self.recorder.mode == "manual")
        self.panel.setLayoutDirection(self.layoutDirection())
        self.panel.pause_toggled.connect(self.recorder.set_paused)
        self.panel.finish_clicked.connect(self.stop_recording)
        self.panel.capture_clicked.connect(
            lambda: self.manual_capture("panel"))
        self.panel.set_count(len(self.project.steps))
        self.panel.move(self.x() + self.width() - 420, self.y() + 40)
        self.panel.show()

    def stop_recording(self):
        self.recorder.stop()
        self.btn_record.setText(tr(self.lang, "btn_record_start"))
        self._sync_record_icon()
        self.btn_record.setProperty("recording", "false")
        _repolish(self.btn_record)
        if self.panel is not None:
            self.panel.close()
            self.panel = None

    def manual_capture(self, source):
        hidden = []
        if self.panel is not None and source in ("panel", "hotkey"):
            self.panel.hide()
            hidden.append(self.panel)
        if source == "main":
            self.hide()
            hidden.append(self)

        def do_capture():
            title = ""
            if sys.platform == "win32":
                try:
                    title = recorder_mod.UiaElementProvider() \
                        ._top_window_title(None)
                except Exception:
                    title = ""
            self.capturer.capture_now(window_title=title)
            for widget in hidden:
                widget.show()

        QTimer.singleShot(450, do_capture)

    def _on_step_captured(self, step, image):
        self.project.add_step(step, image)
        self._after_step_added()
        if self.panel is not None:
            self.panel.set_count(len(self.project.steps))

    def _after_step_added(self):
        self._refresh_steps()
        self.list_steps.setCurrentRow(len(self.project.steps) - 1)

    # -- project file operations ---------------------------------------------
    def new_project(self):
        self._commit_editor()
        self.stop_recording()
        self.project = core.Project()
        self.current_step = None
        self._loaded_text = None
        self.edit_proj_title.setText("")
        self._refresh_steps()
        self.image_view.set_image(None)

    def open_project(self):
        folder = QFileDialog.getExistingDirectory(
            self, tr(self.lang, "dlg_open_project"))
        if not folder:
            return
        try:
            proj = core.Project.load(folder)
        except Exception as exc:
            self._error(exc)
            return
        self._set_project(proj)
        QMessageBox.information(self, display_name(self.lang),
                                tr(self.lang, "msg_loaded"))

    def _set_project(self, proj):
        self.stop_recording()
        self.project = proj
        self.current_step = None
        self._loaded_text = None
        self.edit_proj_title.setText(proj.title)
        self._refresh_steps()
        if proj.steps:
            self.list_steps.setCurrentRow(0)

    def save_project(self):
        self._commit_editor()
        folder = self.project.folder
        if not folder:
            folder = QFileDialog.getExistingDirectory(
                self, tr(self.lang, "dlg_save_project"))
            if not folder:
                return
        try:
            self.project.title = self.edit_proj_title.text()
            self.project.save(folder)
        except Exception as exc:
            self._error(exc)
            return
        QMessageBox.information(self, display_name(self.lang),
                                tr(self.lang, "msg_saved"))

    def export_zip(self):
        self._commit_editor()
        path, _ = QFileDialog.getSaveFileName(
            self, tr(self.lang, "dlg_zip_export"), "project.zip",
            tr(self.lang, "filter_zip"))
        if not path:
            return
        try:
            self.project.title = self.edit_proj_title.text()
            self.project.export_zip(path)
        except Exception as exc:
            self._error(exc)
            return
        QMessageBox.information(self, display_name(self.lang),
                                tr(self.lang, "msg_saved"))

    def import_zip(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr(self.lang, "dlg_zip_import"), "",
            tr(self.lang, "filter_zip"))
        if not path:
            return
        dest = QFileDialog.getExistingDirectory(
            self, tr(self.lang, "dlg_open_project"))
        if not dest:
            return
        target = os.path.join(dest, "imported_project")
        try:
            proj = core.Project.import_zip(path, target)
        except Exception as exc:
            self._error(exc)
            return
        self._set_project(proj)
        QMessageBox.information(self, display_name(self.lang),
                                tr(self.lang, "msg_loaded"))

    # -- settings / export ------------------------------------------------------
    def open_settings(self):
        dlg = SettingsDialog(self, self.lang,
                             self.settings.get("deepl_key", ""))
        dlg.setLayoutDirection(self.layoutDirection())
        if dlg.exec():
            self.settings["deepl_key"] = dlg.edit_key.text().strip()
            save_settings(self.settings)

    def export_manuals(self):
        self._commit_editor()
        if not self.project.steps:
            QMessageBox.warning(self, display_name(self.lang),
                                tr(self.lang, "msg_no_steps"))
            return
        key = self.settings.get("deepl_key", "")
        dlg = ExportDialog(self, self.lang, has_deepl_key=bool(key))
        dlg.setLayoutDirection(self.layoutDirection())
        if not dlg.exec():
            return
        opts = dlg.options()
        if not opts["out_dir"] or not opts["langs"] or not opts["formats"]:
            return
        translator = core.DeepLTranslator(key) if key else None
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = exporter.export_manuals(
                self.project, opts["out_dir"], opts["langs"],
                opts["formats"], show_marker=opts["show_marker"],
                translator=translator, use_deepl=opts["use_deepl"])
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            self._error(exc)
            return
        QApplication.restoreOverrideCursor()
        msg = tr(self.lang, "msg_export_done", count=len(result.files))
        if result.translate_failed:
            msg += "\n" + tr(self.lang, "msg_export_translate_failed")
        QMessageBox.information(self, display_name(self.lang), msg)

    def _error(self, exc):
        QMessageBox.critical(
            self, display_name(self.lang),
            tr(self.lang, "msg_error", detail=str(exc)))

    def closeEvent(self, event):
        self._commit_editor()
        try:
            self.recorder.stop()
        except Exception:
            pass
        super().closeEvent(event)


# ----------------------------------------------------------------------
# Entry point (with the Wine-only font workaround used by the family)
# ----------------------------------------------------------------------

def _under_wine():
    """True only under Wine (ntdll exports wine_get_version only there).
    Used solely for Wine-only stability workarounds; real Windows is
    untouched. Non-Windows platforms return False at once."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        return hasattr(ctypes.WinDLL("ntdll"), "wine_get_version")
    except Exception:
        return False


def main():
    args = list(sys.argv)
    if _under_wine():
        # Wine-only: Qt's native (DirectWrite) font engine can fault in
        # Wine 9.0 during font fallback. The FreeType engine avoids it.
        args += ["-platform", "windows:fontengine=freetype"]
    app = QApplication(args)
    try:
        import os as _os, sys as _sys
        from PySide6.QtGui import QIcon as _QIcon
        _ib = getattr(_sys, "_MEIPASS", None) or _os.path.dirname(_os.path.abspath(__file__))
        _ip = _os.path.join(_ib, "assets", "icon.png")
        if _os.path.exists(_ip):
            app.setWindowIcon(_QIcon(_ip))
    except Exception:
        pass
    app.setApplicationName(APP_ID)
    app.setStyleSheet(theme.stylesheet())
    if _under_wine():
        try:
            from PySide6.QtGui import QFont, QFontDatabase
            families = set(QFontDatabase.families())
            if families and "Yu Gothic UI" not in families \
                    and "Segoe UI" not in families:
                fallback = "Tahoma" if "Tahoma" in families \
                    else sorted(families)[0]
                app.setFont(QFont(fallback))
        except Exception:
            pass
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
