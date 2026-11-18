# -*- coding: utf-8 -*-
"""FormatPassport （フォーマットパスポート) - main window.

Semi-auto by design: the app prepares conversions and flags anything
readable two ways; the human decides. Originals are never modified.
"""
import json
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPushButton, QRadioButton, QScrollArea, QSplitter,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

import core
from countries import COUNTRIES, BY_CODE
from i18n import LANG_NAMES, LANG_ORDER, RTL_LANGS, tr

MAX_PREVIEW_ROWS = 300
STYLE = """
QMainWindow { background: #eef4fb; }
QFrame#header { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
  stop:0 #065f46, stop:.55 #059669, stop:1 #0ea5e9); border-radius: 14px; }
QFrame#card { background: white; border: 1px solid #dbe7f3; border-radius: 12px; }
QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ffffff, stop:1 #dbeafe);
  border: 1px solid #93c5fd; border-radius: 8px; padding: 6px 12px; font-weight: 600; }
QPushButton:hover { background: #bfdbfe; }
QPushButton#primary { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #34d399, stop:1 #059669);
  color: white; border: 1px solid #047857; }
QComboBox, QLineEdit { background: white; border: 1px solid #b6c9de; border-radius: 6px; padding: 4px 6px; }
QTableWidget { background: white; border: 1px solid #dbe7f3; }
QLabel#drop { border: 2px dashed #38bdf8; border-radius: 12px; color: #0369a1;
  background: #f0f9ff; padding: 14px; font-size: 14px; }
"""


class Signals(QObject):
    fx_ready = Signal(object, object)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.lang = "ja"
        self.sender_code = "DE"
        self.receiver_code = "JP"
        self.table = None
        self.result = None
        self.resolutions = {}
        self.fx_cache = core.load_fx_cache()
        self.signals = Signals()
        self.signals.fx_ready.connect(self._on_fx_ready)
        self._load_settings()
        self._build_ui()
        self.apply_language(self.lang, rebuild=False)
        self._update_fx_status()
        self._start_fx_fetch()

    # ------------------------------------------------------------ settings
    def _settings_path(self):
        return os.path.join(core.app_data_dir(), "settings.json")

    def _load_settings(self):
        try:
            with open(self._settings_path(), encoding="utf-8") as fh:
                d = json.load(fh)
            if d.get("lang") in LANG_ORDER:
                self.lang = d["lang"]
            if d.get("sender") in BY_CODE:
                self.sender_code = d["sender"]
            if d.get("receiver") in BY_CODE:
                self.receiver_code = d["receiver"]
        except Exception:
            pass

    def _save_settings(self):
        try:
            with open(self._settings_path(), "w", encoding="utf-8") as fh:
                json.dump({"lang": self.lang, "sender": self.sender_code,
                           "receiver": self.receiver_code}, fh, ensure_ascii=False)
        except Exception:
            pass

    def t(self, key, **kw):
        return tr(self.lang, key, **kw)

    # ------------------------------------------------------------ UI build
    def _build_ui(self):
        self.setStyleSheet(STYLE)
        self.resize(1240, 860)
        self.setAcceptDrops(True)
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        header = QFrame()
        header.setObjectName("header")
        hv = QVBoxLayout(header)
        top = QHBoxLayout()
        title_box = QVBoxLayout()
        self.title_label = QLabel()
        self.title_label.setStyleSheet("color: white; font-size: 22px; font-weight: 800;")
        self.subtitle_label = QLabel()
        self.subtitle_label.setStyleSheet("color: #d1fae5; font-size: 12px;")
        self.subtitle_label.setWordWrap(True)
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
        root.addWidget(header)

        # --- countries card
        card = QFrame(); card.setObjectName("card")
        cv = QVBoxLayout(card)
        row = QHBoxLayout()
        self.sender_label = QLabel()
        self.sender_combo = QComboBox()
        self.sender_combo.currentIndexChanged.connect(self._country_changed)
        row.addWidget(self.sender_label); row.addWidget(self.sender_combo, 1)
        self.sender_ccy = QLabel(); row.addWidget(self.sender_ccy)
        self.swap_btn = QPushButton()
        self.swap_btn.clicked.connect(self._swap)
        row.addWidget(self.swap_btn)
        self.receiver_label = QLabel()
        self.receiver_combo = QComboBox()
        self.receiver_combo.currentIndexChanged.connect(self._country_changed)
        row.addWidget(self.receiver_label); row.addWidget(self.receiver_combo, 1)
        self.receiver_ccy = QLabel(); row.addWidget(self.receiver_ccy)
        cv.addLayout(row)
        row2 = QHBoxLayout()
        self.open_btn = QPushButton()
        self.open_btn.clicked.connect(self._open_file)
        row2.addWidget(self.open_btn)
        self.drop_label = QLabel()
        self.drop_label.setObjectName("drop")
        self.drop_label.setAlignment(Qt.AlignCenter)
        row2.addWidget(self.drop_label, 1)
        self.preview_btn = QPushButton()
        self.preview_btn.setObjectName("primary")
        self.preview_btn.clicked.connect(self._rebuild_preview)
        row2.addWidget(self.preview_btn)
        cv.addLayout(row2)
        row3 = QHBoxLayout()
        self.enc_label = QLabel()
        row3.addWidget(self.enc_label)
        self.enc_combo = QComboBox()
        self.enc_combo.addItem("UTF-8 (BOM)", "utf-8-sig")
        self.enc_combo.addItem("UTF-8", "utf-8")
        self.enc_combo.addItem("Shift_JIS", "shift_jis")
        row3.addWidget(self.enc_combo)
        self.fw_check = QCheckBox()
        row3.addWidget(self.fw_check)
        row3.addStretch(1)
        cv.addLayout(row3)
        root.addWidget(card)

        # --- FX card
        fxcard = QFrame(); fxcard.setObjectName("card")
        fv = QVBoxLayout(fxcard)
        frow = QHBoxLayout()
        self.fx_title = QLabel()
        self.fx_title.setStyleSheet("font-weight: 700;")
        frow.addWidget(self.fx_title)
        self.fx_enable = QCheckBox()
        self.fx_enable.stateChanged.connect(lambda *_: self._rebuild_preview())
        frow.addWidget(self.fx_enable)
        self.fx_mode_group = QButtonGroup(self)
        self.fx_ref = QRadioButton(); self.fx_ref.setChecked(True)
        self.fx_bank = QRadioButton(); self.fx_manual = QRadioButton()
        for rb in (self.fx_ref, self.fx_bank, self.fx_manual):
            self.fx_mode_group.addButton(rb)
            frow.addWidget(rb)
            rb.toggled.connect(lambda *_: self._rebuild_preview())
        self.fx_update_btn = QPushButton()
        self.fx_update_btn.clicked.connect(self._start_fx_fetch)
        frow.addWidget(self.fx_update_btn)
        frow.addStretch(1)
        fv.addLayout(frow)
        self.fx_status = QLabel()
        self.fx_status.setWordWrap(True)
        fv.addWidget(self.fx_status)
        mrow = QHBoxLayout()
        self.manual_bank_label = QLabel(); mrow.addWidget(self.manual_bank_label)
        self.manual_bank = QLineEdit(); mrow.addWidget(self.manual_bank)
        self.manual_tts_label = QLabel(); mrow.addWidget(self.manual_tts_label)
        self.manual_tts = QLineEdit(); self.manual_tts.setMaximumWidth(90); mrow.addWidget(self.manual_tts)
        self.manual_ttb_label = QLabel(); mrow.addWidget(self.manual_ttb_label)
        self.manual_ttb = QLineEdit(); self.manual_ttb.setMaximumWidth(90); mrow.addWidget(self.manual_ttb)
        self.manual_rate_label = QLabel(); mrow.addWidget(self.manual_rate_label)
        self.manual_rate = QLineEdit(); self.manual_rate.setMaximumWidth(90); mrow.addWidget(self.manual_rate)
        self.manual_date_label = QLabel(); mrow.addWidget(self.manual_date_label)
        self.manual_date = QLineEdit(); mrow.addWidget(self.manual_date)
        fv.addLayout(mrow)
        root.addWidget(fxcard)

        # --- previews + review/report
        split = QSplitter(Qt.Vertical)
        tables = QSplitter(Qt.Horizontal)
        self.before_table = QTableWidget()
        self.after_table = QTableWidget()
        for tw in (self.before_table, self.after_table):
            tw.setEditTriggers(QTableWidget.NoEditTriggers)
        tables.addWidget(self.before_table)
        tables.addWidget(self.after_table)
        split.addWidget(tables)
        bottom = QWidget()
        bv = QVBoxLayout(bottom)
        self.review_label = QLabel()
        self.review_label.setStyleSheet("font-weight: 700;")
        bv.addWidget(self.review_label)
        self.review_list = QListWidget()
        self.review_list.itemDoubleClicked.connect(self._review_clicked)
        bv.addWidget(self.review_list)
        self.report_label = QLabel()
        self.report_label.setStyleSheet("font-weight: 700;")
        bv.addWidget(self.report_label)
        self.report_text = QTextEdit()
        self.report_text.setReadOnly(True)
        self.report_text.setMaximumHeight(130)
        bv.addWidget(self.report_text)
        split.addWidget(bottom)
        split.setSizes([520, 300])
        root.addWidget(split, 1)

        bar = QHBoxLayout()
        self.status_label = QLabel()
        bar.addWidget(self.status_label, 1)
        self.export_csv_btn = QPushButton()
        self.export_csv_btn.clicked.connect(lambda: self._export("csv"))
        bar.addWidget(self.export_csv_btn)
        self.export_xlsx_btn = QPushButton()
        self.export_xlsx_btn.clicked.connect(lambda: self._export("xlsx"))
        bar.addWidget(self.export_xlsx_btn)
        self.report_btn = QPushButton()
        self.report_btn.clicked.connect(self._save_report)
        bar.addWidget(self.report_btn)
        root.addLayout(bar)
        self._fill_country_combos()

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
        self.setWindowTitle(self.t("app_title"))
        self.title_label.setText(self.t("app_title"))
        self.subtitle_label.setText(self.t("app_subtitle"))
        self.lang_label.setText(self.t("lang_label"))
        self.sender_label.setText(self.t("sender"))
        self.receiver_label.setText(self.t("receiver"))
        self.swap_btn.setText(self.t("swap"))
        self.open_btn.setText(self.t("open_file"))
        self.drop_label.setText(self.t("drop_hint"))
        self.preview_btn.setText(self.t("preview_btn"))
        self.enc_label.setText(self.t("encoding"))
        self.fw_check.setText(self.t("fix_fw"))
        self.fx_title.setText(self.t("fx_title"))
        self.fx_enable.setText(self.t("fx_enable"))
        self.fx_ref.setText(self.t("fx_mode_ref"))
        self.fx_bank.setText(self.t("fx_mode_bank"))
        self.fx_manual.setText(self.t("fx_mode_manual"))
        self.fx_update_btn.setText(self.t("fx_update"))
        self.manual_bank_label.setText(self.t("manual_bank"))
        self.manual_tts_label.setText(self.t("manual_tts"))
        self.manual_ttb_label.setText(self.t("manual_ttb"))
        self.manual_rate_label.setText(self.t("manual_rate"))
        self.manual_date_label.setText(self.t("manual_date"))
        self.review_label.setText(self.t("review_title"))
        self.report_label.setText(self.t("report_title"))
        self.export_csv_btn.setText(self.t("export_csv"))
        self.export_xlsx_btn.setText(self.t("export_xlsx"))
        self.report_btn.setText(self.t("save_report"))
        self._fill_country_combos()
        self._update_currency_labels()
        self._update_fx_status()
        if self.table is not None and rebuild:
            self._rebuild_preview()

    def _country_name(self, c):
        return c["name_ja"] if self.lang == "ja" else c["name_en"]

    def _fill_country_combos(self):
        for combo, current in ((self.sender_combo, self.sender_code),
                               (self.receiver_combo, self.receiver_code)):
            combo.blockSignals(True)
            combo.clear()
            for c in COUNTRIES:
                combo.addItem("%s (%s)" % (self._country_name(c), c["code"]), c["code"])
            combo.setCurrentIndex([c["code"] for c in COUNTRIES].index(current))
            combo.blockSignals(False)

    def _update_currency_labels(self):
        for code, label in ((self.sender_code, self.sender_ccy),
                            (self.receiver_code, self.receiver_ccy)):
            c = BY_CODE[code]
            cname = c["currency_ja"] if self.lang == "ja" else c["currency_en"]
            label.setText("%s (%s)" % (cname, c["currency"]))

    def _country_changed(self, *_):
        self.sender_code = self.sender_combo.currentData() or self.sender_code
        self.receiver_code = self.receiver_combo.currentData() or self.receiver_code
        self._save_settings()
        self._update_currency_labels()
        if self.table is not None:
            self._rebuild_preview()

    def _swap(self):
        self.sender_code, self.receiver_code = self.receiver_code, self.sender_code
        self._fill_country_combos()
        self._country_changed()

    # ------------------------------------------------------------ FX
    def _start_fx_fetch(self):
        self.fx_status.setText(self.t("fx_fetching"))

        def work():
            merged, _errors = core.fetch_all_rates(timeout=8)
            mufg = None
            try:
                mufg = core.fetch_mufg(timeout=10)
            except Exception:
                mufg = None
            self.signals.fx_ready.emit(merged, mufg)

        threading.Thread(target=work, daemon=True).start()

    def _on_fx_ready(self, merged, mufg):
        if merged and merged.get("rates"):
            self.fx_cache["merged"] = merged
        if mufg:
            self.fx_cache["mufg"] = mufg
        try:
            core.save_fx_cache(self.fx_cache)
        except Exception:
            pass
        self._update_fx_status()
        if self.table is not None and self.fx_enable.isChecked():
            self._rebuild_preview()

    def _update_fx_status(self):
        merged = self.fx_cache.get("merged")
        mufg = self.fx_cache.get("mufg")
        parts = []
        if merged and merged.get("rates"):
            cov = core.tier_coverage(merged)
            parts.append("公式 %d通貨／ECB基準 %d通貨／参考(集計) %d通貨" % (
                cov.get(1, 0), cov.get(2, 0), cov.get(3, 0)))
            parts.append("取得: %s" % merged.get("fetched_at", ""))
        else:
            parts.append(self.t("fx_no_data"))
        if mufg:
            parts.append("MUFG TTS/TTB: %s" % mufg.get("date", ""))
        self.fx_status.setText(" ｜ ".join(parts))

    def _fx_context(self):
        if not self.fx_enable.isChecked():
            return None
        if self.fx_bank.isChecked():
            return {"mode": "bank", "ctx": {"mufg": self.fx_cache.get("mufg")}}
        if self.fx_manual.isChecked():
            ctx = {"bank_name": self.manual_bank.text().strip(),
                   "date_memo": self.manual_date.text().strip()}
            for key, edit in (("tts", self.manual_tts), ("ttb", self.manual_ttb),
                              ("rate", self.manual_rate)):
                v = edit.text().strip()
                if v:
                    ctx[key] = v
            return {"mode": "manual", "ctx": ctx}
        return {"mode": "ref", "ctx": {"bundle": self.fx_cache.get("merged") or {}}}

    # ------------------------------------------------------------ file flow
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            self._load_path(urls[0].toLocalFile())

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.t("open_file"), "",
            "Excel/CSV (*.xlsx *.xlsm *.csv *.tsv *.txt);;All files (*)")
        if path:
            self._load_path(path)

    def _load_path(self, path):
        try:
            self.table = core.load_table(path)
        except Exception as exc:
            QMessageBox.warning(self, self.t("error_title"),
                                self.t("error_load", msg=str(exc)))
            return
        self.source_path = path
        self.resolutions = {}
        self.status_label.setText(self.t(
            "status_loaded", name=os.path.basename(path), rows=len(self.table.rows)))
        self._rebuild_preview()

    def _rebuild_preview(self):
        if self.table is None:
            return
        fx = self._fx_context()
        self.result = core.convert_table(
            self.table, self.sender_code, self.receiver_code,
            opts={"fix_fullwidth_text": self.fw_check.isChecked()},
            resolutions=self.resolutions, fx=fx)
        self._fill_tables()
        self._fill_reviews()
        self.report_text.setPlainText(core.build_report_text(self.result))
        self.status_label.setText(self.t(
            "status_done", changes=self.result.report["changes"],
            reviews=self.result.report["unresolved"]))

    def _fill_tables(self):
        headers = self.table.headers
        types = self.result.report.get("col_types", [])
        type_names = {"date": self.t("col_type_date"), "amount": self.t("col_type_amount"),
                      "code": self.t("col_type_code"), "text": self.t("col_type_text")}
        disp_headers = ["%s [%s]" % (h, type_names.get(types[i], ""))
                        if i < len(types) else h for i, h in enumerate(headers)]
        changes = {(c["row"], c["col"]): c for c in self.result.changes}
        n = min(len(self.table.rows), MAX_PREVIEW_ROWS)
        for tw, rows in ((self.before_table, self.table.rows),
                         (self.after_table, self.result.rows)):
            tw.clear()
            tw.setColumnCount(len(headers))
            tw.setRowCount(n)
            tw.setHorizontalHeaderLabels(disp_headers)
            for r in range(n):
                for c in range(len(headers)):
                    item = QTableWidgetItem(str(rows[r][c]))
                    if tw is self.after_table and (r, c) in changes:
                        item.setBackground(QColor("#fef9c3"))
                        item.setToolTip("%s → %s (%s)" % (
                            changes[(r, c)]["before"], changes[(r, c)]["after"],
                            changes[(r, c)]["reason"]))
                    tw.setItem(r, c, item)
            tw.resizeColumnsToContents()

    def _fill_reviews(self):
        self.review_list.clear()
        reviews = self.result.reviews if self.result else []
        if not reviews:
            self.review_list.addItem(self.t("review_empty"))
            return
        self.review_list.addItem(self.t("review_count", n=len(reviews)))
        for item in reviews:
            li = QListWidgetItem("#%d %s / %s : %s" % (
                item.row + 2, item.header, self.t("choose"), item.original))
            li.setData(Qt.UserRole, item)
            self.review_list.addItem(li)

    def _review_clicked(self, li):
        item = li.data(Qt.UserRole)
        if item is None:
            return
        self._resolve_review(item)

    def _resolve_review(self, item):
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle(self.t("review_title"))
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel("%s : %s" % (item.header, item.original)))
        why = QLabel(item.reason)
        why.setWordWrap(True)
        v.addWidget(why)
        v.addWidget(QLabel(self.t("choose")))
        group = QButtonGroup(dlg)
        radios = []
        for i, cand in enumerate(item.candidates):
            rb = QRadioButton(cand["label"])
            if i == 0:
                rb.setChecked(True)
            group.addButton(rb)
            radios.append((rb, cand))
            v.addWidget(rb)
        row = QHBoxLayout()
        cell_btn = QPushButton(self.t("apply_cell"))
        all_btn = QPushButton(self.t("apply_all"))
        row.addWidget(cell_btn)
        row.addWidget(all_btn)
        v.addLayout(row)
        outcome = {}

        def apply(scope):
            for rb, cand in radios:
                if rb.isChecked():
                    outcome["cand"] = cand
                    break
            outcome["scope"] = scope
            dlg.accept()

        cell_btn.clicked.connect(lambda: apply("cell"))
        all_btn.clicked.connect(lambda: apply("all"))
        if dlg.exec() and "cand" in outcome:
            if outcome["scope"] == "all":
                self.resolutions[item.pattern_key] = outcome["cand"]["output"]
            else:
                self.resolutions["r%dc%d" % (item.row, item.col)] = outcome["cand"]["output"]
            self._rebuild_preview()

    # ------------------------------------------------------------ export
    def _export(self, kind):
        if self.result is None or self.table is None:
            return
        out_table = core.Table(self.table.headers, self.result.rows)
        if kind == "csv":
            path, _ = QFileDialog.getSaveFileName(
                self, self.t("save_as"), "converted.csv", "CSV (*.csv)")
            if not path:
                return
            delim = BY_CODE[self.receiver_code]["delimiter"]
            core.save_table_csv(out_table, path, delimiter=delim,
                                encoding=self.enc_combo.currentData())
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, self.t("save_as"), "converted.xlsx", "Excel (*.xlsx)")
            if not path:
                return
            core.save_table_xlsx(out_table, path)
        self.status_label.setText(self.t("exported", path=path))

    def _save_report(self):
        if self.result is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, self.t("save_as"), "report.txt", "Text (*.txt)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(core.build_report_text(self.result))
        self.status_label.setText(self.t("report_saved", path=path))


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
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
