# -*- coding: utf-8 -*-
"""TranscribeGuard (転記見守り君) - main window.

Semi-automatic by design: the app decomposes the source, watches the
person's typing with live checks, and prepares the result. It never sends
or registers anything; the final transfer is done by the person.
"""
import csv
import json
import os
import sys

from PySide6.QtCore import Qt, QTimer, QStandardPaths, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QScrollArea, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QGraphicsDropShadowEffect,
    QDialogButtonBox, QFormLayout,
)

import core
from i18n import LANG_NAMES, LANG_ORDER, RTL_LANGS, tr

APP_NAME = "TranscribeGuard"


def app_data_dir():
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".transcribe-guard")
    os.makedirs(base, exist_ok=True)
    return base


STYLE = """
QMainWindow { background: #eef4fb; }
QLabel { color: #1e293b; }
QPushButton {
    background: #ffffff; border: 1.5px solid #cbd5e1; border-radius: 9px;
    padding: 7px 13px; font-weight: 600; color: #1e3a5f;
}
QPushButton:hover { background: #e0f2fe; border-color: #38bdf8; }
QPushButton:pressed { background: #bae6fd; }
QLineEdit {
    background: #ffffff; border: 1.5px solid #cbd5e1; border-radius: 7px; padding: 5px 8px;
}
QLineEdit:focus { border-color: #2563eb; }
QScrollBar:vertical { background: #e2e8f0; width: 12px; border-radius: 6px; }
QScrollBar::handle:vertical { background: #94a3b8; border-radius: 6px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #64748b; }
QScrollBar:horizontal { background: #e2e8f0; height: 12px; border-radius: 6px; }
QScrollBar::handle:horizontal { background: #94a3b8; border-radius: 6px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QComboBox {
    background: #ffffff; border: 1.5px solid rgba(255,255,255,.7); border-radius: 8px;
    padding: 4px 8px; font-weight: 600;
}
QProgressBar {
    background: rgba(255,255,255,.35); border: none; border-radius: 7px; height: 14px;
    text-align: center; color: #ffffff; font-size: 10px; font-weight: 700;
}
QProgressBar::chunk { background: #4ade80; border-radius: 7px; }
QTableWidget { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; gridline-color: #eef2f7; }
QHeaderView::section { background: #e0eaff; padding: 5px; border: none; font-weight: 700; }
"""


class ClickLabel(QLabel):
    doubleClicked = Signal()

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)


def shadow(widget, blur=14, y=3, alpha=55):
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(0, y)
    eff.setColor(QColor(30, 41, 59, alpha))
    widget.setGraphicsEffect(eff)
    return widget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.lang = "ja"
        self.items = []
        self.inputs = []
        self.source_name = ""
        self.rows = []          # per-item widget refs, in item order
        self._syncing = False
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(700)
        self._autosave_timer.timeout.connect(self.autosave)

        self._load_settings()
        self.setStyleSheet(STYLE)
        self._build_ui()
        self.apply_language(self.lang, rebuild=False)
        self._restore_autosave()
        self.update_all()

    # ------------------------------------------------------------ settings
    def _settings_path(self):
        return os.path.join(app_data_dir(), "settings.json")

    def _load_settings(self):
        try:
            with open(self._settings_path(), encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("lang") in LANG_ORDER:
                self.lang = data["lang"]
        except Exception:
            pass

    def _save_settings(self):
        try:
            with open(self._settings_path(), "w", encoding="utf-8") as fh:
                json.dump({"lang": self.lang}, fh, ensure_ascii=False)
        except Exception:
            pass

    def autosave(self):
        try:
            path = os.path.join(app_data_dir(), "autosave.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(core.session_dict(self.items, self.current_inputs(), self.lang, self.source_name),
                          fh, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def _restore_autosave(self):
        path = os.path.join(app_data_dir(), "autosave.json")
        if not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            items, inputs, _lang, name = core.session_from_dict(data)
            if items:
                self.items, self.inputs, self.source_name = items, inputs, name
                self.rebuild_panels()
        except Exception:
            pass

    def current_inputs(self):
        if self.rows and len(self.rows) == len(self.items):
            return [r["edit"].text() for r in self.rows]
        return list(self.inputs) + [""] * (len(self.items) - len(self.inputs))

    def t(self, key, **kw):
        return tr(self.lang, key, **kw)

    # ------------------------------------------------------------ UI build
    def _build_ui(self):
        self.setMinimumSize(1020, 680)
        self.resize(1200, 780)
        self.setAcceptDrops(True)
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 8)
        root.setSpacing(8)

        # header
        header = QFrame()
        header.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            " stop:0 #1d4ed8, stop:.55 #2563eb, stop:1 #06b6d4); border-radius: 14px; }")
        shadow(header, blur=18, y=4, alpha=70)
        hv = QVBoxLayout(header)
        hv.setContentsMargins(16, 12, 16, 12)
        hv.setSpacing(7)
        top = QHBoxLayout()
        title_box = QVBoxLayout()
        self.title_label = QLabel()
        self.title_label.setStyleSheet("color: white; font-size: 22px; font-weight: 800;")
        self.subtitle_label = QLabel()
        self.subtitle_label.setStyleSheet("color: #dbeafe; font-size: 12px;")
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)
        top.addLayout(title_box)
        top.addStretch(1)
        self.lang_label = QLabel()
        self.lang_label.setStyleSheet("color: white; font-weight: 700;")
        top.addWidget(self.lang_label)
        self.lang_combo = QComboBox()
        for code in LANG_ORDER:
            self.lang_combo.addItem(LANG_NAMES[code], code)
        self.lang_combo.setCurrentIndex(LANG_ORDER.index(self.lang))
        self.lang_combo.currentIndexChanged.connect(
            lambda i: self.apply_language(self.lang_combo.itemData(i)))
        top.addWidget(self.lang_combo)
        hv.addLayout(top)

        stats = QHBoxLayout()
        stats.setSpacing(8)
        self.stat_labels = {}
        for key in ("stat_total", "stat_done", "stat_remaining", "stat_mismatch"):
            lab = QLabel()
            lab.setStyleSheet(
                "background: rgba(255,255,255,.92); border-radius: 9px; padding: 5px 12px;"
                " font-weight: 800; color: #1e3a5f; font-size: 13px;")
            if key == "stat_remaining":
                lab.setStyleSheet(
                    "background: #fef08a; border-radius: 9px; padding: 5px 12px;"
                    " font-weight: 800; color: #713f12; font-size: 13px;")
            self.stat_labels[key] = lab
            stats.addWidget(lab)
        stats.addStretch(1)
        hv.addLayout(stats)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        hv.addWidget(self.progress)
        root.addWidget(header)

        self.banner = QLabel()
        self.banner.setStyleSheet(
            "background: #dcfce7; color: #166534; border: 1.5px solid #4ade80;"
            " border-radius: 10px; padding: 8px 12px; font-weight: 800; font-size: 14px;")
        self.banner.hide()
        root.addWidget(self.banner)

        self.ocr_bar = QLabel()
        self.ocr_bar.setWordWrap(True)
        self.ocr_bar.setStyleSheet(
            "background: #fef9c3; color: #854d0e; border: 1.5px solid #facc15;"
            " border-radius: 10px; padding: 8px 12px; font-weight: 600;")
        self.ocr_bar.hide()
        root.addWidget(self.ocr_bar)

        # toolbar
        bar = QHBoxLayout()
        bar.setSpacing(7)
        self.btn_open = QPushButton()
        self.btn_open.clicked.connect(self.open_file)
        self.btn_sample = QPushButton()
        self.btn_sample.clicked.connect(lambda: self.load_items(core.sample_items(), "sample"))
        self.btn_paste = QPushButton()
        self.btn_paste.clicked.connect(self.paste_text)
        self.btn_add = QPushButton()
        self.btn_add.clicked.connect(self.add_item_dialog)
        self.btn_clear = QPushButton()
        self.btn_clear.clicked.connect(self.clear_inputs)
        for b in (self.btn_open, self.btn_sample, self.btn_paste, self.btn_add, self.btn_clear):
            bar.addWidget(b)
        bar.addStretch(1)
        self.btn_copy = QPushButton()
        self.btn_copy.clicked.connect(self.copy_tsv)
        self.btn_xlsx = QPushButton()
        self.btn_xlsx.clicked.connect(self.save_xlsx)
        self.btn_csv = QPushButton()
        self.btn_csv.clicked.connect(self.save_csv)
        self.btn_sess_save = QPushButton()
        self.btn_sess_save.clicked.connect(self.save_session)
        self.btn_sess_load = QPushButton()
        self.btn_sess_load.clicked.connect(self.load_session)
        for b in (self.btn_copy, self.btn_xlsx, self.btn_csv, self.btn_sess_save, self.btn_sess_load):
            bar.addWidget(b)
        root.addLayout(bar)

        self.drop_hint = QLabel()
        self.drop_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        root.addWidget(self.drop_hint)

        titles = QHBoxLayout()
        self.left_title = QLabel()
        self.left_title.setStyleSheet("font-weight: 800; font-size: 13px; color: #1d4ed8;")
        self.right_title = QLabel()
        self.right_title.setStyleSheet("font-weight: 800; font-size: 13px; color: #1d4ed8;")
        titles.addWidget(self.left_title, 1)
        titles.addWidget(self.right_title, 1)
        root.addLayout(titles)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.left_scroll = QScrollArea()
        self.left_scroll.setWidgetResizable(True)
        self.right_scroll = QScrollArea()
        self.right_scroll.setWidgetResizable(True)
        for sc in (self.left_scroll, self.right_scroll):
            sc.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.left_content = QWidget()
        self.left_layout = QVBoxLayout(self.left_content)
        self.left_layout.setContentsMargins(2, 2, 6, 2)
        self.left_layout.setSpacing(8)
        self.left_scroll.setWidget(self.left_content)
        self.right_content = QWidget()
        self.right_layout = QVBoxLayout(self.right_content)
        self.right_layout.setContentsMargins(6, 2, 2, 2)
        self.right_layout.setSpacing(8)
        self.right_scroll.setWidget(self.right_content)
        splitter.addWidget(self.left_scroll)
        splitter.addWidget(self.right_scroll)
        splitter.setSizes([560, 560])
        root.addWidget(splitter, 1)
        self.left_scroll.verticalScrollBar().valueChanged.connect(
            lambda v: self._sync_scroll(self.right_scroll, v))
        self.right_scroll.verticalScrollBar().valueChanged.connect(
            lambda v: self._sync_scroll(self.left_scroll, v))

        # totals
        self.totals_title = QLabel()
        self.totals_title.setStyleSheet("font-weight: 800; font-size: 13px; color: #1d4ed8;")
        root.addWidget(self.totals_title)
        self.totals_table = QTableWidget(0, 3)
        self.totals_table.setMaximumHeight(128)
        self.totals_table.verticalHeader().setVisible(False)
        self.totals_table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.totals_table)

        self.footer = QLabel()
        self.footer.setWordWrap(True)
        self.footer.setStyleSheet("color: #475569; font-size: 11.5px; font-weight: 600;")
        root.addWidget(self.footer)

    def _sync_scroll(self, other, value):
        if self._syncing:
            return
        self._syncing = True
        other.verticalScrollBar().setValue(value)
        self._syncing = False

    # ------------------------------------------------------------ language
    def apply_language(self, lang, rebuild=True):
        if lang not in LANG_ORDER:
            lang = "ja"
        self.lang = lang
        self._save_settings()
        idx = LANG_ORDER.index(lang)
        if self.lang_combo.currentIndex() != idx:
            self.lang_combo.blockSignals(True)
            self.lang_combo.setCurrentIndex(idx)
            self.lang_combo.blockSignals(False)
        direction = Qt.LayoutDirection.RightToLeft if lang in RTL_LANGS else Qt.LayoutDirection.LeftToRight
        QApplication.instance().setLayoutDirection(direction)
        self.setWindowTitle(self.t("app_title") + " — TranscribeGuard")
        self.title_label.setText(self.t("app_title"))
        self.subtitle_label.setText(self.t("app_subtitle"))
        self.lang_label.setText(self.t("lang_label"))
        self.btn_open.setText(self.t("btn_open"))
        self.btn_sample.setText(self.t("btn_sample"))
        self.btn_paste.setText(self.t("btn_paste"))
        self.btn_add.setText(self.t("btn_add"))
        self.btn_clear.setText(self.t("btn_clear_inputs"))
        self.btn_copy.setText(self.t("btn_copy_tsv"))
        self.btn_xlsx.setText(self.t("btn_save_xlsx"))
        self.btn_csv.setText(self.t("btn_save_csv"))
        self.btn_sess_save.setText(self.t("btn_save_session"))
        self.btn_sess_load.setText(self.t("btn_load_session"))
        self.drop_hint.setText(self.t("drop_hint"))
        self.left_title.setText(self.t("left_title"))
        self.right_title.setText(self.t("right_title"))
        self.totals_title.setText(self.t("totals_title"))
        self.footer.setText(self.t("footer_note"))
        self.banner.setText(self.t("completion"))
        if rebuild:
            self.rebuild_panels()
        self.update_all()

    # ------------------------------------------------------------ panels
    def _clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            w = child.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
            elif child.layout() is not None:
                self._clear_layout(child.layout())

    def rebuild_panels(self):
        # keep current typed values before rebuilding widgets
        if self.rows and len(self.rows) == len(self.items):
            self.inputs = self.current_inputs()
        self._clear_layout(self.left_layout)
        self._clear_layout(self.right_layout)
        self.rows = []
        if not self.items:
            lab = QLabel(self.t("empty_left"))
            lab.setWordWrap(True)
            lab.setStyleSheet("color: #64748b; font-size: 13px; padding: 14px;")
            self.left_layout.addWidget(lab)
            self.left_layout.addStretch(1)
            self.right_layout.addStretch(1)
            return
        groups = []
        for idx, it in enumerate(self.items):
            if not groups or groups[-1][0] != it["group"]:
                groups.append((it["group"], []))
            groups[-1][1].append(idx)
        for gname, members in groups:
            left_card = self._group_card(self.left_layout, gname)
            right_card = self._group_card(self.right_layout, gname)
            for idx in members:
                it = self.items[idx]
                self._build_left_row(left_card, idx, it)
                self._build_right_row(right_card, idx, it)
        self.left_layout.addStretch(1)
        self.right_layout.addStretch(1)
        for idx, row in enumerate(self.rows):
            row["edit"].setText(self.inputs[idx] if idx < len(self.inputs) else "")
        self.update_all()

    def _group_card(self, parent_layout, gname):
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #ffffff; border: 1px solid #dbe7f5; border-radius: 12px; }")
        shadow(card, blur=10, y=2, alpha=35)
        v = QVBoxLayout(card)
        v.setContentsMargins(10, 7, 10, 9)
        v.setSpacing(4)
        head = QLabel(gname if gname else "―")
        head.setFixedHeight(24)
        head.setStyleSheet("font-weight: 800; font-size: 13.5px; color: #1d4ed8;")
        v.addWidget(head)
        parent_layout.addWidget(card)
        return v

    def _build_left_row(self, layout, idx, it):
        row = QWidget()
        row.setFixedHeight(54)
        h = QHBoxLayout(row)
        h.setContentsMargins(2, 2, 2, 2)
        h.setSpacing(6)
        field = QLabel(it["field"])
        field.setFixedWidth(92)
        field.setStyleSheet("color: #475569; font-weight: 700; font-size: 12px;")
        value = ClickLabel(it["value"])
        value.setStyleSheet("font-weight: 700; font-size: 13.5px; color: #0f172a;")
        value.setWordWrap(True)
        value.doubleClicked.connect(lambda i=idx: self.edit_source_value(i))
        check = QLabel("")
        check.setFixedWidth(22)
        check.setStyleSheet("font-size: 15px; font-weight: 800;")
        delete = QPushButton("✕")
        delete.setFixedSize(24, 24)
        delete.setToolTip(self.t("btn_delete"))
        delete.setStyleSheet("QPushButton { border: none; color: #94a3b8; padding: 0; }"
                             "QPushButton:hover { color: #dc2626; background: #fee2e2; }")
        delete.clicked.connect(lambda _=False, i=idx: self.delete_item(i))
        h.addWidget(field)
        h.addWidget(value, 1)
        h.addWidget(check)
        h.addWidget(delete)
        layout.addWidget(row)
        self.rows.append({"row_widget": row, "value_label": value, "check_label": check})

    def _build_right_row(self, layout, idx, it):
        row = QWidget()
        row.setFixedHeight(54)
        v = QVBoxLayout(row)
        v.setContentsMargins(2, 1, 2, 1)
        v.setSpacing(0)
        h = QHBoxLayout()
        h.setSpacing(6)
        field = QLabel(it["field"])
        field.setFixedWidth(92)
        field.setStyleSheet("color: #475569; font-weight: 700; font-size: 12px;")
        edit = QLineEdit()
        edit.setPlaceholderText(it["value"])
        edit.textChanged.connect(lambda _t, i=idx: self.on_input_changed(i))
        edit.installEventFilter(self)
        mark = QLabel("")
        mark.setFixedWidth(22)
        mark.setStyleSheet("font-size: 15px; font-weight: 800;")
        h.addWidget(field)
        h.addWidget(edit, 1)
        h.addWidget(mark)
        v.addLayout(h)
        reason = QLabel("")
        reason.setFixedHeight(15)
        reason.setStyleSheet("color: #dc2626; font-size: 10.5px; padding-left: 98px;")
        v.addWidget(reason)
        layout.addWidget(row)
        self.rows[idx].update({"edit": edit, "reason_label": reason, "mark_label": mark})

    # ------------------------------------------------------------ checking
    def on_input_changed(self, idx):
        self.check_row(idx)
        self.update_stats_totals()
        self._autosave_timer.start()

    def check_row(self, idx):
        if idx >= len(self.rows) or "edit" not in self.rows[idx]:
            return
        row = self.rows[idx]
        it = self.items[idx]
        typed = row["edit"].text()
        res = core.compare(it["value"], typed)
        st = res["status"]
        if st == "match":
            row["edit"].setStyleSheet(
                "QLineEdit { background: #dcfce7; border: 1.5px solid #22c55e; border-radius: 7px; padding: 5px 8px; }")
            row["mark_label"].setText("✓")
            row["mark_label"].setStyleSheet("color: #16a34a; font-size: 15px; font-weight: 800;")
            row["value_label"].setStyleSheet(
                "font-weight: 700; font-size: 13.5px; color: #b6bdc9; text-decoration: line-through;")
            row["check_label"].setText("✓")
            row["check_label"].setStyleSheet("color: #16a34a; font-size: 15px; font-weight: 800;")
            row["reason_label"].setText("")
            row["row_widget"].setStyleSheet("")
        elif st == "mismatch":
            row["edit"].setStyleSheet(
                "QLineEdit { background: #fee2e2; border: 1.5px solid #ef4444; border-radius: 7px; padding: 5px 8px; }")
            row["mark_label"].setText("✕")
            row["mark_label"].setStyleSheet("color: #dc2626; font-size: 15px; font-weight: 800;")
            row["value_label"].setStyleSheet(
                "font-weight: 800; font-size: 13.5px; color: #b91c1c;")
            row["check_label"].setText("✕")
            row["check_label"].setStyleSheet("color: #dc2626; font-size: 15px; font-weight: 800;")
            row["row_widget"].setStyleSheet("background: #fef2f2; border-radius: 8px;")
            if res["reason"] == "digits":
                row["reason_label"].setText(self.t("reason_digits", src=res["src_digits"], inp=res["in_digits"]))
            elif res["reason"] == "number":
                row["reason_label"].setText(self.t("reason_number", src=res["src_len"], inp=res["in_len"]))
            else:
                row["reason_label"].setText(self.t("reason_text", src=res["src_len"], inp=res["in_len"], pos=res["diff_pos"]))
        else:
            row["edit"].setStyleSheet("")
            row["mark_label"].setText("")
            row["value_label"].setStyleSheet("font-weight: 700; font-size: 13.5px; color: #0f172a;")
            row["check_label"].setText("")
            row["reason_label"].setText("")
            row["row_widget"].setStyleSheet("")

    def update_stats_totals(self):
        inputs = self.current_inputs()
        stats = core.compute_stats(self.items, inputs)
        self.stat_labels["stat_total"].setText(self.t("stat_total", count=stats["total"]))
        self.stat_labels["stat_done"].setText(self.t("stat_done", count=stats["done"]))
        self.stat_labels["stat_remaining"].setText(self.t("stat_remaining", count=stats["remaining"]))
        self.stat_labels["stat_mismatch"].setText(self.t("stat_mismatch", count=stats["mismatch"]))
        pct = int(stats["done"] * 100 / stats["total"]) if stats["total"] else 0
        self.progress.setValue(pct)
        self.banner.setVisible(bool(stats["total"]) and stats["remaining"] == 0 and stats["mismatch"] == 0)
        totals = core.field_totals(self.items, inputs)
        self.totals_table.setColumnCount(3)
        self.totals_table.setHorizontalHeaderLabels(
            [self.t("totals_field"), self.t("totals_source"), self.t("totals_typed")])
        self.totals_table.setRowCount(len(totals))
        for r, tot in enumerate(totals):
            vals = [tot["field"], core.fmt_num(tot["source_sum"]), core.fmt_num(tot["typed_sum"])]
            for c, val in enumerate(vals):
                item = QTableWidgetItem(val)
                bg = QColor("#dcfce7") if tot["match"] else QColor("#fee2e2")
                item.setBackground(bg)
                if c:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.totals_table.setItem(r, c, item)

    def update_all(self):
        for i in range(len(self.rows)):
            self.check_row(i)
        self.update_stats_totals()

    # ------------------------------------------------------------ actions
    def load_items(self, items, source_name=""):
        self.items = items
        self.inputs = [""] * len(items)
        self.source_name = source_name
        self.rebuild_panels()
        self.autosave()
        if self.rows and "edit" in self.rows[0]:
            self.rows[0]["edit"].setFocus()

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, self.t("open_title"), "", self.t("open_filter"))
        if path:
            self.load_path(path)

    def load_path(self, path):
        try:
            items, notice = core.extract_file(path, ui_lang=self.lang)
        except Exception as exc:
            QMessageBox.warning(self, self.t("app_title"), self.t("load_error", error=str(exc)))
            return
        if notice == "ocr_unavailable":
            self.ocr_bar.setText(self.t("ocr_notice"))
            self.ocr_bar.show()
        else:
            self.ocr_bar.hide()
        if not items:
            self.statusBar().showMessage(self.t("no_items_from_file"), 6000)
            if notice != "ocr_unavailable":
                return
        self.load_items(items, os.path.basename(path))

    def paste_text(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(self.t("paste_title"))
        v = QVBoxLayout(dlg)
        hint = QLabel(self.t("paste_hint"))
        hint.setWordWrap(True)
        v.addWidget(hint)
        edit = QPlainTextEdit()
        edit.setMinimumSize(480, 260)
        v.addWidget(edit)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        v.addWidget(box)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            items = core.extract_text(edit.toPlainText())
            if items:
                self.load_items(items, "paste")
            else:
                self.statusBar().showMessage(self.t("no_items_from_file"), 6000)

    def add_item_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(self.t("add_title"))
        form = QFormLayout(dlg)
        g = QLineEdit(self.items[-1]["group"] if self.items else "")
        f = QLineEdit()
        val = QLineEdit()
        form.addRow(self.t("add_group"), g)
        form.addRow(self.t("add_field"), f)
        form.addRow(self.t("add_value"), val)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        form.addRow(box)
        if dlg.exec() == QDialog.DialogCode.Accepted and (f.text().strip() or val.text().strip()):
            self.inputs = self.current_inputs()
            self.items.append({"group": g.text().strip(), "field": f.text().strip(), "value": val.text().strip()})
            self.inputs.append("")
            self.rebuild_panels()
            self.autosave()
            if self.rows:
                self.rows[-1]["edit"].setFocus()

    def delete_item(self, idx):
        self.inputs = self.current_inputs()
        del self.items[idx]
        del self.inputs[idx]
        self.rebuild_panels()
        self.autosave()

    def edit_source_value(self, idx):
        text, ok = QInputDialog.getText(self, self.t("edit_value_title"), self.t("edit_value_label"),
                                        text=self.items[idx]["value"])
        if ok:
            self.items[idx]["value"] = text.strip()
            self.rows[idx]["value_label"].setText(text.strip())
            self.rows[idx]["edit"].setPlaceholderText(text.strip())
            self.check_row(idx)
            self.update_stats_totals()
            self.autosave()

    def clear_inputs(self):
        for row in self.rows:
            if "edit" in row:
                row["edit"].clear()
        self.update_all()
        self.autosave()
        if self.rows and "edit" in self.rows[0]:
            self.rows[0]["edit"].setFocus()

    # ------------------------------------------------------------ export
    def copy_tsv(self):
        QApplication.clipboard().setText(core.build_tsv(self.items, self.current_inputs()))
        self.statusBar().showMessage(self.t("copied"), 4000)

    def save_xlsx(self):
        path, _ = QFileDialog.getSaveFileName(self, self.t("save_xlsx_title"),
                                              "TranscribeGuard-Result.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(["group", "field", "source", "input"])
        inputs = self.current_inputs()
        for i, it in enumerate(self.items):
            ws.append([it["group"], it["field"], it["value"], inputs[i] if i < len(inputs) else ""])
        wb.save(path)
        self.statusBar().showMessage(self.t("saved"), 4000)

    def save_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, self.t("save_csv_title"),
                                              "TranscribeGuard-Result.csv", "CSV (*.csv)")
        if not path:
            return
        inputs = self.current_inputs()
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["group", "field", "source", "input"])
            for i, it in enumerate(self.items):
                w.writerow([it["group"], it["field"], it["value"], inputs[i] if i < len(inputs) else ""])
        self.statusBar().showMessage(self.t("saved"), 4000)

    def save_session(self):
        path, _ = QFileDialog.getSaveFileName(self, self.t("save_session_title"),
                                              "TranscribeGuard-Session.json", "JSON (*.json)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(core.session_dict(self.items, self.current_inputs(), self.lang, self.source_name),
                      fh, ensure_ascii=False, indent=1)
        self.statusBar().showMessage(self.t("saved"), 4000)

    def load_session(self):
        path, _ = QFileDialog.getOpenFileName(self, self.t("load_session_title"), "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            items, inputs, _lang, name = core.session_from_dict(data)
        except Exception as exc:
            QMessageBox.warning(self, self.t("app_title"), self.t("load_error", error=str(exc)))
            return
        self.items, self.inputs, self.source_name = items, inputs, name
        self.rebuild_panels()

    # ------------------------------------------------------------ events
    def eventFilter(self, obj, event):
        if event.type() == event.Type.KeyPress and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            edits = [r["edit"] for r in self.rows if "edit" in r]
            if obj in edits:
                i = edits.index(obj)
                if i + 1 < len(edits):
                    edits[i + 1].setFocus()
                    edits[i + 1].selectAll()
                return True
        return super().eventFilter(obj, event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            self.load_path(urls[0].toLocalFile())


def _under_wine():
    """True only under Wine (ntdll exports wine_get_version only there).
    Used solely for Wine-only stability workarounds; real Windows is untouched."""
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
        # Wine 9.0 during font fallback for emoji glyphs, leaving the
        # window unpainted (black). The FreeType engine avoids that path.
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
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    if sys.platform == "win32":
        try:
            # Only when the usual Windows UI fonts are absent (e.g. Wine):
            # fall back to an installed family so font fallback cannot crash.
            # macOS keeps Qt's native default font and font selection.
            from PySide6.QtGui import QFont, QFontDatabase
            families = set(QFontDatabase.families())
            if families and "Yu Gothic UI" not in families and "Segoe UI" not in families:
                fallback = "Tahoma" if "Tahoma" in families else sorted(families)[0]
                app.setFont(QFont(fallback))
        except Exception:
            pass
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
