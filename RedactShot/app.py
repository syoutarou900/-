# -*- coding: utf-8 -*-
"""RedactShot - main GUI.

Screenshot privacy filter: detect sensitive regions in a screenshot,
preview mosaic / blur / blackout effects live, and export only after a
final-preview confirmation. Fully offline; the original image file is
never modified and saving over it is blocked.

Engine modules (worker A) are imported by contract:
  detect.Candidate / detect.CATEGORIES / detect.detect(...)
  effects.EFFECTS / effects.apply_effects(pil_image, items)
  ocr.run_ocr(image_path, ui_lang) / ocr.OcrUnavailable
If an engine module is not present yet, a minimal local fallback keeps
the GUI runnable (manual regions still work).
"""
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field

from PIL import Image

from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QThread, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox,
    QProgressDialog, QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

import appinfo
from i18n import LANG_NAMES, LANG_ORDER, RTL_LANGS, tr

try:
    import fonts as _fonts_mod
    import theme as _theme_mod
except Exception:  # pragma: no cover - fonts/theme ship with the app
    _fonts_mod = None
    _theme_mod = None

# ---------------------------------------------------------------- engine imports
try:
    import detect as _detect_mod
    Candidate = _detect_mod.Candidate
    CATEGORIES = list(_detect_mod.CATEGORIES)
    _detect_fn = _detect_mod.detect
except Exception:
    _detect_mod = None
    CATEGORIES = ["email", "phone", "card", "money", "password", "masked", "custom"]

    @dataclass
    class Candidate:  # fallback mirroring the contract
        id: int
        category: str
        text: str
        reason_key: str
        reason_params: dict = field(default_factory=dict)
        x: int = 0
        y: int = 0
        w: int = 0
        h: int = 0
        enabled: bool = True
        manual: bool = False

    def _detect_fn(words, img_w, img_h, custom_terms, enabled):
        return []

try:
    import effects as _effects_mod
    EFFECTS = list(_effects_mod.EFFECTS)
    _apply_effects_fn = _effects_mod.apply_effects
except Exception:
    _effects_mod = None
    EFFECTS = ["pixelate", "blur", "blackout"]

    def _apply_effects_fn(pil_image, items):
        from PIL import ImageFilter
        out = pil_image.copy().convert("RGB")
        for (x, y, w, h, effect, strength) in items:
            x, y = max(0, int(x)), max(0, int(y))
            w, h = int(w), int(h)
            if w <= 0 or h <= 0 or x >= out.width or y >= out.height:
                continue
            box = (x, y, min(out.width, x + w), min(out.height, y + h))
            region = out.crop(box)
            s = max(1, int(strength))
            if effect == "blackout":
                region = Image.new("RGB", region.size, (0, 0, 0))
            elif effect == "blur":
                # Blur is fixed at the safe level (radius 15), matching
                # effects.BLUR_FIXED_RADIUS; strength is ignored.
                region = region.filter(ImageFilter.GaussianBlur(radius=15.0))
            else:  # pixelate
                # Pixelate is fixed at the safe level (block 14),
                # matching effects.PIXELATE_FIXED_BLOCK; the passed
                # strength is ignored, same as blur.
                block = 14
                small = region.resize(
                    (max(1, region.width // block), max(1, region.height // block)),
                    Image.Resampling.BILINEAR)
                region = small.resize(region.size, Image.Resampling.NEAREST)
            out.paste(region, box)
        return out

try:
    import ocr as _ocr_mod
    OcrUnavailable = _ocr_mod.OcrUnavailable
    _run_ocr_fn = _ocr_mod.run_ocr
except Exception:
    _ocr_mod = None

    class OcrUnavailable(Exception):
        pass

    def _run_ocr_fn(image_path, ui_lang):
        raise OcrUnavailable("ocr module not available")


ALL_CATEGORIES = CATEGORIES + (["manual"] if "manual" not in CATEGORIES else [])

CAT_COLORS = {
    "email": "#2563EB", "phone": "#059669", "card": "#D97706",
    "money": "#7C3AED", "password": "#DC2626", "masked": "#64748B",
    "custom": "#0891B2", "manual": "#D6336C",
}

# The application stylesheet lives in theme.py (modern flat design,
# applied at app level in main() before any widget is built).


def settings_path():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        folder = os.path.join(base, appinfo.APP_ID)
    elif sys.platform == "darwin":
        folder = os.path.join(os.path.expanduser("~"), "Library", "Application Support", appinfo.APP_ID)
    else:
        folder = os.path.join(os.path.expanduser("~"), ".local", "share", appinfo.APP_ID)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "settings.json")


def pil_to_qimage(pil_img):
    img = pil_img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    return QImage(data, img.width, img.height, img.width * 4, QImage.Format.Format_RGBA8888).copy()


def pil_to_qpixmap(pil_img):
    return QPixmap.fromImage(pil_to_qimage(pil_img))


# ---------------------------------------------------------------- canvas
class ImageCanvas(QWidget):
    regionCreated = Signal(int, int, int, int)
    geometryChanged = Signal()
    selectionChanged = Signal(object)
    deleteRequested = Signal(object)

    HANDLE = 9

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 320)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self._pixmap = None          # preview pixmap (effects applied)
        self._img_w = 0
        self._img_h = 0
        self.candidates = []
        self.selected_id = None
        self.add_mode = False
        self.hint_text = ""
        self._drag_kind = None       # None | "new" | "move" | "resize"
        self._drag_start_img = None  # QPointF in image coords
        self._drag_rect_img = None   # QRectF in image coords (new region)
        self._move_offset = None
        self._resize_handle = -1
        self._orig_rect = None

    # -- data ---------------------------------------------------------
    def set_image(self, pixmap, img_w, img_h):
        self._pixmap = pixmap
        self._img_w, self._img_h = img_w, img_h
        self.update()

    def set_candidates(self, candidates):
        self.candidates = candidates
        self.update()

    def set_selected(self, cand_id):
        self.selected_id = cand_id
        self.update()

    # -- geometry -------------------------------------------------------
    def _image_rect(self):
        if not self._img_w or not self._img_h:
            return QRectF()
        margin = 14
        avail_w = max(10, self.width() - margin * 2)
        avail_h = max(10, self.height() - margin * 2)
        scale = min(avail_w / self._img_w, avail_h / self._img_h)
        w, h = self._img_w * scale, self._img_h * scale
        x = (self.width() - w) / 2.0
        y = (self.height() - h) / 2.0
        return QRectF(x, y, w, h)

    def _to_image(self, pos):
        r = self._image_rect()
        if r.isEmpty():
            return None
        scale = r.width() / self._img_w if self._img_w else 1
        x = (pos.x() - r.x()) / scale
        y = (pos.y() - r.y()) / scale
        x = min(max(x, 0.0), float(self._img_w))
        y = min(max(y, 0.0), float(self._img_h))
        return QPointF(x, y)

    def _to_widget_rect(self, cand):
        r = self._image_rect()
        if r.isEmpty():
            return QRectF()
        scale = r.width() / self._img_w if self._img_w else 1
        return QRectF(r.x() + cand.x * scale, r.y() + cand.y * scale,
                      cand.w * scale, cand.h * scale)

    def _find(self, cand_id):
        for c in self.candidates:
            if c.id == cand_id:
                return c
        return None

    def _handle_at(self, pos, cand):
        wr = self._to_widget_rect(cand)
        corners = [wr.topLeft(), wr.topRight(), wr.bottomLeft(), wr.bottomRight()]
        for i, pt in enumerate(corners):
            if abs(pos.x() - pt.x()) <= self.HANDLE and abs(pos.y() - pt.y()) <= self.HANDLE:
                return i
        return -1

    def _hit_candidate(self, img_pt):
        for c in reversed(self.candidates):
            if c.x <= img_pt.x() <= c.x + c.w and c.y <= img_pt.y() <= c.y + c.h:
                return c
        return None

    # -- painting -------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#141824"))
        if self._pixmap is None or self._img_w == 0:
            p.setPen(QColor("#9AA0B5"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.hint_text)
            p.end()
            return
        r = self._image_rect()
        p.drawPixmap(r.toRect(), self._pixmap)
        for c in self.candidates:
            wr = self._to_widget_rect(c)
            is_sel = (c.id == self.selected_id)
            color = QColor(CAT_COLORS.get(c.category, "#D6336C"))
            if c.enabled:
                pen = QPen(color, 3 if is_sel else 2)
            else:
                pen = QPen(QColor("#8A8FA3"), 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(wr)
            if is_sel:
                p.setBrush(QColor("#FFFFFF"))
                p.setPen(QPen(QColor("#D6336C"), 2))
                for pt in (wr.topLeft(), wr.topRight(), wr.bottomLeft(), wr.bottomRight()):
                    half = self.HANDLE / 2.0
                    p.drawRect(QRectF(pt.x() - half, pt.y() - half, self.HANDLE, self.HANDLE))
        if self._drag_kind == "new" and self._drag_rect_img is not None:
            r2 = self._image_rect()
            scale = r2.width() / self._img_w if self._img_w else 1
            wr = QRectF(r2.x() + self._drag_rect_img.x() * scale,
                        r2.y() + self._drag_rect_img.y() * scale,
                        self._drag_rect_img.width() * scale,
                        self._drag_rect_img.height() * scale)
            p.setPen(QPen(QColor("#D6336C"), 2, Qt.PenStyle.DashLine))
            p.setBrush(QColor(214, 51, 108, 40))
            p.drawRect(wr)
        p.end()

    # -- mouse ----------------------------------------------------------
    def mousePressEvent(self, event):
        self.setFocus()
        if self._pixmap is None or event.button() != Qt.MouseButton.LeftButton:
            return
        img_pt = self._to_image(event.position())
        if img_pt is None:
            return
        sel = self._find(self.selected_id)
        if sel is not None:
            h = self._handle_at(event.position(), sel)
            if h >= 0:
                self._drag_kind = "resize"
                self._resize_handle = h
                self._drag_start_img = img_pt
                self._orig_rect = QRectF(sel.x, sel.y, sel.w, sel.h)
                return
        hit = self._hit_candidate(img_pt)
        if hit is not None and not self.add_mode:
            if hit.id != self.selected_id:
                self.selected_id = hit.id
                self.selectionChanged.emit(hit.id)
            self._drag_kind = "move"
            self._drag_start_img = img_pt
            self._move_offset = QPointF(img_pt.x() - hit.x, img_pt.y() - hit.y)
            self._orig_rect = QRectF(hit.x, hit.y, hit.w, hit.h)
            self.update()
            return
        # start a new region
        self._drag_kind = "new"
        self._drag_start_img = img_pt
        self._drag_rect_img = QRectF(img_pt, img_pt)

    def mouseMoveEvent(self, event):
        if self._drag_kind is None or self._pixmap is None:
            return
        img_pt = self._to_image(event.position())
        if img_pt is None:
            return
        if self._drag_kind == "new":
            self._drag_rect_img = QRectF(self._drag_start_img, img_pt).normalized()
        elif self._drag_kind == "move":
            c = self._find(self.selected_id)
            if c is not None and self._move_offset is not None:
                c.x = int(min(max(img_pt.x() - self._move_offset.x(), 0), max(0, self._img_w - c.w)))
                c.y = int(min(max(img_pt.y() - self._move_offset.y(), 0), max(0, self._img_h - c.h)))
        elif self._drag_kind == "resize":
            c = self._find(self.selected_id)
            if c is not None and self._orig_rect is not None:
                o = self._orig_rect
                x1, y1, x2, y2 = o.left(), o.top(), o.right(), o.bottom()
                if self._resize_handle in (0, 2):
                    x1 = img_pt.x()
                if self._resize_handle in (1, 3):
                    x2 = img_pt.x()
                if self._resize_handle in (0, 1):
                    y1 = img_pt.y()
                if self._resize_handle in (2, 3):
                    y2 = img_pt.y()
                rect = QRectF(QPointF(x1, y1), QPointF(x2, y2)).normalized()
                rect = rect.intersected(QRectF(0, 0, self._img_w, self._img_h))
                if rect.width() >= 2 and rect.height() >= 2:
                    c.x, c.y = int(rect.x()), int(rect.y())
                    c.w, c.h = int(rect.width()), int(rect.height())
        self.update()

    def mouseReleaseEvent(self, event):
        if self._drag_kind == "new" and self._drag_rect_img is not None:
            r = self._drag_rect_img
            if r.width() >= 4 and r.height() >= 4:
                self.regionCreated.emit(int(r.x()), int(r.y()), int(r.width()), int(r.height()))
            else:
                # plain click on empty space: deselect
                if self.selected_id is not None:
                    self.selected_id = None
                    self.selectionChanged.emit(None)
        elif self._drag_kind in ("move", "resize"):
            self.geometryChanged.emit()
        self._drag_kind = None
        self._drag_rect_img = None
        self._orig_rect = None
        self.update()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.selected_id is not None:
            self.deleteRequested.emit(self.selected_id)
        else:
            super().keyPressEvent(event)


# ---------------------------------------------------------------- dialogs
class FinalPreviewDialog(QDialog):
    """Shows the finished (effects-applied) image; export only on confirm."""

    def __init__(self, pil_image, lang, parent=None):
        super().__init__(parent)
        self.lang = lang
        self.setWindowTitle(tr(lang, "final_preview"))
        self.resize(760, 620)
        v = QVBoxLayout(self)
        msg = QLabel(tr(lang, "preview_check_message"))
        msg.setWordWrap(True)
        msg.setStyleSheet("font-weight: 700; color: #A61E4D;")
        v.addWidget(msg)
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setStyleSheet("background: #141824; border-radius: 10px;")
        pix = pil_to_qpixmap(pil_image)
        self._full_pix = pix
        v.addWidget(self.img_label, 1)
        self._fit_pixmap()
        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_cancel = QPushButton(tr(lang, "cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_confirm = QPushButton(tr(lang, "confirm_export"))
        self.btn_confirm.setProperty("class", "primary")
        self.btn_confirm.setStyleSheet("QPushButton { padding: 8px 18px; }")
        self.btn_confirm.clicked.connect(self.accept)
        row.addWidget(self.btn_cancel)
        row.addWidget(self.btn_confirm)
        v.addLayout(row)

    def _fit_pixmap(self):
        if hasattr(self, "_full_pix"):
            scaled = self._full_pix.scaled(720, 460, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation)
            self.img_label.setPixmap(scaled)


class SettingsDialog(QDialog):
    def __init__(self, settings, lang, parent=None):
        super().__init__(parent)
        self.lang = lang
        self.settings = settings
        self.setWindowTitle(tr(lang, "settings_title"))
        self.resize(520, 560)
        v = QVBoxLayout(self)

        v.addWidget(QLabel(tr(lang, "custom_terms")))
        self.term_list = QListWidget()
        self.term_list.addItems(list(settings.get("custom_terms", [])))
        v.addWidget(self.term_list)
        row = QHBoxLayout()
        self.term_edit = QLineEdit()
        self.term_edit.setPlaceholderText(tr(lang, "term_placeholder"))
        self.btn_add_term = QPushButton(tr(lang, "add_term"))
        self.btn_add_term.clicked.connect(self._add_term)
        self.btn_remove_term = QPushButton(tr(lang, "remove_term"))
        self.btn_remove_term.clicked.connect(self._remove_term)
        row.addWidget(self.term_edit, 1)
        row.addWidget(self.btn_add_term)
        row.addWidget(self.btn_remove_term)
        v.addLayout(row)

        v.addWidget(QLabel(tr(lang, "default_settings")))
        erow = QHBoxLayout()
        erow.addWidget(QLabel(tr(lang, "default_effect")))
        self.effect_combo = QComboBox()
        for eff in EFFECTS:
            self.effect_combo.addItem(tr(lang, f"effect_{eff}"), eff)
        cur = settings.get("default_effect", EFFECTS[0])
        if cur in EFFECTS:
            self.effect_combo.setCurrentIndex(EFFECTS.index(cur))
        erow.addWidget(self.effect_combo, 1)
        v.addLayout(erow)
        # Effect strength is fixed at a safe level for every effect and
        # cannot be changed, so there is no strength control here; a
        # note next to the default-effect picker explains that.
        self.fixed_note = QLabel(tr(lang, "strength_fixed_note"))
        self.fixed_note.setWordWrap(True)
        self.fixed_note.setStyleSheet("color: #B02A54; font-size: 11px; font-weight: 700;")
        v.addWidget(self.fixed_note)

        v.addWidget(QLabel(tr(lang, "initial_categories")))
        self.cat_checks = {}
        enabled = settings.get("enabled_categories", {})
        grid = QVBoxLayout()
        for cat in ALL_CATEGORIES:
            cb = QCheckBox(tr(lang, f"cat_{cat}"))
            cb.setChecked(bool(enabled.get(cat, True)))
            self.cat_checks[cat] = cb
            grid.addWidget(cb)
        v.addLayout(grid)
        v.addStretch(1)
        brow = QHBoxLayout()
        brow.addStretch(1)
        btn_cancel = QPushButton(tr(lang, "cancel"))
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton(tr(lang, "ok"))
        btn_ok.setProperty("class", "primary")
        btn_ok.clicked.connect(self.accept)
        brow.addWidget(btn_cancel)
        brow.addWidget(btn_ok)
        v.addLayout(brow)

    def _add_term(self):
        text = self.term_edit.text().strip()
        if text and not self.term_list.findItems(text, Qt.MatchFlag.MatchExactly):
            self.term_list.addItem(text)
        self.term_edit.clear()

    def _remove_term(self):
        for item in self.term_list.selectedItems():
            self.term_list.takeItem(self.term_list.row(item))

    def result_settings(self):
        out = dict(self.settings)
        out["custom_terms"] = [self.term_list.item(i).text() for i in range(self.term_list.count())]
        out["default_effect"] = self.effect_combo.currentData()
        out.pop("default_strength", None)  # strength is fixed; drop legacy key
        out["enabled_categories"] = {cat: cb.isChecked() for cat, cb in self.cat_checks.items()}
        return out


# ---------------------------------------------------------------- main window

class OcrThread(QThread):
    """Runs OCR off the UI thread so large screenshots never freeze the window."""
    done = Signal(object)    # list of word dicts
    failed = Signal(object)  # exception instance

    def __init__(self, image_path, ui_lang, parent=None):
        super().__init__(parent)
        self._image_path = image_path
        self._ui_lang = ui_lang

    def run(self):
        try:
            words = _run_ocr_fn(self._image_path, self._ui_lang)
        except Exception as exc:  # OcrUnavailable or anything unexpected
            self.failed.emit(exc)
            return
        self.done.emit(words)


class MainWindow(QMainWindow):
    MAX_PIXELS = 120_000_000  # refuse decompression-bomb scale images

    def __init__(self):
        super().__init__()
        self.settings = self._load_settings()
        self.lang = self.settings.get("lang", "ja")
        if self.lang not in LANG_ORDER:
            self.lang = "ja"
        self.original_pil = None       # PIL Image, full resolution, never modified
        self.original_path = None
        self.source_name = ""
        self.candidates = []
        self._last_words = None
        self._manual_counter = 0
        self._preview_key = None
        self._preview_pil = None
        self._row_widgets = {}         # candidate id -> dict of widgets
        self._cat_bulk_checks = {}
        self._ocr_thread = None
        self._ocr_generation = 0
        self._progress = None
        self._progress_timer = QTimer(self)
        self._progress_timer.setSingleShot(True)
        self._progress_timer.timeout.connect(self._show_progress)

        self._build_ui()
        # apply the saved default effect (strength is fixed by design)
        eff = self.settings.get("default_effect", EFFECTS[0])
        if eff in EFFECTS:
            self.effect_combo.setCurrentIndex(EFFECTS.index(eff))
        self.apply_language(self.lang, save=False)
        self.status_label.setText(self.t("status_ready"))

    # -- helpers ---------------------------------------------------------
    def t(self, key, **kw):
        return tr(self.lang, key, **kw)

    def cat_label(self, cat):
        return self.t(f"cat_{cat}") if f"cat_{cat}" in _all_keys() else cat

    def reason_text(self, cand):
        params = dict(getattr(cand, "reason_params", {}) or {})
        return self.t(cand.reason_key, **params)

    # -- settings ---------------------------------------------------------
    def _load_settings(self):
        defaults = {
            "lang": "ja", "custom_terms": [],
            "default_effect": EFFECTS[0],
            "enabled_categories": {c: True for c in ALL_CATEGORIES},
        }
        try:
            with open(settings_path(), encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                defaults.update(data)
                # Legacy key from the adjustable-strength era: effect
                # strength is fixed now, so the value is dropped.
                defaults.pop("default_strength", None)
                merged = {c: True for c in ALL_CATEGORIES}
                if isinstance(defaults.get("enabled_categories"), dict):
                    merged.update(defaults["enabled_categories"])
                defaults["enabled_categories"] = merged
        except Exception:
            pass
        return defaults

    def _save_settings(self):
        self.settings["lang"] = self.lang
        try:
            with open(settings_path(), "w", encoding="utf-8") as fh:
                json.dump(self.settings, fh, ensure_ascii=False, indent=1)
        except Exception:
            pass

    # -- UI build ---------------------------------------------------------
    def _build_ui(self):
        self.setMinimumSize(1080, 700)
        self.resize(1240, 800)
        self.setAcceptDrops(True)
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 8)
        root.setSpacing(8)

        # header: dark slate + magenta accent (distinct from other apps)
        # NOTE: the selector must be #objectName, not "QFrame": QLabel
        # inherits QFrame, so a "QFrame { ... }" rule leaks onto every
        # label inside the frame (each label drew the frame's border).
        header = QFrame()
        header.setObjectName("headerFrame")
        header.setStyleSheet(
            "#headerFrame { background: #1E2432; border-radius: 14px; "
            "border-bottom: 4px solid #D6336C; }")
        hv = QHBoxLayout(header)
        hv.setContentsMargins(16, 12, 16, 12)
        title_box = QVBoxLayout()
        self.title_label = QLabel()
        self.title_label.setStyleSheet("color: #FFFFFF; font-size: 22px; font-weight: 800;")
        self.subtitle_label = QLabel()
        self.subtitle_label.setStyleSheet("color: #C3C9D9; font-size: 12px;")
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)
        hv.addLayout(title_box)
        hv.addStretch(1)
        self.lang_label = QLabel()
        self.lang_label.setStyleSheet("color: #FFFFFF; font-weight: 700;")
        hv.addWidget(self.lang_label)
        self.lang_combo = QComboBox()
        self.lang_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        for code in LANG_ORDER:
            self.lang_combo.addItem(LANG_NAMES[code], code)
        if self.lang in LANG_ORDER:
            self.lang_combo.setCurrentIndex(LANG_ORDER.index(self.lang))
        self.lang_combo.currentIndexChanged.connect(
            lambda i: self.apply_language(self.lang_combo.itemData(i)))
        hv.addWidget(self.lang_combo)
        root.addWidget(header)

        # OCR / info banner
        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet(
            "background: #FFF3CD; color: #664D03; border: 1.5px solid #FFCA2C;"
            " border-radius: 10px; padding: 8px 12px; font-weight: 600;")
        self.banner.hide()
        root.addWidget(self.banner)

        # toolbar
        bar = QHBoxLayout()
        bar.setSpacing(7)
        self.btn_open = QPushButton()
        self.btn_open.clicked.connect(self.open_image_dialog)
        self.btn_paste = QPushButton()
        self.btn_paste.clicked.connect(self.paste_from_clipboard)
        self.btn_add = QPushButton()
        self.btn_add.setCheckable(True)
        self.btn_add.toggled.connect(self._on_add_mode_toggled)
        for b in (self.btn_open, self.btn_paste, self.btn_add):
            bar.addWidget(b)
        bar.addWidget(QLabel("|"))
        self.effect_label = QLabel()
        bar.addWidget(self.effect_label)
        self.effect_combo = QComboBox()
        # Long localised effect names (e.g. Arabic) were clipped after a
        # language switch because the combo kept its first-show width.
        self.effect_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        for eff in EFFECTS:
            self.effect_combo.addItem(eff, eff)
        self.effect_combo.currentIndexChanged.connect(lambda _i: self._on_effect_changed())
        bar.addWidget(self.effect_combo)
        bar.addStretch(1)
        self.btn_export = QPushButton()
        self.btn_export.setProperty("class", "primary")
        self.btn_export.clicked.connect(self.export_flow)
        self.btn_copy = QPushButton()
        self.btn_copy.clicked.connect(self.copy_to_clipboard)
        self.btn_settings = QPushButton()
        self.btn_settings.clicked.connect(self.open_settings)
        for b in (self.btn_export, self.btn_copy, self.btn_settings):
            bar.addWidget(b)
        root.addLayout(bar)

        # No strength control anywhere: every effect is fixed at a safe
        # level. The note gets its own full-width row under the toolbar
        # so long translations can never squeeze or overlap the toolbar.
        self.fixed_note = QLabel()
        self.fixed_note.setWordWrap(True)
        self.fixed_note.setStyleSheet("color: #B02A54; font-size: 11px; font-weight: 700;")
        root.addWidget(self.fixed_note)

        # main split: canvas (left) + candidate panel (right)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.canvas = ImageCanvas()
        self.canvas.regionCreated.connect(self.add_manual_region)
        self.canvas.selectionChanged.connect(self._on_canvas_selection)
        self.canvas.geometryChanged.connect(self.refresh_preview)
        self.canvas.deleteRequested.connect(self.delete_candidate)
        splitter.addWidget(self.canvas)

        panel = QFrame()
        panel.setObjectName("candidatePanel")
        panel.setStyleSheet("#candidatePanel { background: #FFFFFF; border: 1px solid #E1E4EC; border-radius: 14px; }")
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(10, 10, 10, 10)
        self.candidates_title = QLabel()
        self.candidates_title.setStyleSheet("font-weight: 800; font-size: 14px; color: #1E2432;")
        pv.addWidget(self.candidates_title)
        self.bulk_layout = QVBoxLayout()
        pv.addLayout(self.bulk_layout)
        self.cand_scroll = QScrollArea()
        self.cand_scroll.setWidgetResizable(True)
        self.cand_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.cand_content = QWidget()
        self.cand_layout = QVBoxLayout(self.cand_content)
        self.cand_layout.setContentsMargins(2, 2, 2, 2)
        self.cand_layout.setSpacing(7)
        self.cand_scroll.setWidget(self.cand_content)
        pv.addWidget(self.cand_scroll, 1)
        self.delete_hint_label = QLabel()
        self.delete_hint_label.setStyleSheet("color: #6B7280; font-size: 11px;")
        pv.addWidget(self.delete_hint_label)
        splitter.addWidget(panel)
        splitter.setSizes([760, 400])
        root.addWidget(splitter, 1)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #3F465E; font-size: 12px; font-weight: 600;")
        root.addWidget(self.status_label)

    # -- language ---------------------------------------------------------
    def apply_language(self, lang, save=True):
        if lang not in LANG_ORDER:
            lang = "ja"
        self.lang = lang
        if save:
            self._save_settings()
        idx = LANG_ORDER.index(lang)
        if self.lang_combo.currentIndex() != idx:
            self.lang_combo.blockSignals(True)
            self.lang_combo.setCurrentIndex(idx)
            self.lang_combo.blockSignals(False)
        direction = Qt.LayoutDirection.RightToLeft if lang in RTL_LANGS else Qt.LayoutDirection.LeftToRight
        QApplication.instance().setLayoutDirection(direction)
        self.setLayoutDirection(direction)
        # Bundled-font stack follows the language; re-polish the whole
        # tree so existing widgets adopt it at once (a font change
        # alone does not re-resolve families in the frozen build).
        if _fonts_mod is not None:
            app_inst = QApplication.instance()
            if app_inst is not None:
                _fonts_mod.apply_language_font(app_inst, lang)
                style = self.style()
                for widget in [self, *self.findChildren(QWidget)]:
                    style.unpolish(widget)
                    style.polish(widget)
        name = appinfo.display_name(lang)
        self.setWindowTitle(f"{name} — {appinfo.APP_ID} {appinfo.VERSION}")
        self.title_label.setText(name)
        self.subtitle_label.setText(self.t("subtitle"))
        self.lang_label.setText(self.t("language"))
        self.btn_open.setText(self.t("open_image"))
        self.btn_paste.setText(self.t("paste_image"))
        self.btn_add.setText(self.t("add_region"))
        self.effect_label.setText(self.t("effect"))
        self.fixed_note.setText(self.t("strength_fixed_note"))
        # re-localise effect combo, preserving selection
        cur_eff = self.effect_combo.currentData() or EFFECTS[0]
        self.effect_combo.blockSignals(True)
        self.effect_combo.clear()
        for eff in EFFECTS:
            self.effect_combo.addItem(self.t(f"effect_{eff}"), eff)
        if cur_eff in EFFECTS:
            self.effect_combo.setCurrentIndex(EFFECTS.index(cur_eff))
        self.effect_combo.blockSignals(False)
        self.btn_export.setText(self.t("export"))
        self.btn_copy.setText(self.t("copy_clipboard"))
        self.btn_settings.setText(self.t("settings"))
        self.candidates_title.setText(self.t("candidates"))
        self.delete_hint_label.setText(self.t("delete_hint"))
        self.canvas.hint_text = self.t("drop_hint") + "\n" + self.t("no_image")
        self.canvas.update()
        # The status line kept the previous language's text after a
        # switch; re-render it for the current state in the new language.
        if self.original_pil is None:
            self.status_label.setText(self.t("status_ready"))
        else:
            self.status_label.setText(
                self.t("status_loaded", name=self.source_name,
                       count=len(self.candidates)))
        # If the OCR banner is showing, its text is language-specific too.
        if self.banner.isVisible():
            self.banner.setText(self.t("ocr_unavailable"))
        self.rebuild_candidate_panel()
        self.refresh_preview()

    # -- image loading ------------------------------------------------------
    def open_image_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, self.t("open_title"), "", self.t("open_filter"))
        if path:
            self.load_path(path)

    def load_path(self, path):
        try:
            pil = Image.open(path)
            # Size check from the header BEFORE decoding: load_pil also
            # checks MAX_PIXELS, but decoding a decompression-bomb-scale
            # image first (measured: ~1.1 GB peak RSS for 130 MP) defeats
            # the purpose of the limit.
            if pil.width * pil.height > self.MAX_PIXELS:
                QMessageBox.warning(self, appinfo.display_name(self.lang),
                                    self.t("image_too_large"))
                return
            pil.load()
            pil = pil.convert("RGB")
        except Exception as exc:
            QMessageBox.warning(self, appinfo.display_name(self.lang), self.t("load_error", error=str(exc)))
            return
        self.load_pil(pil, source_path=path, display_name=os.path.basename(path))

    def load_pil(self, pil_image, source_path=None, display_name="clipboard"):
        if pil_image.width * pil_image.height > self.MAX_PIXELS:
            QMessageBox.warning(self, appinfo.display_name(self.lang),
                                self.t("image_too_large"))
            return
        self.original_pil = pil_image.copy()
        self.original_path = os.path.abspath(source_path) if source_path else None
        self.source_name = display_name
        self.candidates = []
        self._last_words = None
        self.banner.hide()
        self._preview_key = None
        self.canvas.set_selected(None)
        self.rebuild_candidate_panel()
        self.refresh_preview(force=True)
        self.status_label.setText(self.t("detecting"))
        self._start_detection(source_path)

    def _start_detection(self, source_path):
        """Kick off OCR on a worker thread; the UI stays responsive."""
        self._ocr_generation += 1
        gen = self._ocr_generation
        path_for_ocr = source_path
        tmp_path = None
        if not path_for_ocr:
            fd, tmp_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            self.original_pil.save(tmp_path)
            path_for_ocr = tmp_path
        thread = OcrThread(path_for_ocr, self.lang, self)
        self._ocr_thread = thread
        self._progress_timer.start(400)

        def _cleanup():
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

        thread.done.connect(lambda words: self._on_ocr_done(gen, words, _cleanup))
        thread.failed.connect(lambda exc: self._on_ocr_failed(gen, exc, _cleanup))
        thread.start()

    def _show_progress(self):
        if self._ocr_thread is None or self._progress is not None:
            return
        dlg = QProgressDialog(self.t("detecting"), None, 0, 0, self)
        dlg.setWindowTitle(appinfo.display_name(self.lang))
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setCancelButton(None)
        dlg.setMinimumDuration(0)
        self._progress = dlg
        dlg.show()

    def _close_progress(self):
        self._progress_timer.stop()
        if self._progress is not None:
            self._progress.close()
            self._progress = None

    def _on_ocr_done(self, gen, words, cleanup):
        cleanup()
        if gen != self._ocr_generation:
            return  # a newer image superseded this run
        self._ocr_thread = None
        self._close_progress()
        self._last_words = words
        img_w, img_h = self.original_pil.size
        enabled = {c for c, on in self.settings.get("enabled_categories", {}).items() if on}
        if not enabled:
            enabled = set(ALL_CATEGORIES)
        try:
            found = _detect_fn(words, img_w, img_h,
                               list(self.settings.get("custom_terms", [])), enabled)
        except Exception:
            found = []
        cat_on = self.settings.get("enabled_categories", {})
        for cand in found:
            if cand.category in cat_on:
                cand.enabled = bool(cat_on[cand.category])
        self.candidates = list(found)
        self.rebuild_candidate_panel()
        self.refresh_preview(force=True)
        self.status_label.setText(
            self.t("status_loaded", name=self.source_name, count=len(self.candidates)))

    def _on_ocr_failed(self, gen, exc, cleanup):
        cleanup()
        if gen != self._ocr_generation:
            return
        self._ocr_thread = None
        self._close_progress()
        self.candidates = []
        self.banner.setText(self.t("ocr_unavailable"))
        self.banner.show()
        self.rebuild_candidate_panel()
        self.refresh_preview(force=True)
        self.status_label.setText(
            self.t("status_loaded", name=self.source_name, count=0))

    def paste_from_clipboard(self):
        clip = QApplication.clipboard()
        mime = clip.mimeData()
        if mime is not None and mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    self.load_path(url.toLocalFile())
                    return
        image = clip.image()
        if image is None or image.isNull():
            self.status_label.setText(self.t("clipboard_no_image"))
            return
        image = image.convertToFormat(QImage.Format.Format_RGBA8888)
        ptr = image.bits()
        data = bytes(ptr[: image.sizeInBytes()]) if hasattr(ptr, "__getitem__") else ptr.tobytes()
        pil = Image.frombytes("RGBA", (image.width(), image.height()), data).convert("RGB")
        self.load_pil(pil, source_path=None, display_name="clipboard")

    # -- candidates ---------------------------------------------------------
    def add_manual_region(self, x, y, w, h):
        if self.original_pil is None:
            return
        self._manual_counter += 1
        cand = Candidate(
            id=100000 + self._manual_counter, category="manual", text="",
            reason_key="reason_manual", reason_params={},
            x=int(x), y=int(y), w=int(w), h=int(h), enabled=True, manual=True)
        self.candidates.append(cand)
        self.canvas.set_selected(cand.id)
        self.rebuild_candidate_panel()
        self.refresh_preview()
        self.status_label.setText(
            self.t("status_loaded", name=self.source_name, count=len(self.candidates)))

    def delete_candidate(self, cand_id):
        self.candidates = [c for c in self.candidates if c.id != cand_id]
        self.canvas.set_selected(None)
        self.rebuild_candidate_panel()
        self.refresh_preview()
        if self.original_pil is not None:
            self.status_label.setText(
                self.t("status_loaded", name=self.source_name, count=len(self.candidates)))

    def _on_canvas_selection(self, cand_id):
        self.canvas.set_selected(cand_id)
        self._highlight_row(cand_id)

    def _on_add_mode_toggled(self, checked):
        self.canvas.add_mode = bool(checked)
        if checked:
            self.status_label.setText(self.t("add_region_on"))
        self.canvas.setCursor(Qt.CursorShape.CrossCursor if checked else Qt.CursorShape.ArrowCursor)

    def _on_effect_changed(self):
        self.refresh_preview()

    def current_effect(self):
        return self.effect_combo.currentData() or EFFECTS[0]

    def current_strength(self):
        # Kept for the apply_effects() call contract only: effects.py
        # ignores this value and always applies the fixed safe level
        # for blur and pixelate (blackout never used it).
        return 10

    def _clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            w = child.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
            elif child.layout() is not None:
                self._clear_layout(child.layout())

    def rebuild_candidate_panel(self):
        self._clear_layout(self.bulk_layout)
        self._clear_layout(self.cand_layout)
        self._row_widgets = {}
        self._cat_bulk_checks = {}
        self._ocr_thread = None
        self._ocr_generation = 0
        self._progress = None
        self._progress_timer = QTimer(self)
        self._progress_timer.setSingleShot(True)
        self._progress_timer.timeout.connect(self._show_progress)
        self.candidates_title.setText(
            f"{self.t('candidates')} — {self.t('candidate_count', count=len(self.candidates))}")
        # category bulk toggles
        cats_present = []
        for c in self.candidates:
            if c.category not in cats_present:
                cats_present.append(c.category)
        for cat in cats_present:
            row = QHBoxLayout()
            chip = QLabel()
            chip.setFixedSize(12, 12)
            chip.setStyleSheet(f"background: {CAT_COLORS.get(cat, '#D6336C')}; border-radius: 3px;")
            row.addWidget(chip)
            cb = QCheckBox(self.cat_label(cat))
            members = [c for c in self.candidates if c.category == cat]
            cb.setChecked(all(c.enabled for c in members))
            cb.setToolTip(self.t("select_all_cat"))
            cb.toggled.connect(lambda checked, cat=cat: self._bulk_toggle(cat, checked))
            self._cat_bulk_checks[cat] = cb
            row.addWidget(cb)
            row.addStretch(1)
            holder = QWidget()
            holder.setLayout(row)
            self.bulk_layout.addWidget(holder)
        if not self.candidates:
            lab = QLabel(self.t("no_candidates"))
            lab.setWordWrap(True)
            lab.setStyleSheet("color: #6B7280; padding: 10px;")
            self.cand_layout.addWidget(lab)
        for cand in self.candidates:
            self.cand_layout.addWidget(self._build_candidate_row(cand))
        self.cand_layout.addStretch(1)
        self.canvas.set_candidates(self.candidates)

    def _build_candidate_row(self, cand):
        frame = QFrame()
        frame.setObjectName("candidateRow")
        is_sel = (cand.id == self.canvas.selected_id)
        frame.setStyleSheet(
            "#candidateRow { background: %s; border: 1.5px solid %s; border-radius: 10px; }"
            % (("#FFF7FA" if is_sel else "#FFFFFF"),
               ("#D6336C" if is_sel else "#E3E5EC")))
        h = QHBoxLayout(frame)
        h.setContentsMargins(8, 6, 8, 6)
        cb = QCheckBox()
        cb.setChecked(bool(cand.enabled))
        cb.toggled.connect(lambda checked, cid=cand.id: self._candidate_toggled(cid, checked))
        h.addWidget(cb)
        chip = QLabel()
        chip.setFixedSize(12, 12)
        chip.setStyleSheet(f"background: {CAT_COLORS.get(cand.category, '#D6336C')}; border-radius: 3px;")
        h.addWidget(chip)
        texts = QVBoxLayout()
        title = self.cat_label(cand.category)
        if cand.category == "password":
            title = f"{title} · {self.t('password_note')}"
        shown_text = cand.text if cand.text else self.t("manual_region_text")
        top = QLabel(f"{title}: {shown_text}")
        top.setWordWrap(True)
        top.setStyleSheet("font-weight: 700; font-size: 12px;")
        bottom = QLabel(f"{self.t('reason')}: {self.reason_text(cand)}")
        bottom.setWordWrap(True)
        bottom.setStyleSheet("color: #5B6172; font-size: 11px;")
        texts.addWidget(top)
        texts.addWidget(bottom)
        h.addLayout(texts, 1)
        frame.mousePressEvent = lambda event, cid=cand.id: self._select_candidate(cid)
        self._row_widgets[cand.id] = {"frame": frame, "checkbox": cb}
        return frame

    def _highlight_row(self, cand_id):
        for cid, widgets in self._row_widgets.items():
            sel = (cid == cand_id)
            widgets["frame"].setStyleSheet(
                "#candidateRow { background: %s; border: 1.5px solid %s; border-radius: 10px; }"
                % (("#FFF7FA" if sel else "#FFFFFF"),
                   ("#D6336C" if sel else "#E3E5EC")))

    def _select_candidate(self, cand_id):
        self.canvas.set_selected(cand_id)
        self._highlight_row(cand_id)

    def _candidate_toggled(self, cand_id, checked):
        for c in self.candidates:
            if c.id == cand_id:
                c.enabled = bool(checked)
                break
        self.refresh_preview()
        self._sync_bulk_checks()

    def _bulk_toggle(self, cat, checked):
        for c in self.candidates:
            if c.category == cat:
                c.enabled = bool(checked)
        # update row checkboxes without a full rebuild
        for c in self.candidates:
            if c.category == cat and c.id in self._row_widgets:
                cb = self._row_widgets[c.id]["checkbox"]
                cb.blockSignals(True)
                cb.setChecked(bool(checked))
                cb.blockSignals(False)
        self.refresh_preview()

    def _sync_bulk_checks(self):
        for cat, cb in self._cat_bulk_checks.items():
            members = [c for c in self.candidates if c.category == cat]
            if members:
                cb.blockSignals(True)
                cb.setChecked(all(c.enabled for c in members))
                cb.blockSignals(False)

    # -- preview / export -----------------------------------------------------
    def enabled_items(self):
        eff, strength = self.current_effect(), self.current_strength()
        return [(c.x, c.y, c.w, c.h, eff, strength) for c in self.candidates if c.enabled]

    def build_final_image(self):
        """Full-resolution image with effects applied (original is untouched)."""
        if self.original_pil is None:
            return None
        return _apply_effects_fn(self.original_pil.copy(), self.enabled_items())

    def refresh_preview(self, force=False):
        if self.original_pil is None:
            self.canvas.set_image(None, 0, 0)
            return
        key = (id(self.original_pil), tuple(self.enabled_items()),
               tuple((c.id, c.x, c.y, c.w, c.h, c.enabled) for c in self.candidates))
        if not force and key == self._preview_key and self._preview_pil is not None:
            return
        self._preview_key = key
        self._preview_pil = self.build_final_image()
        pix = pil_to_qpixmap(self._preview_pil)
        self.canvas.set_image(pix, self.original_pil.width, self.original_pil.height)
        self.canvas.set_candidates(self.candidates)

    def export_flow(self):
        """Export must always pass through the final-preview dialog."""
        if self.original_pil is None:
            self.status_label.setText(self.t("no_image"))
            return
        final = self.build_final_image()
        dlg = FinalPreviewDialog(final, self.lang, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if self.original_path:
            stem = os.path.splitext(os.path.basename(self.original_path))[0]
            folder = os.path.dirname(self.original_path)
            initial = os.path.join(folder, f"{stem}_redacted.png")
        else:
            initial = "screenshot_redacted.png"
        path, _filter = QFileDialog.getSaveFileName(
            self, self.t("save_title"), initial, "PNG (*.png);;JPEG (*.jpg *.jpeg)")
        if not path:
            return
        if self.original_path and os.path.normcase(os.path.abspath(path)) == os.path.normcase(self.original_path):
            QMessageBox.warning(self, appinfo.display_name(self.lang), self.t("overwrite_blocked"))
            return
        out = final
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext in (".jpg", ".jpeg"):
                out.convert("RGB").save(path, format="JPEG", quality=92)
            else:
                if not ext:
                    path += ".png"
                out.save(path, format="PNG")
        except Exception as exc:
            QMessageBox.warning(self, appinfo.display_name(self.lang), self.t("load_error", error=str(exc)))
            return
        self.status_label.setText(f"{self.t('saved')}: {path}")

    def copy_to_clipboard(self):
        if self.original_pil is None:
            self.status_label.setText(self.t("no_image"))
            return
        final = self.build_final_image()
        QApplication.clipboard().setImage(pil_to_qimage(final))
        self.status_label.setText(self.t("copied"))

    # -- settings dialog -------------------------------------------------------
    def open_settings(self):
        dlg = SettingsDialog(self.settings, self.lang, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.settings = dlg.result_settings()
            self.settings["default_effect"] = dlg.result_settings()["default_effect"]
            self._save_settings()
            # if words are cached, re-detect with the new terms/categories
            if self.original_pil is not None and self._last_words is not None:
                manual = [c for c in self.candidates if getattr(c, "manual", False)]
                img_w, img_h = self.original_pil.size
                enabled = {c for c, on in self.settings.get("enabled_categories", {}).items() if on}
                try:
                    found = _detect_fn(self._last_words, img_w, img_h,
                                       list(self.settings.get("custom_terms", [])), enabled)
                    self.candidates = list(found) + manual
                except Exception:
                    pass
                self.rebuild_candidate_panel()
            self.refresh_preview(force=True)

    # -- drag & drop --------------------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp")):
                self.load_path(path)


_KEY_CACHE = None


def _all_keys():
    global _KEY_CACHE
    if _KEY_CACHE is None:
        from i18n import STRINGS
        _KEY_CACHE = set(STRINGS.get("ja", {}).keys())
    return _KEY_CACHE


def _under_wine():
    """True only when running under Wine (never on real Windows)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        return hasattr(ctypes.windll.ntdll, "wine_get_version")
    except Exception:
        return False


def _initial_lang():
    """Language from the saved settings (for the pre-window font)."""
    try:
        with open(settings_path(), encoding="utf-8") as fh:
            lang = json.load(fh).get("lang", "ja")
        return lang if lang in LANG_ORDER else "ja"
    except Exception:
        return "ja"


def main():
    argv = list(sys.argv)
    if _under_wine():
        # Wine's DirectWrite font path can crash during Qt font
        # initialisation on some host colour fonts (observed as an
        # alternating launch crash correlated with the host emoji font
        # registration). The FreeType font engine avoids that path.
        # Real Windows never takes this branch.
        argv += ["-platform", "windows:fontengine=freetype"]
    app = QApplication(argv)
    try:
        import os as _os, sys as _sys
        from PySide6.QtGui import QIcon as _QIcon
        _ib = getattr(_sys, "_MEIPASS", None) or _os.path.dirname(_os.path.abspath(__file__))
        _ip = _os.path.join(_ib, "assets", "icon.png")
        if _os.path.exists(_ip):
            app.setWindowIcon(_QIcon(_ip))
    except Exception:
        pass
    app.setApplicationName(appinfo.APP_ID)
    app.setOrganizationName(appinfo.APP_ID)
    if _fonts_mod is not None and _theme_mod is not None:
        # Register the bundled fonts and set the UI font BEFORE any
        # widget exists: widgets resolve their font families when
        # first polished, and in the frozen build a later font change
        # does not re-resolve them (the Japanese-tofu bug pattern).
        _fonts_mod.register_fonts()
        _theme_mod.apply_theme(app)
        _fonts_mod.apply_language_font(app, _initial_lang())
        if _under_wine():
            try:
                # Only if the bundled fonts somehow failed to load,
                # fall back to one concrete system family (Wine's
                # fallback chain was the crash risk).
                from PySide6.QtGui import QFont, QFontDatabase
                families = set(QFontDatabase.families())
                if families and "Inter" not in families \
                        and "Noto Sans JP" not in families:
                    fallback = "Tahoma" if "Tahoma" in families \
                        else next(iter(families))
                    app.setFont(QFont(fallback, 10))
            except Exception:
                pass
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
