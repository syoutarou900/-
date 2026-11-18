# -*- coding: utf-8 -*-
"""TashikaMail (たしかめーる) - main window.

Pre-send checker for estimate / invoice emails. The app NEVER sends
mail: it checks the body + attachments the user drops in, shows traffic
lights (green / yellow / red) with reasons and evidence, and the human
decides whether to send from their own mail software.
"""
import json
import os
import sys

from PySide6.QtCore import QObject, QStandardPaths, Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFormLayout, QFrame,
    QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

import core
import core_checks
from appinfo import APP_ID, display_name
from i18n import LANG_NAMES, LANG_ORDER, RTL_LANGS, tr

COUNTRY_CODES = ["JP", "US", "GB", "DE", "FR", "CN", "KR", "ES", "IT",
                 "PT", "RU", "TR", "ID", "OTHER"]
LEVEL_COLORS = {"green": "#16a34a", "yellow": "#d97706", "red": "#dc2626"}
LEVEL_BG = {"green": "#dcfce7", "yellow": "#fef3c7", "red": "#fee2e2"}

STYLE = """
QMainWindow { background: #eef4fb; }
QLabel { color: #1e293b; }
QPushButton {
    background: #ffffff; border: 1.5px solid #cbd5e1; border-radius: 9px;
    padding: 7px 13px; font-weight: 600; color: #1e3a5f;
}
QPushButton:hover { background: #e0f2fe; border-color: #38bdf8; }
QPushButton:pressed { background: #bae6fd; }
QPushButton#checkButton {
    background: #2563eb; color: #ffffff; border: none; font-size: 15px;
    padding: 10px 22px; border-radius: 11px;
}
QPushButton#checkButton:hover { background: #1d4ed8; }
QLineEdit, QPlainTextEdit, QListWidget {
    background: #ffffff; border: 1.5px solid #cbd5e1; border-radius: 7px;
    padding: 5px 8px;
}
QLineEdit:focus, QPlainTextEdit:focus { border-color: #2563eb; }
QComboBox {
    background: #ffffff; border: 1.5px solid #cbd5e1; border-radius: 8px;
    padding: 4px 8px; font-weight: 600;
}
QScrollBar:vertical { background: #e2e8f0; width: 12px; border-radius: 6px; }
QScrollBar::handle:vertical { background: #94a3b8; border-radius: 6px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #64748b; }
QScrollBar:horizontal { background: #e2e8f0; height: 12px; border-radius: 6px; }
QScrollBar::handle:horizontal { background: #94a3b8; border-radius: 6px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QTableWidget { background: #ffffff; border: 1px solid #e2e8f0; gridline-color: #eef2f7; }
QHeaderView::section { background: #e0eaff; padding: 5px; border: none; font-weight: 700; }
"""


def app_data_dir():
    base = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation)
    if not base:
        base = os.path.join(os.path.expanduser("~"), "." + APP_ID.lower())
    os.makedirs(base, exist_ok=True)
    return base


def shadow(widget, blur=14, y=3, alpha=55):
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(0, y)
    eff.setColor(QColor(30, 41, 59, alpha))
    widget.setGraphicsEffect(eff)
    return widget


def card(title_key=None):
    frame = QFrame()
    frame.setStyleSheet(
        "QFrame { background: #ffffff; border-radius: 12px; }")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(12, 10, 12, 12)
    lay.setSpacing(8)
    title = None
    if title_key:
        title = QLabel()
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #1e3a5f;")
        lay.addWidget(title)
    return frame, lay, title


class _CheckWorker(QObject):
    """Runs attachment reading (incl. OCR) + checks off the UI thread,
    so OCR processing never freezes the window."""

    progress = Signal(str)
    finished = Signal(object, list)

    def __init__(self, inp, lang):
        super().__init__()
        self.inp = inp
        self.lang = lang

    def run(self):
        fresh = []
        for att in self.inp.attachments:
            self.progress.emit(att.name)
            fresh.append(core.read_attachment(att.path, att.name,
                                              ui_lang=self.lang))
        self.inp.attachments = fresh
        report = core_checks.run_checks(self.inp)
        self.finished.emit(report, fresh)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.lang = "ja"
        self.country = "JP"
        self.attachments = []          # list[core.Attachment]
        self.report = None
        self._check_thread = None
        self._load_settings()
        self.setStyleSheet(STYLE)
        self.setAcceptDrops(True)
        self._build_ui()
        self.apply_language(self.lang)
        self.resize(1180, 800)

    # ---------------------------------------------------------- settings
    def _settings_path(self):
        return os.path.join(app_data_dir(), "settings.json")

    def _load_settings(self):
        try:
            with open(self._settings_path(), encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("lang") in LANG_ORDER:
                self.lang = data["lang"]
            if data.get("country") in COUNTRY_CODES:
                self.country = data["country"]
        except Exception:
            pass

    def _save_settings(self):
        try:
            with open(self._settings_path(), "w", encoding="utf-8") as fh:
                json.dump({"lang": self.lang, "country": self.country}, fh)
        except Exception:
            pass

    # ---------------------------------------------------------- UI build
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        main = QVBoxLayout(root)
        main.setContentsMargins(10, 10, 10, 8)
        main.setSpacing(10)

        # header
        header = QFrame()
        header.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            " stop:0 #1d4ed8, stop:1 #0ea5e9); border-radius: 12px; }")
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(16, 10, 16, 10)
        title_box = QVBoxLayout()
        self.title_label = QLabel()
        self.title_label.setStyleSheet(
            "color: #ffffff; font-size: 24px; font-weight: 800;")
        self.subtitle_label = QLabel()
        self.subtitle_label.setStyleSheet("color: #dbeafe; font-size: 12px;")
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)
        hlay.addLayout(title_box)
        hlay.addStretch(1)
        self.lang_label = QLabel()
        self.lang_label.setStyleSheet("color: #ffffff; font-weight: 700;")
        hlay.addWidget(self.lang_label)
        self.lang_combo = QComboBox()
        for code in LANG_ORDER:
            self.lang_combo.addItem(LANG_NAMES[code], code)
        self.lang_combo.setCurrentIndex(LANG_ORDER.index(self.lang))
        self.lang_combo.currentIndexChanged.connect(
            lambda i: self.apply_language(self.lang_combo.itemData(i)))
        hlay.addWidget(self.lang_combo)
        shadow(header)
        main.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ----- left: inputs -----
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left = QWidget()
        llay = QVBoxLayout(left)
        llay.setContentsMargins(0, 0, 4, 0)
        llay.setSpacing(10)

        in_card, in_lay, self.in_title = card("hdr_input")
        form = QFormLayout()
        form.setSpacing(7)
        self.to_edit = QLineEdit()
        self.subject_edit = QLineEdit()
        self.country_combo = QComboBox()
        for code in COUNTRY_CODES:
            self.country_combo.addItem(code, code)
        self.country_combo.setCurrentIndex(COUNTRY_CODES.index(self.country))
        self.country_combo.currentIndexChanged.connect(self._country_changed)
        self.lbl_to = QLabel()
        self.lbl_subject = QLabel()
        self.lbl_country = QLabel()
        form.addRow(self.lbl_to, self.to_edit)
        form.addRow(self.lbl_subject, self.subject_edit)
        form.addRow(self.lbl_country, self.country_combo)
        in_lay.addLayout(form)
        self.lbl_body = QLabel()
        in_lay.addWidget(self.lbl_body)
        self.body_edit = QPlainTextEdit()
        self.body_edit.setMinimumHeight(150)
        in_lay.addWidget(self.body_edit)
        btn_row = QHBoxLayout()
        self.btn_open_body = QPushButton()
        self.btn_open_body.clicked.connect(self.open_body_file)
        self.btn_clear = QPushButton()
        self.btn_clear.clicked.connect(self.clear_all)
        btn_row.addWidget(self.btn_open_body)
        btn_row.addWidget(self.btn_clear)
        btn_row.addStretch(1)
        in_lay.addLayout(btn_row)
        self.drop_hint = QLabel()
        self.drop_hint.setWordWrap(True)
        self.drop_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        in_lay.addWidget(self.drop_hint)
        shadow(in_card)
        llay.addWidget(in_card)

        att_card, att_lay, self.att_title = card("hdr_attach")
        self.att_list = QListWidget()
        self.att_list.setMinimumHeight(90)
        att_lay.addWidget(self.att_list)
        att_btns = QHBoxLayout()
        self.btn_add_files = QPushButton()
        self.btn_add_files.clicked.connect(self.add_files_dialog)
        self.btn_remove_file = QPushButton()
        self.btn_remove_file.clicked.connect(self.remove_selected_files)
        self.att_count_label = QLabel()
        att_btns.addWidget(self.btn_add_files)
        att_btns.addWidget(self.btn_remove_file)
        att_btns.addStretch(1)
        att_btns.addWidget(self.att_count_label)
        att_lay.addLayout(att_btns)
        shadow(att_card)
        llay.addWidget(att_card)

        exp_card, exp_lay, self.exp_title = card("hdr_expected")
        self.exp_hint = QLabel()
        self.exp_hint.setWordWrap(True)
        self.exp_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        exp_lay.addWidget(self.exp_hint)
        eform = QFormLayout()
        eform.setSpacing(7)
        self.exp_company = QLineEdit()
        self.exp_domain = QLineEdit()
        self.exp_amount = QLineEdit()
        self.exp_date = QLineEdit()
        self.exp_docnum = QLineEdit()
        self.lbl_exp_company = QLabel()
        self.lbl_exp_domain = QLabel()
        self.lbl_exp_amount = QLabel()
        self.lbl_exp_date = QLabel()
        self.lbl_exp_docnum = QLabel()
        eform.addRow(self.lbl_exp_company, self.exp_company)
        eform.addRow(self.lbl_exp_domain, self.exp_domain)
        eform.addRow(self.lbl_exp_amount, self.exp_amount)
        eform.addRow(self.lbl_exp_date, self.exp_date)
        eform.addRow(self.lbl_exp_docnum, self.exp_docnum)
        exp_lay.addLayout(eform)
        shadow(exp_card)
        llay.addWidget(exp_card)
        llay.addStretch(1)
        left_scroll.setWidget(left)
        splitter.addWidget(left_scroll)

        # ----- right: results -----
        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(4, 0, 0, 0)
        rlay.setSpacing(10)
        res_card, res_lay, self.res_title = card("hdr_results")
        self.overall_label = QLabel()
        self.overall_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overall_label.setStyleSheet(
            "font-size: 22px; font-weight: 800; padding: 12px;"
            " border-radius: 10px; background: #e2e8f0; color: #334155;")
        res_lay.addWidget(self.overall_label)
        self.overall_hint = QLabel()
        self.overall_hint.setWordWrap(True)
        self.overall_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        res_lay.addWidget(self.overall_hint)
        self.btn_check = QPushButton()
        self.btn_check.setObjectName("checkButton")
        self.btn_check.clicked.connect(self.run_check)
        res_lay.addWidget(self.btn_check)
        self.progress_label = QLabel()
        self.progress_label.setWordWrap(True)
        self.progress_label.setStyleSheet("color: #475569; font-size: 12px;")
        res_lay.addWidget(self.progress_label)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["", "", "", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(True)
        self.table.horizontalHeader().setStretchLastSection(False)
        from PySide6.QtWidgets import QHeaderView
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        res_lay.addWidget(self.table)
        self.suggest_label = QLabel()
        self.suggest_label.setWordWrap(True)
        self.suggest_label.setStyleSheet("color: #92400e; font-size: 12px;")
        res_lay.addWidget(self.suggest_label)
        self.btn_export = QPushButton()
        self.btn_export.clicked.connect(self.export_renamed)
        self.btn_export.setEnabled(False)
        res_lay.addWidget(self.btn_export)
        shadow(res_card)
        rlay.addWidget(res_card)
        splitter.addWidget(right)
        splitter.setSizes([520, 660])
        main.addWidget(splitter, 1)

        self.footer_label = QLabel()
        self.footer_label.setWordWrap(True)
        self.footer_label.setStyleSheet("color: #64748b; font-size: 11px;")
        main.addWidget(self.footer_label)

    # ---------------------------------------------------------- language
    def apply_language(self, lang):
        if lang not in LANG_ORDER:
            lang = "en"
        self.lang = lang
        self._save_settings()
        idx = LANG_ORDER.index(lang)
        if self.lang_combo.currentIndex() != idx:
            self.lang_combo.blockSignals(True)
            self.lang_combo.setCurrentIndex(idx)
            self.lang_combo.blockSignals(False)
        rtl = lang in RTL_LANGS
        self.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if rtl
            else Qt.LayoutDirection.LeftToRight)
        t = lambda k, **p: tr(lang, k, **p)
        name = display_name(lang)
        self.setWindowTitle(name)
        self.title_label.setText(f"🛡️ {name}")
        self.subtitle_label.setText(t("app_subtitle"))
        self.lang_label.setText(t("lang_label"))
        self.in_title.setText(t("hdr_input"))
        self.att_title.setText(t("hdr_attach"))
        self.exp_title.setText(t("hdr_expected"))
        self.res_title.setText(t("hdr_results"))
        self.lbl_to.setText(t("lbl_to"))
        self.lbl_subject.setText(t("lbl_subject"))
        self.lbl_body.setText(t("lbl_body"))
        self.lbl_country.setText(t("lbl_country"))
        self.to_edit.setPlaceholderText(t("ph_to"))
        self.btn_open_body.setText(t("btn_open_body"))
        self.btn_clear.setText(t("btn_clear"))
        self.btn_add_files.setText(t("btn_add_files"))
        self.btn_remove_file.setText(t("btn_remove_file"))
        self.btn_check.setText(t("btn_check"))
        self.btn_export.setText(t("btn_export_rename"))
        self.drop_hint.setText(t("drop_hint"))
        self.exp_hint.setText(t("expected_hint"))
        self.lbl_exp_company.setText(t("lbl_exp_company"))
        self.lbl_exp_domain.setText(t("lbl_exp_domain"))
        self.lbl_exp_amount.setText(t("lbl_exp_amount"))
        self.lbl_exp_date.setText(t("lbl_exp_date"))
        self.lbl_exp_docnum.setText(t("lbl_exp_docnum"))
        footer = t("footer_note")
        if sys.platform == "darwin" and not core.ocr_available():
            # macOS only: the bundled Tesseract is a Windows binary, so
            # OCR depends on a Homebrew install. When it is missing,
            # say so (with the install command) instead of letting
            # images simply come back "unreadable". On Windows this
            # branch is never taken and the footer is unchanged.
            footer += "\n" + t("ocr_mac_missing")
        self.footer_label.setText(footer)
        for i, code in enumerate(COUNTRY_CODES):
            self.country_combo.setItemText(i, t(f"c_{code}"))
        self.table.setHorizontalHeaderLabels(
            [t("col_level"), t("col_check"), t("col_reason"),
             t("col_evidence")])
        self._refresh_att_list()
        if self.report is not None:
            self._show_report(self.report)
        else:
            self.overall_label.setText(t("overall_none"))
            self.overall_hint.setText("")

    def _country_changed(self, i):
        self.country = self.country_combo.itemData(i)
        self._save_settings()

    # ---------------------------------------------------------- input handling
    def _refresh_att_list(self):
        self.att_list.clear()
        for att in self.attachments:
            label = f"📎 {att.name}"
            if att.via_ocr:
                label += tr(self.lang, "ocr_badge")
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, att.path)
            self.att_list.addItem(item)
        if self.attachments:
            self.att_count_label.setText(
                tr(self.lang, "att_count", count=len(self.attachments)))
        else:
            self.att_count_label.setText(tr(self.lang, "att_none"))

    def add_attachment_paths(self, paths):
        for path in paths:
            if os.path.isdir(path):
                continue
            self.attachments.append(
                core.read_attachment(path, ui_lang=self.lang))
        self._refresh_att_list()

    def load_eml(self, path):
        out_dir = os.path.join(app_data_dir(), "eml_parts")
        data = core.parse_eml(path, keep_attachments=True, out_dir=out_dir)
        recipients = ", ".join(data["recipients"])
        if recipients:
            self.to_edit.setText(recipients)
        if data["subject"]:
            self.subject_edit.setText(data["subject"])
        if data["body"]:
            self.body_edit.setPlainText(data["body"])
        for part in data["attachments"]:
            self.attachments.append(
                core.read_attachment(part["path"], part["name"],
                                     ui_lang=self.lang))
        self._refresh_att_list()

    def load_body_file(self, path):
        if path.lower().endswith(".eml"):
            self.load_eml(path)
            return
        try:
            with open(path, "rb") as fh:
                text = core._decode_bytes(fh.read())
            self.body_edit.setPlainText(text)
        except Exception:
            pass

    def handle_dropped(self, paths):
        for path in paths:
            low = path.lower()
            if low.endswith(".eml"):
                self.load_eml(path)
            elif low.endswith(".txt") and not self.attachments \
                    and not self.body_edit.toPlainText().strip():
                self.load_body_file(path)
            else:
                self.add_attachment_paths([path])

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls()
                 if u.isLocalFile()]
        if paths:
            self.handle_dropped(paths)
        event.acceptProposedAction()

    def open_body_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr(self.lang, "dlg_open_body"), "",
            tr(self.lang, "filter_files"))
        if path:
            self.load_body_file(path)

    def add_files_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr(self.lang, "dlg_open_att"), "",
            tr(self.lang, "filter_files"))
        if paths:
            self.handle_dropped(paths)

    def remove_selected_files(self):
        rows = sorted({i.row() for i in self.att_list.selectedIndexes()},
                      reverse=True)
        for r in rows:
            if 0 <= r < len(self.attachments):
                del self.attachments[r]
        self._refresh_att_list()

    def clear_all(self):
        self.to_edit.clear()
        self.subject_edit.clear()
        self.body_edit.clear()
        self.exp_company.clear()
        self.exp_domain.clear()
        self.exp_amount.clear()
        self.exp_date.clear()
        self.exp_docnum.clear()
        self.attachments = []
        self.report = None
        self.table.setRowCount(0)
        self.suggest_label.setText("")
        self.btn_export.setEnabled(False)
        self._refresh_att_list()
        self.apply_language(self.lang)

    # ---------------------------------------------------------- checking
    def build_input(self):
        return core_checks.CheckInput(
            recipients_text=self.to_edit.text(),
            subject=self.subject_edit.text(),
            body=self.body_edit.toPlainText(),
            attachments=list(self.attachments),
            expected_company=self.exp_company.text(),
            expected_domain=self.exp_domain.text(),
            expected_amount=self.exp_amount.text(),
            expected_date=self.exp_date.text(),
            expected_docnum=self.exp_docnum.text(),
            country=self.country,
            labels={"body": tr(self.lang, "body_label"),
                    "att": tr(self.lang, "att_label")},
        )

    def run_check(self):
        if getattr(self, "_check_thread", None) is not None:
            return  # a check is already running
        self.btn_check.setEnabled(False)
        self.progress_label.setText(tr(self.lang, "progress_checking"))
        worker = _CheckWorker(self.build_input(), self.lang)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(
            lambda name: self.progress_label.setText(
                tr(self.lang, "progress_reading", file=name)))
        worker.finished.connect(self._finish_check)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(
            lambda: setattr(self, "_check_thread", None))
        self._check_thread = thread
        self._check_worker = worker
        thread.start()

    def _finish_check(self, report, attachments):
        self.attachments = attachments
        self._refresh_att_list()
        self.report = report
        self._show_report(report)
        self.progress_label.setText("")
        self.btn_check.setEnabled(True)

    def _show_report(self, report):
        lang = self.lang
        overall_key = {"green": "overall_green", "yellow": "overall_yellow",
                       "red": "overall_red"}[report.overall]
        self.overall_label.setText(tr(lang, overall_key))
        self.overall_label.setStyleSheet(
            "font-size: 22px; font-weight: 800; padding: 12px;"
            " border-radius: 10px;"
            f" background: {LEVEL_BG[report.overall]};"
            f" color: {LEVEL_COLORS[report.overall]};")
        self.overall_hint.setText(
            tr(lang, f"overall_hint_{report.overall}"))
        self.table.setRowCount(0)
        for f in report.findings:
            row = self.table.rowCount()
            self.table.insertRow(row)
            lvl = QTableWidgetItem(tr(lang, f"level_{f.level}"))
            lvl.setForeground(QColor(LEVEL_COLORS[f.level]))
            font = lvl.font()
            font.setBold(True)
            lvl.setFont(font)
            reason_params = dict(f.params)
            reason = tr(lang, f.reason_key, **reason_params) \
                if reason_params else tr(lang, f.reason_key)
            items = [lvl,
                     QTableWidgetItem(tr(lang, f"chk_{f.check}")),
                     QTableWidgetItem(reason),
                     QTableWidgetItem(f.evidence)]
            for col, item in enumerate(items):
                item.setBackground(QColor(LEVEL_BG[f.level]))
                self.table.setItem(row, col, item)
            self.table.setRowHeight(row, 44)
        if report.rename_suggestions:
            lines = [tr(lang, "lbl_suggestions")]
            by_path = {a.path: a.name for a in self.attachments}
            for path, new_name in report.rename_suggestions.items():
                lines.append(f"• {by_path.get(path, path)}  →  {new_name}")
            self.suggest_label.setText("\n".join(lines))
            self.btn_export.setEnabled(True)
        else:
            self.suggest_label.setText("")
            self.btn_export.setEnabled(False)

    def export_renamed(self):
        if not self.report or not self.report.rename_suggestions:
            return
        out_dir = QFileDialog.getExistingDirectory(
            self, tr(self.lang, "dlg_export"))
        if not out_dir:
            return
        written = core_checks.export_renamed_copies(
            self.report.rename_suggestions, self.attachments, out_dir)
        QMessageBox.information(
            self, display_name(self.lang),
            tr(self.lang, "msg_exported", count=len(written)))


def _under_wine():
    """True only under Wine (ntdll exports wine_get_version only there).
    Used solely for Wine-only stability workarounds; real Windows is
    untouched. Non-Windows platforms (macOS, Linux) return False at
    once - ctypes.WinDLL does not exist there."""
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
        # Wine 9.0 during font fallback, crashing the app intermittently
        # at startup (page fault in Qt6Core's UTF-16 scan via the font
        # engine). The FreeType engine avoids that path.
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
    if _under_wine():
        try:
            # Only when the usual Windows UI fonts are absent (e.g.
            # Wine): fall back to an installed family so font fallback
            # cannot crash.
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
