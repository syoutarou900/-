# -*- coding: utf-8 -*-
"""MatchDetective (マッチング探偵) - main window.

Two-table reconciliation: the app proposes keys and candidate pairings;
the human makes the final decisions. Source files are never modified.
"""
import json
import os
import sys
import urllib.parse
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QStringListModel, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QCompleter, QDialog, QFileDialog,
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

import core
import houjin
from i18n import LANG_NAMES, LANG_ORDER, RTL_LANGS, tr

MAX_PREVIEW = 200


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


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def data_dir():
    """Per-user data folder: %APPDATA%\\MatchDetective on Windows,
    ~/Library/Application Support/MatchDetective on macOS
    (settings, alias dictionary, registry cache). Falls back to the
    app folder where neither exists (dev / test runs)."""
    if sys.platform == "darwin":
        # Never write inside the .app bundle (read-only / signed):
        # use the standard per-user Application Support folder.
        d = os.path.join(os.path.expanduser("~"), "Library",
                         "Application Support", "MatchDetective")
        try:
            os.makedirs(d, exist_ok=True)
            return d
        except Exception:
            pass
    base = os.environ.get("APPDATA")
    if base:
        d = os.path.join(base, "MatchDetective")
        try:
            os.makedirs(d, exist_ok=True)
            return d
        except Exception:
            pass
    return app_dir()


def shadow(widget, blur=16, y=3, alpha=60):
    from PySide6.QtWidgets import QGraphicsDropShadowEffect
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(0, y)
    eff.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(eff)


class DropCard(QFrame):
    def __init__(self, on_drop):
        super().__init__()
        self.on_drop = on_drop
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            self.on_drop(urls[0].toLocalFile())


class DictDialog(QDialog):
    """Alias-dictionary management: list pairs (source/date), delete,
    and add a pair by typing two names. Typed names are stored exactly
    as typed — never rewritten or 'resolved'."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(win.t("dict_title"))
        self.resize(560, 420)
        v = QVBoxLayout(self)
        self.list = QListWidget()
        v.addWidget(self.list, 1)
        add_row = QHBoxLayout()
        self.name_a = QLineEdit()
        self.name_a.setPlaceholderText(win.t("dict_name_a"))
        self.name_b = QLineEdit()
        self.name_b.setPlaceholderText(win.t("dict_name_b"))
        add_btn = QPushButton(win.t("dict_add_btn"))
        add_btn.clicked.connect(self._add)
        add_row.addWidget(self.name_a)
        add_row.addWidget(self.name_b)
        add_row.addWidget(add_btn)
        v.addLayout(add_row)
        note = QLabel(win.t("dict_note"))
        note.setWordWrap(True)
        note.setStyleSheet("color: #64748b; font-size: 11px;")
        v.addWidget(note)
        btn_row = QHBoxLayout()
        del_btn = QPushButton(win.t("dict_del_btn"))
        del_btn.clicked.connect(self._delete)
        close_btn = QPushButton(win.t("dict_close_btn"))
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(del_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        v.addLayout(btn_row)
        self._refresh()

    def _refresh(self):
        self.list.clear()
        for e in self.win.dictionary.entries:
            if e.get("source") == "houjin" and e.get("number"):
                src = self.win.t("reason_houjin", number=e["number"])
            else:
                src = self.win.t("dict_source_manual")
            item = QListWidgetItem("%s  ⇄  %s   (%s · %s)" % (
                e["a"], e["b"], src, e.get("date", "")))
            item.setData(Qt.UserRole, (e["a"], e["b"]))
            self.list.addItem(item)

    def _add(self):
        a, b = self.name_a.text(), self.name_b.text()
        if not a.strip() or not b.strip():
            return
        # stored exactly as typed (no normalization of the stored text)
        if self.win.dictionary.add(a, b, source="manual"):
            self.win.dictionary.save()
        self.name_a.clear()
        self.name_b.clear()
        self._refresh()

    def _delete(self):
        item = self.list.currentItem()
        if item is None:
            return
        a, b = item.data(Qt.UserRole)
        if self.win.dictionary.remove(a, b):
            self.win.dictionary.save()
        # deliberately no retroactive change to a shown result:
        # deletion takes effect from the next reconciliation run
        self._refresh()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.lang = "ja"
        self.table_a = None
        self.table_b = None
        self.path_a = ""
        self.path_b = ""
        self.result = None
        self.result_cfg = None
        self._combo_dirty = {}   # (row, side) -> user typed/picked by hand
        self._houjin_id = ""
        self._evidence_records = []   # [houjin.Corporation] shown below
        self._evidence_name = ""
        self._load_settings()
        self.dictionary = core.AliasDictionary(
            os.path.join(data_dir(), "aliases.json"))
        self._build_ui()
        self.apply_language(self.lang, rebuild=False)
        self.status_label.setText(self.t("status_ready"))

    # ------------------------------------------------------------ settings
    def _settings_path(self):
        return os.path.join(data_dir(), "settings.json")

    def _load_settings(self):
        d = None
        for path in (self._settings_path(),
                     os.path.join(app_dir(), "settings.json")):  # legacy
            try:
                with open(path, encoding="utf-8") as fh:
                    d = json.load(fh)
                break
            except Exception:
                continue
        d = d or {}
        if d.get("lang") in LANG_ORDER:
            self.lang = d["lang"]
        self._tol = str(d.get("tolerance", "0"))
        self._houjin_id = str(d.get("houjin_id", ""))

    def _save_settings(self):
        try:
            with open(self._settings_path(), "w", encoding="utf-8") as fh:
                json.dump({"lang": self.lang,
                           "tolerance": self.tol_edit.text().strip() if hasattr(self, "tol_edit") else self._tol,
                           "houjin_id": self.houjin_id_edit.text().strip() if hasattr(self, "houjin_id_edit") else self._houjin_id},
                          fh, ensure_ascii=False)
        except Exception:
            pass

    def t(self, key, **kw):
        return tr(self.lang, key, **kw)

    # ------------------------------------------------------------ UI build
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        # header
        header = QFrame()
        header.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            " stop:0 #1e3a8a, stop:.55 #2563eb, stop:1 #0ea5e9); border-radius: 14px; }")
        shadow(header, blur=18, y=4, alpha=70)
        hv = QVBoxLayout(header)
        hv.setContentsMargins(16, 12, 16, 12)
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
        root.addWidget(header)

        # load cards
        load_row = QHBoxLayout()
        self.card_a = self._make_load_card("a")
        self.card_b = self._make_load_card("b")
        load_row.addWidget(self.card_a["frame"])
        load_row.addWidget(self.card_b["frame"])
        root.addLayout(load_row)

        # previews
        prev_row = QHBoxLayout()
        self.prev_a = self._make_preview()
        self.prev_b = self._make_preview()
        prev_row.addWidget(self.prev_a)
        prev_row.addWidget(self.prev_b)
        root.addLayout(prev_row)

        # setup card
        setup = QFrame()
        setup.setStyleSheet("QFrame { background: white; border-radius: 12px; }")
        shadow(setup)
        sv = QVBoxLayout(setup)
        self.setup_title = QLabel()
        self.setup_title.setStyleSheet("font-weight: 700; font-size: 13px;")
        sv.addWidget(self.setup_title)
        grid = QGridLayout()
        self.setup_labels = {}
        self.combos = {}   # (row_name, side) -> QComboBox ; rows: key1 key2 cmp1 cmp2
        for r, rname in enumerate(("key1", "key2", "cmp1", "cmp2")):
            lab = QLabel()
            self.setup_labels[rname] = lab
            grid.addWidget(lab, r, 0)
            for c, side in enumerate(("a", "b")):
                combo = QComboBox()
                combo.setMinimumWidth(170)
                # Editable with autocompletion: the user may also TYPE a
                # column name; it is resolved in core.resolve_column when
                # the field loses focus or reconciliation runs. Nothing
                # validates or rewrites the text while it is being typed
                # (IME composition stays untouched).
                combo.setEditable(True)
                combo.setInsertPolicy(QComboBox.NoInsert)
                completer = QCompleter(combo)
                completer.setCaseSensitivity(Qt.CaseInsensitive)
                completer.setFilterMode(Qt.MatchContains)
                completer.setCompletionMode(QCompleter.PopupCompletion)
                completer.setModel(QStringListModel([], combo))
                combo.setCompleter(completer)
                self._combo_dirty[(rname, side)] = False
                combo.lineEdit().textEdited.connect(
                    lambda _t, rn=rname, sd=side: self._on_text_typed(rn, sd))
                combo.activated.connect(
                    lambda _i, rn=rname, sd=side: self._on_combo_picked(rn, sd))
                combo.lineEdit().editingFinished.connect(
                    lambda rn=rname, sd=side: self._on_combo_edited(rn, sd))
                self.combos[(rname, side)] = combo
                grid.addWidget(combo, r, c + 1)
        sv.addLayout(grid)
        opt_row = QHBoxLayout()
        self.tol_label = QLabel()
        opt_row.addWidget(self.tol_label)
        self.tol_edit = QLineEdit(self._tol)
        self.tol_edit.setMaximumWidth(70)
        opt_row.addWidget(self.tol_edit)
        opt_row.addStretch(1)
        self.run_btn = QPushButton()
        self.run_btn.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            " stop:0 #38bdf8, stop:1 #2563eb); color: white; font-weight: 800;"
            " font-size: 14px; padding: 8px 26px; border-radius: 10px; }")
        self.run_btn.clicked.connect(self._run)
        opt_row.addWidget(self.run_btn)
        sv.addLayout(opt_row)
        # corporate-number (A) settings: the user's own free NTA
        # application ID. Optional — everything else works without it.
        hj_row = QHBoxLayout()
        self.houjin_id_label = QLabel()
        hj_row.addWidget(self.houjin_id_label)
        self.houjin_id_edit = QLineEdit(self._houjin_id)
        self.houjin_id_edit.setEchoMode(QLineEdit.Password)
        self.houjin_id_edit.setMaximumWidth(220)
        self.houjin_id_edit.editingFinished.connect(self._save_settings)
        hj_row.addWidget(self.houjin_id_edit)
        self.houjin_reg_link = QLabel()
        self.houjin_reg_link.setOpenExternalLinks(True)
        hj_row.addWidget(self.houjin_reg_link)
        hj_row.addStretch(1)
        sv.addLayout(hj_row)
        self.houjin_id_hint = QLabel()
        self.houjin_id_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        self.houjin_id_hint.setWordWrap(True)
        sv.addWidget(self.houjin_id_hint)
        root.addWidget(setup)

        # summary + results
        self.summary_label = QLabel()
        self.summary_label.setStyleSheet("font-weight: 700; font-size: 13px;")
        root.addWidget(self.summary_label)
        self.tabs = QTabWidget()
        # cat1 tab
        cat1w = QWidget()
        c1 = QVBoxLayout(cat1w)
        c1row = QHBoxLayout()
        col_a = QVBoxLayout()
        self.cat1_a_title = QLabel()
        col_a.addWidget(self.cat1_a_title)
        self.cat1_a_list = QListWidget()
        col_a.addWidget(self.cat1_a_list)
        col_b = QVBoxLayout()
        self.cat1_b_title = QLabel()
        col_b.addWidget(self.cat1_b_title)
        self.cat1_b_list = QListWidget()
        col_b.addWidget(self.cat1_b_list)
        c1row.addLayout(col_a)
        c1row.addLayout(col_b)
        c1.addLayout(c1row)
        self.manual_btn = QPushButton()
        self.manual_btn.clicked.connect(self._manual_pair)
        c1.addWidget(self.manual_btn)
        # dictionary (B) + registry evidence (A) actions on cat-1 rows
        act_row = QHBoxLayout()
        self.register_same_btn = QPushButton()
        self.register_same_btn.clicked.connect(self._register_same)
        act_row.addWidget(self.register_same_btn)
        self.dict_btn = QPushButton()
        self.dict_btn.clicked.connect(self._open_dict_dialog)
        act_row.addWidget(self.dict_btn)
        act_row.addStretch(1)
        c1.addLayout(act_row)
        self.evidence_title = QLabel()
        self.evidence_title.setStyleSheet("font-weight: 700; font-size: 12px;")
        c1.addWidget(self.evidence_title)
        ev_row = QHBoxLayout()
        self.houjin_check_btn = QPushButton()
        self.houjin_check_btn.clicked.connect(self._houjin_check)
        ev_row.addWidget(self.houjin_check_btn)
        self.houjin_auto_btn = QPushButton()
        self.houjin_auto_btn.clicked.connect(self._houjin_auto)
        ev_row.addWidget(self.houjin_auto_btn)
        self.web_check_btn = QPushButton()
        self.web_check_btn.clicked.connect(self._web_check)
        ev_row.addWidget(self.web_check_btn)
        ev_row.addStretch(1)
        c1.addLayout(ev_row)
        self.evidence_list = QListWidget()
        self.evidence_list.setMaximumHeight(110)
        c1.addWidget(self.evidence_list)
        pick_row = QHBoxLayout()
        self.houjin_pick_btn = QPushButton()
        self.houjin_pick_btn.clicked.connect(self._houjin_pick)
        pick_row.addWidget(self.houjin_pick_btn)
        self.evidence_meta = QLabel()
        self.evidence_meta.setStyleSheet("color: #475569; font-size: 11px;")
        pick_row.addWidget(self.evidence_meta)
        pick_row.addStretch(1)
        c1.addLayout(pick_row)
        self.attribution_label = QLabel()
        self.attribution_label.setStyleSheet("color: #94a3b8; font-size: 10px;")
        self.attribution_label.setWordWrap(True)
        c1.addWidget(self.attribution_label)
        self.tabs.addTab(cat1w, "")
        # cat2 tab
        self.cat2_table = QTableWidget(0, 6)
        self.tabs.addTab(self.cat2_table, "")
        # cat3 tab
        self.cat3_list = QListWidget()
        self.tabs.addTab(self.cat3_list, "")
        # ok tab
        self.ok_table = QTableWidget(0, 4)
        self.tabs.addTab(self.ok_table, "")
        root.addWidget(self.tabs, 1)

        # export row
        erow = QHBoxLayout()
        self.include_ok = QCheckBox()
        erow.addWidget(self.include_ok)
        erow.addStretch(1)
        self.export_xlsx_btn = QPushButton()
        self.export_xlsx_btn.clicked.connect(lambda: self._export("xlsx"))
        self.export_csv_btn = QPushButton()
        self.export_csv_btn.clicked.connect(lambda: self._export("csv"))
        self.report_btn = QPushButton()
        self.report_btn.clicked.connect(self._save_report)
        erow.addWidget(self.export_xlsx_btn)
        erow.addWidget(self.export_csv_btn)
        erow.addWidget(self.report_btn)
        root.addLayout(erow)

        self.status_label = QLabel()
        root.addWidget(self.status_label)
        self.resize(1180, 800)

    def _make_load_card(self, side):
        frame = DropCard(lambda p, s=side: self._load_path(p, s))
        frame.setStyleSheet(
            "QFrame { background: white; border: 2px dashed #93c5fd; border-radius: 12px; }")
        shadow(frame)
        v = QVBoxLayout(frame)
        title = QLabel()
        title.setStyleSheet("font-weight: 800; font-size: 14px;")
        v.addWidget(title)
        info = QLabel()
        info.setStyleSheet("color: #475569;")
        info.setWordWrap(True)
        v.addWidget(info)
        btn = QPushButton()
        btn.clicked.connect(lambda: self._open_file(side))
        v.addWidget(btn)
        return {"frame": frame, "title": title, "info": info, "btn": btn}

    def _make_preview(self):
        tw = QTableWidget(0, 0)
        tw.setMaximumHeight(150)
        tw.setEditTriggers(QTableWidget.NoEditTriggers)
        return tw

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
        for side, card in (("a", self.card_a), ("b", self.card_b)):
            card["title"].setText(self.t("table_" + side))
            card["btn"].setText(self.t("open_" + side))
            if getattr(self, "table_" + side) is None:
                card["info"].setText(self.t("drop_hint"))
        self.setup_title.setText(self.t("setup_title"))
        for rname in ("key1", "key2", "cmp1", "cmp2"):
            self.setup_labels[rname].setText(self.t(rname))
        self.tol_label.setText(self.t("tol_label"))
        self.run_btn.setText(self.t("run_btn"))
        self.cat1_a_title.setText(self.t("cat1_a_title"))
        self.cat1_b_title.setText(self.t("cat1_b_title"))
        self.manual_btn.setText(self.t("manual_pair_btn"))
        self.tabs.setTabText(0, self.t("tab_cat1"))
        self.tabs.setTabText(1, self.t("tab_cat2"))
        self.tabs.setTabText(2, self.t("tab_cat3"))
        self.tabs.setTabText(3, self.t("tab_ok"))
        self.cat2_table.setHorizontalHeaderLabels(
            [self.t("hdr_row"), self.t("hdr_col"), self.t("hdr_a"),
             self.t("hdr_b"), self.t("hdr_diff"), self.t("hdr_reason")])
        self.ok_table.setHorizontalHeaderLabels(
            [self.t("hdr_row"), self.t("hdr_a"), self.t("hdr_row"), self.t("hdr_b")])
        self.include_ok.setText(self.t("include_ok"))
        self.export_xlsx_btn.setText(self.t("export_xlsx"))
        self.export_csv_btn.setText(self.t("export_csv"))
        self.report_btn.setText(self.t("save_report"))
        self.houjin_id_label.setText(self.t("houjin_id_label"))
        self.houjin_id_hint.setText(self.t("houjin_id_hint"))
        self.houjin_reg_link.setText('<a href="%s">%s</a>' % (
            houjin.REGISTRATION_URL, self.t("houjin_reg_link")))
        self.register_same_btn.setText(self.t("register_same_btn"))
        self.dict_btn.setText(self.t("dict_btn"))
        self.evidence_title.setText(self.t("houjin_evidence_title"))
        self.houjin_check_btn.setText(self.t("houjin_check_btn"))
        self.houjin_auto_btn.setText(self.t("houjin_auto_btn"))
        self.web_check_btn.setText(self.t("web_check_btn"))
        self.houjin_pick_btn.setText(self.t("houjin_pick_btn"))
        self.attribution_label.setText(self.t("houjin_attribution"))
        if rebuild:
            self._refresh_results()
            self._refresh_summary()

    # ------------------------------------------------------------ loading
    def _open_file(self, side):
        path, _ = QFileDialog.getOpenFileName(
            self, self.t("open_" + side), "",
            "Excel/CSV (*.xlsx *.xlsm *.csv *.tsv *.txt);;All files (*)")
        if path:
            self._load_path(path, side)

    def _load_path(self, path, side):
        try:
            table = core.load_table(path)
        except Exception as exc:
            QMessageBox.warning(self, self.t("error_title"),
                                self.t("error_load", msg=str(exc)))
            return
        if side == "a":
            self.table_a, self.path_a = table, path
        else:
            self.table_b, self.path_b = table, path
        card = self.card_a if side == "a" else self.card_b
        card["info"].setText("%s (%s)" % (
            os.path.basename(path), self.t("rows_fmt", n=len(table.rows))))
        prev = self.prev_a if side == "a" else self.prev_b
        self._fill_preview(prev, table)
        if self.table_a is not None and self.table_b is not None:
            self._apply_proposal()
        self.result = None

    def _fill_preview(self, tw, table):
        tw.clear()
        tw.setColumnCount(len(table.headers))
        tw.setHorizontalHeaderLabels(table.headers)
        n = min(len(table.rows), MAX_PREVIEW)
        tw.setRowCount(n)
        for r in range(n):
            for c in range(len(table.headers)):
                tw.setItem(r, c, QTableWidgetItem(str(table.rows[r][c])))

    def _apply_proposal(self):
        keys, compares = core.propose_mapping(self.table_a, self.table_b)
        for rname in ("key1", "key2", "cmp1", "cmp2"):
            for side, table in (("a", self.table_a), ("b", self.table_b)):
                combo = self.combos[(rname, side)]
                combo.blockSignals(True)
                combo.clear()
                if rname in ("key2", "cmp2"):
                    combo.addItem(self.t("none_opt"), -1)
                for i, h in enumerate(table.headers):
                    combo.addItem(h, i)
                combo.blockSignals(False)
                combo.completer().setModel(
                    QStringListModel(list(table.headers), combo))
                self._combo_dirty[(rname, side)] = False
                self._mark_combo((rname, side), False)
        def set_pair(rname, pair):
            if pair is None:
                return
            self.combos[(rname, "a")].setCurrentIndex(
                self.combos[(rname, "a")].findData(pair[0]))
            self.combos[(rname, "b")].setCurrentIndex(
                self.combos[(rname, "b")].findData(pair[1]))
        if len(keys) >= 1:
            set_pair("key1", keys[0])
        if len(keys) >= 2:
            set_pair("key2", keys[1])
        if len(compares) >= 1:
            set_pair("cmp1", compares[0])
        if len(compares) >= 2:
            set_pair("cmp2", compares[1])

    # ------------------------------------------------- typed column names
    # The key/compare combos are editable. Whatever the user leaves in the
    # box — a list pick or free-typed text — is resolved to a real column
    # index only here (focus-out / run), never while typing, and the typed
    # text itself is never rewritten.
    def _mark_combo(self, key, bad):
        self.combos[key].setStyleSheet(
            "QComboBox { border: 2px solid #dc2626; }" if bad else "")

    def _on_text_typed(self, rname, side):
        # Keystrokes only: mark the field as hand-edited (for cross-fill)
        # and drop a stale error mark. No validation, no rewriting — an
        # IME composition in progress must not be disturbed.
        self._combo_dirty[(rname, side)] = True
        self._mark_combo((rname, side), False)

    def _on_combo_picked(self, rname, side):
        self._combo_dirty[(rname, side)] = True
        self._mark_combo((rname, side), False)

    def _combo_index(self, rname, side):
        """Resolve one setup combo -> ('ok', idx) | ('unset', None) |
        ('bad', None). 'bad' = non-empty text that matches no column."""
        table = self.table_a if side == "a" else self.table_b
        if table is None:
            return ("unset", None)
        combo = self.combos[(rname, side)]
        text = combo.currentText()
        if not text.strip() or text == self.t("none_opt"):
            return ("unset", None)
        # fast path: the box still shows an item exactly as listed
        ci = combo.currentIndex()
        if 0 <= ci < combo.count() and combo.itemText(ci) == text:
            data = combo.itemData(ci)
            return ("unset", None) if data is None or data < 0 else ("ok", data)
        idx = core.resolve_column(table, text)
        return ("ok", idx) if idx is not None else ("bad", None)

    def _validate_combo(self, rname, side):
        """Focus-out validation: mark + warn, but never touch the text."""
        status, _idx = self._combo_index(rname, side)
        if status == "bad":
            self._mark_combo((rname, side), True)
            self.status_label.setText(self.t(
                "col_unresolved",
                text=self.combos[(rname, side)].currentText()))
            return False
        self._mark_combo((rname, side), False)
        return True

    def _on_combo_edited(self, rname, side):
        if self._validate_combo(rname, side):
            self._cross_fill(rname, side)

    def _cross_fill(self, rname, side):
        """If this side resolved, try the same typed name on the other
        side — but only when the other box is untouched by the user and
        does not currently resolve to a column."""
        other = "b" if side == "a" else "a"
        okey = (rname, other)
        if self._combo_dirty.get(okey):
            return
        status, _idx = self._combo_index(rname, other)
        if status == "ok":
            return
        table_o = self.table_b if other == "b" else self.table_a
        if table_o is None:
            return
        idx = core.resolve_column(
            table_o, self.combos[(rname, side)].currentText())
        if idx is None:
            return
        # show the other table's own header name in its box
        self.combos[okey].setEditText(table_o.headers[idx])
        self._mark_combo(okey, False)

    def _current_mapping(self):
        """-> (key_pairs, compare_pairs, bad) where bad lists
        (row, side, text) combos whose text resolved to no column.
        A pair counts only when BOTH sides resolve; a row with one side
        set and the other 'unset' keeps the pre-existing behaviour of
        being ignored unless the set side is unresolvable."""
        bad = []
        pairs = {}
        for rname in ("key1", "key2", "cmp1", "cmp2"):
            resolved = {}
            for side in ("a", "b"):
                status, idx = self._combo_index(rname, side)
                if status == "bad":
                    bad.append((rname, side,
                                self.combos[(rname, side)].currentText()))
                elif status == "ok":
                    resolved[side] = idx
            if len(resolved) == 2:
                pairs[rname] = (resolved["a"], resolved["b"])
        keys = [pairs[r] for r in ("key1", "key2") if r in pairs]
        cmps = [pairs[r] for r in ("cmp1", "cmp2") if r in pairs]
        return keys, cmps, bad

    # ------------------------------------------------------------ run
    def _run(self):
        if self.table_a is None or self.table_b is None:
            self.status_label.setText(self.t("status_need"))
            return
        keys, cmps, bad = self._current_mapping()
        for rname, side, _text in bad:
            self._mark_combo((rname, side), True)
        if bad:
            # typed text that matches no column: warn and stop — never
            # silently fall back to some other column
            self.status_label.setText(
                self.t("col_unresolved", text=bad[0][2]))
            return
        if not keys:
            self.status_label.setText(self.t("status_need"))
            return
        try:
            tol = Decimal(self.tol_edit.text().strip() or "0")
        except InvalidOperation:
            tol = Decimal("0")
        self._save_settings()
        self.result = core.reconcile(
            self.table_a, self.table_b, keys, cmps, tolerance=tol,
            equiv=core.CompanyEquivalence(self.dictionary))
        self.result_cfg = {"key_pairs": keys, "compare_pairs": cmps,
                           "tolerance": tol}
        self._refresh_results()
        self._refresh_summary()

    def _key_display(self, table, idx, side):
        pairs = self.result_cfg["key_pairs"]
        row = table.rows[idx]
        vals = []
        for a, b in pairs:
            ci = a if side == "a" else b
            vals.append(str(row[ci]) if ci < len(row) else "")
        return " / ".join(vals)

    def _cmp_display(self, table, idx, side):
        pairs = self.result_cfg["compare_pairs"]
        row = table.rows[idx]
        vals = []
        for a, b in pairs:
            ci = a if side == "a" else b
            vals.append(str(row[ci]) if ci < len(row) else "")
        return " / ".join(vals)

    def _refresh_summary(self):
        if self.result is None:
            self.summary_label.setText("")
            return
        c = self.result.counts()
        self.summary_label.setText(self.t(
            "summary_fmt", ta=c["total_a"], tb=c["total_b"], ok=c["ok"],
            diff=c["diff"], c1a=c["cat1_a"], c1b=c["cat1_b"], c3=c["cat3"]))
        self.tabs.setTabText(0, "%s (%d)" % (self.t("tab_cat1"), c["cat1_a"] + c["cat1_b"]))
        self.tabs.setTabText(1, "%s (%d)" % (self.t("tab_cat2"), c["diff"]))
        self.tabs.setTabText(2, "%s (%d)" % (self.t("tab_cat3"), c["cat3"]))
        self.tabs.setTabText(3, "%s (%d)" % (self.t("tab_ok"), c["ok"]))

    def _refresh_results(self):
        self.cat1_a_list.clear()
        self.cat1_b_list.clear()
        self.cat2_table.setRowCount(0)
        self.cat3_list.clear()
        self.ok_table.setRowCount(0)
        if self.result is None:
            return
        res = self.result
        for lst, idxs, side in ((self.cat1_a_list, res.cat1_a(), "a"),
                                (self.cat1_b_list, res.cat1_b(), "b")):
            table = self.table_a if side == "a" else self.table_b
            for i in idxs:
                text = "#%d  %s  |  %s" % (
                    i + 2, self._key_display(table, i, side),
                    self._cmp_display(table, i, side))
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, i)
                lst.addItem(item)
        # cat2
        rows = []
        for dp in res.diff_pairs:
            for d in dp.diffs:
                rows.append((dp, d))
        self.cat2_table.setRowCount(len(rows))
        for r, (dp, d) in enumerate(rows):
            col_name = self.table_a.headers[d["ca"]]
            diff = ""
            if d["da"] is not None and d["db"] is not None:
                diff = core.fmt_decimal(d["db"] - d["da"])
            vals = ["%d / %d" % (dp.a + 2, dp.b + 2), col_name,
                    str(d["va"]), str(d["vb"]), diff, dp.origin]
            for c, v in enumerate(vals):
                self.cat2_table.setItem(r, c, QTableWidgetItem(v))
        self.cat2_table.resizeColumnsToContents()
        # cat3
        for cand in res.candidates:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, cand.id)
            self.cat3_list.addItem(item)
            self.cat3_list.setItemWidget(item, self._candidate_widget(cand))
            item.setSizeHint(self.cat3_list.itemWidget(item).sizeHint())
        # ok
        self.ok_table.setRowCount(len(res.ok_pairs))
        for r, (ai, bi) in enumerate(res.ok_pairs):
            vals = [str(ai + 2), self._key_display(self.table_a, ai, "a"),
                    str(bi + 2), self._key_display(self.table_b, bi, "b")]
            for c, v in enumerate(vals):
                self.ok_table.setItem(r, c, QTableWidgetItem(v))
        self.ok_table.resizeColumnsToContents()

    def _reason_text(self, cand):
        return self.t(cand.reason_key, **cand.reason_params)

    def _candidate_widget(self, cand):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 6, 8, 6)
        a_disp = " + ".join("#%d %s" % (i + 2, self._key_display(self.table_a, i, "a"))
                             for i in cand.a_rows)
        b_disp = " + ".join("#%d %s" % (i + 2, self._key_display(self.table_b, i, "b"))
                             for i in cand.b_rows)
        title = QLabel("A: %s  ⇄  B: %s" % (a_disp, b_disp))
        title.setStyleSheet("font-weight: 700;")
        title.setWordWrap(True)
        v.addWidget(title)
        detail_text = self._reason_text(cand)
        if cand.confidence is not None:
            detail_text += " ・ %s: %d%%" % (self.t("hdr_conf"), cand.confidence)
        detail_text += " ・ %s" % self.t("status_" + cand.status)
        detail = QLabel(detail_text)
        detail.setWordWrap(True)
        v.addWidget(detail)
        if cand.status == "pending":
            row = QHBoxLayout()
            acc = QPushButton(self.t("accept_btn"))
            rej = QPushButton(self.t("reject_btn"))
            acc.clicked.connect(lambda _, cid=cand.id: self._decide(cid, True))
            rej.clicked.connect(lambda _, cid=cand.id: self._decide(cid, False))
            row.addWidget(acc)
            row.addWidget(rej)
            row.addStretch(1)
            v.addLayout(row)
        return w

    def _decide(self, cid, accept):
        if self.result is None:
            return
        if accept:
            self.result.accept(cid)
        else:
            self.result.reject(cid)
        self._refresh_results()
        self._refresh_summary()

    # ------------------------------------------- dictionary / registry
    def _company_col(self, side):
        """Index of the company-name key column for `side`, or None."""
        if not self.result_cfg:
            return None
        for a, b in self.result_cfg["key_pairs"]:
            ha = self.table_a.headers[a] if a < len(self.table_a.headers) else ""
            hb = self.table_b.headers[b] if b < len(self.table_b.headers) else ""
            if core.header_concept(ha) == "company" or \
                    core.header_concept(hb) == "company":
                return a if side == "a" else b
        return None

    def _row_company(self, side, idx):
        col = self._company_col(side)
        if col is None:
            return None
        table = self.table_a if side == "a" else self.table_b
        row = table.rows[idx]
        return str(row[col]) if col < len(row) else ""

    def _selected_cat1(self):
        ia = self.cat1_a_list.currentItem()
        ib = self.cat1_b_list.currentItem()
        ai = ia.data(Qt.UserRole) if ia is not None else None
        bi = ib.data(Qt.UserRole) if ib is not None else None
        return ai, bi

    def _manual_pair(self):
        if self.result is None:
            return
        ai, bi = self._selected_cat1()
        if ai is None or bi is None:
            return
        name_a = self._row_company("a", ai)
        name_b = self._row_company("b", bi)
        learn = False
        if name_a and name_b and \
                core.normalize_company(name_a) != core.normalize_company(name_b) and \
                not self.dictionary.has(name_a, name_b):
            # names differ beyond normalization: ask once whether this
            # confirmed pair should be learned into the dictionary
            dlg = QDialog(self)
            dlg.setWindowTitle(self.t("pair_confirm_title"))
            v = QVBoxLayout(dlg)
            msg = QLabel(self.t("pair_confirm_fmt", a=name_a, b=name_b))
            msg.setWordWrap(True)
            v.addWidget(msg)
            chk = QCheckBox(self.t("dict_register_opt"))
            chk.setChecked(True)               # default ON (per design)
            v.addWidget(chk)
            row = QHBoxLayout()
            okb = QPushButton(self.t("ok_btn"))
            okb.clicked.connect(dlg.accept)
            canb = QPushButton(self.t("cancel_btn"))
            canb.clicked.connect(dlg.reject)
            row.addWidget(okb)
            row.addWidget(canb)
            v.addLayout(row)
            if dlg.exec() != QDialog.Accepted:
                return
            learn = chk.isChecked()
        if self.result.manual_pair(ai, bi):
            if learn:
                self.dictionary.add(name_a, name_b, source="manual")
                self.dictionary.save()
                self.status_label.setText(
                    self.t("dict_registered", a=name_a, b=name_b))
            self._refresh_results()
            self._refresh_summary()

    def _register_same(self):
        """(B) learning action: register the two selected rows' company
        names as the same company, and pair the rows in this result."""
        if self.result is None:
            return
        ai, bi = self._selected_cat1()
        if ai is None or bi is None:
            self.status_label.setText(self.t("dict_need_both"))
            return
        name_a = self._row_company("a", ai)
        name_b = self._row_company("b", bi)
        if name_a is None or name_b is None:
            self.status_label.setText(self.t("dict_need_company"))
            return
        self.dictionary.add(name_a, name_b, source="manual")
        self.dictionary.save()
        self.result.manual_pair(ai, bi)
        self.status_label.setText(
            self.t("dict_registered", a=name_a, b=name_b))
        self._refresh_results()
        self._refresh_summary()

    def _open_dict_dialog(self):
        DictDialog(self).exec()

    # -- corporate-number registry (A) --------------------------------
    def _houjin_client(self):
        app_id = self.houjin_id_edit.text().strip()
        if not app_id:
            return None
        self._save_settings()
        return houjin.HoujinClient(
            app_id, cache_path=os.path.join(data_dir(), "houjin_cache.json"))

    def _houjin_error_status(self, exc):
        key = {"network": "houjin_err_network", "http": "houjin_err_http",
               "parse": "houjin_err_parse"}.get(exc.kind, "houjin_err_parse")
        self.status_label.setText(self.t(key))

    def _houjin_lookup(self, client, name):
        """Registry lookup with a wait cursor; None on error (status set)."""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.status_label.setText(self.t("houjin_searching"))
        QApplication.processEvents()
        try:
            return client.search_by_name(name)
        except houjin.HoujinError as exc:
            self._houjin_error_status(exc)
            return None
        finally:
            QApplication.restoreOverrideCursor()

    def _show_evidence(self, name, res):
        self._evidence_name = name
        self._evidence_records = res["records"][:50]
        self.evidence_list.clear()
        for rec in self._evidence_records:
            text = "%s  %s  /  %s  /  %s" % (
                rec.number, rec.name, rec.furigana, rec.address)
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, rec.number)
            self.evidence_list.addItem(item)
        cache = self.t("houjin_from_cache") if res["from_cache"] else ""
        summary = self.t(
            "houjin_records_fmt", name=name, count=len(res["records"]),
            date=res["last_update"] or "-", cache=cache,
            fetched=res["fetched"])
        self.evidence_meta.setText(summary)
        if res["records"]:
            self.status_label.setText(summary)   # clears "searching…"
        else:
            self.status_label.setText(self.t("houjin_no_hit", name=name))

    def _selected_name_for_check(self):
        ai, bi = self._selected_cat1()
        if ai is not None:
            return self._row_company("a", ai)
        if bi is not None:
            return self._row_company("b", bi)
        return None

    def _houjin_check(self):
        """Evidence action: show the registry records for the selected
        unmatched company name. The app does not scrape company sites —
        the official registry is the evidence; the human judges."""
        if self.result is None:
            return
        name = self._selected_name_for_check()
        if not name:
            self.status_label.setText(self.t("dict_need_company"))
            return
        client = self._houjin_client()
        if client is None:
            self.status_label.setText(self.t("houjin_need_id"))
            return
        res = self._houjin_lookup(client, name)
        if res is not None:
            self._show_evidence(name, res)

    def _houjin_auto(self):
        """Auto-pair category-1 rows ONLY on registry-proven identity
        (houjin.evaluate's strict rule). Multi-hit names are surfaced
        as evidence for the human instead of being paired."""
        if self.result is None:
            return
        client = self._houjin_client()
        if client is None:
            self.status_label.setText(self.t("houjin_need_id"))
            return
        res = self.result
        lookups = {}
        paired = 0
        multi = None
        for ai in list(res.cat1_a()):
            for bi in list(res.cat1_b()):
                if ai not in res.cat1_a() or bi not in res.cat1_b():
                    continue
                name_a = self._row_company("a", ai)
                name_b = self._row_company("b", bi)
                if not name_a or not name_b:
                    continue
                a_kana = core.is_kana_only(name_a)
                b_kana = core.is_kana_only(name_b)
                if a_kana == b_kana:
                    continue        # need exactly one kana-only side
                x, y = (name_b, name_a) if a_kana else (name_a, name_b)
                if x not in lookups:
                    got = self._houjin_lookup(client, x)
                    if got is None:
                        self._refresh_results()
                        self._refresh_summary()
                        return      # error already reported
                    lookups[x] = got
                status, payload = houjin.evaluate(
                    lookups[x]["records"], x, y)
                if status == "auto":
                    if res.houjin_pair(ai, bi, payload.number):
                        paired += 1
                elif status == "multi" and multi is None:
                    multi = (x, payload, lookups[x])
        self._refresh_results()
        self._refresh_summary()
        if multi is not None:
            x, _records, got = multi
            self._show_evidence(x, got)
            self.status_label.setText(self.t(
                "houjin_multi_msg", name=x, count=len(_records)))
        elif paired:
            self.status_label.setText(self.t("houjin_auto_done", n=paired))

    def _houjin_pick(self):
        """Human pick from the evidence list: register the two selected
        rows' names as a dictionary pair annotated with the picked
        corporation's number, and pair the rows in this result."""
        if self.result is None:
            return
        item = self.evidence_list.currentItem()
        ai, bi = self._selected_cat1()
        if item is None or ai is None or bi is None:
            self.status_label.setText(self.t("dict_need_both"))
            return
        name_a = self._row_company("a", ai)
        name_b = self._row_company("b", bi)
        if name_a is None or name_b is None:
            self.status_label.setText(self.t("dict_need_company"))
            return
        number = item.data(Qt.UserRole)
        self.dictionary.add(name_a, name_b, source="houjin", number=number)
        self.dictionary.save()
        self.result.manual_pair(ai, bi)
        self.status_label.setText(
            self.t("dict_registered", a=name_a, b=name_b))
        self._refresh_results()
        self._refresh_summary()

    def _web_check(self):
        """Open the user's default browser with a company search. The
        human checks the official site themselves; the app never
        scrapes company websites."""
        name = self._selected_name_for_check()
        if not name:
            self.status_label.setText(self.t("dict_need_company"))
            return
        q = urllib.parse.quote("%s 会社概要 公式サイト" % name)
        QDesktopServices.openUrl(QUrl("https://www.google.com/search?q=" + q))

    # ------------------------------------------------------------ export
    def _export_rows(self):
        """Rows for export: [category, a_row, a_key, a_cmp, b_row, b_key,
        b_cmp, reason, confidence, status]"""
        if self.result is None:
            return []
        res = self.result
        out = []
        cat1, cat2, cat3 = self.t("tab_cat1"), self.t("tab_cat2"), self.t("tab_cat3")
        for i in res.cat1_a():
            out.append([cat1, i + 2, self._key_display(self.table_a, i, "a"),
                        self._cmp_display(self.table_a, i, "a"),
                        "", "", "", "", "", ""])
        for i in res.cat1_b():
            out.append([cat1, "", "", "", i + 2,
                        self._key_display(self.table_b, i, "b"),
                        self._cmp_display(self.table_b, i, "b"), "", "", ""])
        for dp in res.diff_pairs:
            for d in dp.diffs:
                out.append([cat2, dp.a + 2,
                            self._key_display(self.table_a, dp.a, "a"), str(d["va"]),
                            dp.b + 2, self._key_display(self.table_b, dp.b, "b"),
                            str(d["vb"]),
                            "%s: %s → %s" % (self.table_a.headers[d["ca"]], d["va"], d["vb"]),
                            "", self.t("status_accepted") if dp.origin != "exact" else ""])
        for cand in res.candidates:
            a_disp = " + ".join("#%d %s" % (i + 2, self._key_display(self.table_a, i, "a")) for i in cand.a_rows)
            b_disp = " + ".join("#%d %s" % (i + 2, self._key_display(self.table_b, i, "b")) for i in cand.b_rows)
            out.append([cat3, a_disp, "", "", b_disp, "", "",
                        self._reason_text(cand),
                        "" if cand.confidence is None else cand.confidence,
                        self.t("status_" + cand.status)])
        if self.include_ok.isChecked():
            for ai, bi in res.ok_pairs:
                out.append([self.t("tab_ok"), ai + 2,
                            self._key_display(self.table_a, ai, "a"),
                            self._cmp_display(self.table_a, ai, "a"),
                            bi + 2, self._key_display(self.table_b, bi, "b"),
                            self._cmp_display(self.table_b, bi, "b"), "", "", ""])
        return out

    def _export(self, kind):
        rows = self._export_rows()
        if not rows:
            return
        headers = [self.t("exp_cat"), self.t("hdr_row"), self.t("hdr_a"), "",
                   self.t("hdr_row"), self.t("hdr_b"), "",
                   self.t("hdr_reason"), self.t("hdr_conf"), self.t("exp_status")]
        table = core.Table(headers, [[str(c) for c in r] for r in rows])
        if kind == "csv":
            path, _ = QFileDialog.getSaveFileName(
                self, self.t("save_as"), "differences.csv", "CSV (*.csv)")
            if path:
                core.save_table_csv(table, path)
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, self.t("save_as"), "differences.xlsx", "Excel (*.xlsx)")
            if path:
                core.save_table_xlsx(table, path)
        if path:
            self.status_label.setText(path)

    def _report_text(self):
        res, cfg = self.result, self.result_cfg
        c = res.counts()
        lines = [self.t("rep_title"), "=" * 40]
        lines.append("%s: A=%s / B=%s" % (
            self.t("rep_keys"),
            " + ".join(self.table_a.headers[a] for a, _ in cfg["key_pairs"]),
            " + ".join(self.table_b.headers[b] for _, b in cfg["key_pairs"])))
        lines.append("%s: %s" % (self.t("rep_tol"), core.fmt_decimal(cfg["tolerance"])))
        lines.append("")
        lines.append("[%s]" % self.t("rep_counts"))
        lines.append(self.t("summary_fmt", ta=c["total_a"], tb=c["total_b"],
                            ok=c["ok"], diff=c["diff"], c1a=c["cat1_a"],
                            c1b=c["cat1_b"], c3=c["cat3"]))
        lines.append("")
        lines.append("[%s]" % self.t("tab_cat1"))
        for i in res.cat1_a():
            lines.append("A #%d %s | %s" % (i + 2, self._key_display(self.table_a, i, "a"),
                                            self._cmp_display(self.table_a, i, "a")))
        for i in res.cat1_b():
            lines.append("B #%d %s | %s" % (i + 2, self._key_display(self.table_b, i, "b"),
                                            self._cmp_display(self.table_b, i, "b")))
        lines.append("")
        lines.append("[%s]" % self.t("tab_cat2"))
        for dp in res.diff_pairs:
            for d in dp.diffs:
                lines.append("#%d/%d %s: %s -> %s" % (
                    dp.a + 2, dp.b + 2, self.table_a.headers[d["ca"]], d["va"], d["vb"]))
        lines.append("")
        lines.append("[%s]" % self.t("tab_cat3"))
        for cand in res.candidates:
            a_disp = " + ".join("#%d %s" % (i + 2, self._key_display(self.table_a, i, "a")) for i in cand.a_rows)
            b_disp = " + ".join("#%d %s" % (i + 2, self._key_display(self.table_b, i, "b")) for i in cand.b_rows)
            lines.append("A %s ⇄ B %s | %s | %s" % (
                a_disp, b_disp, self._reason_text(cand),
                self.t("status_" + cand.status)))
        if res.houjin_pairs:
            lines.append("")
            lines.append("[%s]" % self.t("rep_houjin"))
            for ai, bi, number in res.houjin_pairs:
                lines.append("A #%d %s ⇄ B #%d %s | %s" % (
                    ai + 2, self._key_display(self.table_a, ai, "a"),
                    bi + 2, self._key_display(self.table_b, bi, "b"),
                    self.t("reason_houjin", number=number)))
        lines.append("")
        lines.append(self.t("rep_note"))
        return "\n".join(lines)

    def _save_report(self):
        if self.result is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, self.t("save_as"), "report.txt", "Text (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self._report_text())
            self.status_label.setText(path)


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
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
