# -*- coding: utf-8 -*-
"""UniList GUI (PySide6, single codebase for Windows and macOS).

Flow: open a customer/vendor list -> check/correct the proposed column
roles -> find candidate duplicate groups (exact matches after
deterministic normalization only) -> compare side by side and choose
the value to keep per field -> merge ONLY the groups a human approves.
The original file is never modified; results are exported to a new
file, merges can be undone, sessions can be saved and resumed.
"""
import json
import os
import sys

from PySide6.QtCore import Qt, QSettings, QStandardPaths
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QFileDialog, QGroupBox,
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QRadioButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

import core
import normalize as nz
from appinfo import APP_ID, APP_VERSION, display_name
from i18n import LANG_NAMES, LANG_ORDER, RTL_LANGS, STRINGS, tr

TIER_BG = {"A": "#fde8e8", "B": "#fff6da", "C": "#eef1f4"}
TIER_FG = {"A": "#b02a2a", "B": "#8a6d00", "C": "#5a6672"}

# Resolve typed role words in ANY UI language (plus the synonym table
# in core.resolve_role, which covers many more variants).
_ROLE_TEXT_LOOKUP = {}
for _lang in LANG_ORDER:
    for _role in core.ROLES:
        _txt = STRINGS[_lang].get(f"role_{_role}")
        if _txt:
            _ROLE_TEXT_LOOKUP[core._role_key(_txt)] = _role


def resolve_role_input(text):
    role = core.resolve_role(text)
    if role:
        return role
    return _ROLE_TEXT_LOOKUP.get(core._role_key(text or ""))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("Muse", APP_ID)
        self.lang = self.settings.value("language", "ja")
        if self.lang not in LANG_ORDER:
            self.lang = "ja"
        self.engine = core.Engine()
        self.groups = []
        self.current_group = None
        self._radio_groups = []      # per field: (QButtonGroup, [values])
        self._merged_labels = []     # per field: QLabel in merged column
        self._global_notdup = self._load_global_notdup()
        self.engine.not_dup |= self._global_notdup

        self.setWindowTitle(display_name(self.lang))
        self.resize(1240, 780)
        self.setAcceptDrops(True)
        self._build_ui()
        self.apply_language()

    # -- not-duplicate global store -------------------------------------------
    def _notdup_path(self):
        base = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation)
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, "notdup.json")

    def _load_global_notdup(self):
        try:
            with open(self._notdup_path(), "r", encoding="utf-8") as fh:
                return {frozenset(p) for p in json.load(fh)}
        except Exception:
            return set()

    def _save_global_notdup(self):
        try:
            with open(self._notdup_path(), "w", encoding="utf-8") as fh:
                json.dump([sorted(p) for p in self.engine.not_dup],
                          fh, ensure_ascii=False)
        except Exception:
            pass

    # -- UI construction ---------------------------------------------------------
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        main = QVBoxLayout(root)

        head = QHBoxLayout()
        title_box = QVBoxLayout()
        self.title_label = QLabel()
        self.title_label.setStyleSheet(
            "font-size: 20px; font-weight: 800; color: #1a6b4a;")
        self.subtitle_label = QLabel()
        self.subtitle_label.setStyleSheet("color: #555;")
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)
        head.addLayout(title_box, 1)
        self.lang_caption = QLabel()
        head.addWidget(self.lang_caption)
        self.lang_combo = QComboBox()
        for code in LANG_ORDER:
            self.lang_combo.addItem(LANG_NAMES[code], code)
        self.lang_combo.setCurrentIndex(LANG_ORDER.index(self.lang))
        self.lang_combo.currentIndexChanged.connect(self._on_lang_changed)
        head.addWidget(self.lang_combo)
        main.addLayout(head)

        bar = QHBoxLayout()
        self.btn_open = QPushButton()
        self.btn_open.clicked.connect(self.open_file_dialog)
        bar.addWidget(self.btn_open)
        self.btn_save_session = QPushButton()
        self.btn_save_session.clicked.connect(self.save_session_dialog)
        bar.addWidget(self.btn_save_session)
        self.btn_load_session = QPushButton()
        self.btn_load_session.clicked.connect(self.load_session_dialog)
        bar.addWidget(self.btn_load_session)
        self.file_label = QLabel()
        bar.addWidget(self.file_label, 1)
        self.rows_label = QLabel()
        bar.addWidget(self.rows_label)
        main.addLayout(bar)

        split = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        lv = QVBoxLayout(left)
        self.columns_box = QGroupBox()
        cl = QVBoxLayout(self.columns_box)
        self.columns_table = QTableWidget(0, 2)
        self.columns_table.verticalHeader().setVisible(False)
        cl.addWidget(self.columns_table)
        lv.addWidget(self.columns_box)
        self.btn_detect = QPushButton()
        self.btn_detect.setStyleSheet(
            "font-weight: 700; padding: 8px; background: #1a6b4a;"
            " color: white; border-radius: 6px;")
        self.btn_detect.clicked.connect(self.run_detect)
        lv.addWidget(self.btn_detect)
        lv.addStretch(1)
        split.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        self.groups_box = QGroupBox()
        gl = QVBoxLayout(self.groups_box)
        self.groups_table = QTableWidget(0, 4)
        self.groups_table.verticalHeader().setVisible(False)
        self.groups_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.groups_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection)
        self.groups_table.itemSelectionChanged.connect(self._on_group_selected)
        gl.addWidget(self.groups_table)
        rv.addWidget(self.groups_box, 3)

        self.preview_box = QGroupBox()
        pv = QVBoxLayout(self.preview_box)
        self.preview_hint = QLabel()
        self.preview_hint.setWordWrap(True)
        pv.addWidget(self.preview_hint)
        self.preview_table = QTableWidget(0, 0)
        self.preview_table.verticalHeader().setVisible(False)
        pv.addWidget(self.preview_table)
        prow = QHBoxLayout()
        self.btn_apply = QPushButton()
        self.btn_apply.clicked.connect(self.apply_merge)
        prow.addWidget(self.btn_apply)
        self.btn_notdup = QPushButton()
        self.btn_notdup.clicked.connect(self.mark_not_duplicate)
        prow.addWidget(self.btn_notdup)
        prow.addStretch(1)
        pv.addLayout(prow)
        rv.addWidget(self.preview_box, 4)
        split.addWidget(right)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 5)
        main.addWidget(split, 1)

        bottom = QHBoxLayout()
        self.btn_undo = QPushButton()
        self.btn_undo.clicked.connect(self.undo_merge)
        bottom.addWidget(self.btn_undo)
        self.btn_export = QPushButton()
        self.btn_export.clicked.connect(self.export_dialog)
        bottom.addWidget(self.btn_export)
        self.btn_export_log = QPushButton()
        self.btn_export_log.clicked.connect(self.export_log_dialog)
        bottom.addWidget(self.btn_export_log)
        self.merged_label = QLabel()
        bottom.addWidget(self.merged_label)
        bottom.addStretch(1)
        main.addLayout(bottom)

        self.hint_label = QLabel()
        self.hint_label.setStyleSheet("color: #1a6b4a; font-weight: 600;")
        main.addWidget(self.hint_label)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        main.addWidget(self.status_label)

    # -- language ------------------------------------------------------------------
    def apply_language(self):
        lang = self.lang
        self.setWindowTitle(display_name(lang))
        self.title_label.setText(
            f"{display_name(lang)}  v{APP_VERSION}")
        self.subtitle_label.setText(tr(lang, "app_subtitle"))
        self.lang_caption.setText(tr(lang, "lang_label"))
        self.btn_open.setText(tr(lang, "btn_open"))
        self.btn_save_session.setText(tr(lang, "btn_save_session"))
        self.btn_load_session.setText(tr(lang, "btn_load_session"))
        self.columns_box.setTitle(tr(lang, "hdr_columns"))
        self.columns_table.setHorizontalHeaderLabels(
            [tr(lang, "col_column_name"), tr(lang, "col_role")])
        self.btn_detect.setText(tr(lang, "btn_detect"))
        self.groups_box.setTitle(tr(lang, "hdr_groups"))
        self.groups_table.setHorizontalHeaderLabels([
            tr(lang, "grp_col_tier"), tr(lang, "grp_col_reason"),
            tr(lang, "grp_col_count"), tr(lang, "grp_col_representative")])
        self.preview_box.setTitle(tr(lang, "hdr_preview"))
        self.preview_hint.setText(tr(lang, "lbl_select_group"))
        self.btn_apply.setText(tr(lang, "btn_apply_merge"))
        self.btn_notdup.setText(tr(lang, "btn_not_dup"))
        self.btn_undo.setText(tr(lang, "btn_undo"))
        self.btn_export.setText(tr(lang, "btn_export"))
        self.btn_export_log.setText(tr(lang, "btn_export_log"))
        self.hint_label.setText(tr(lang, "hint_human"))
        self._refresh_file_label()
        self._refresh_merged_label()
        self._render_columns()
        self._render_groups()
        self._clear_preview()
        app = QApplication.instance()
        if app:
            app.setLayoutDirection(
                Qt.LayoutDirection.RightToLeft if lang in RTL_LANGS
                else Qt.LayoutDirection.LeftToRight)

    def _on_lang_changed(self, index):
        self.lang = self.lang_combo.itemData(index)
        self.settings.setValue("language", self.lang)
        self.apply_language()

    # -- file loading ---------------------------------------------------------------
    def _last_dir(self):
        return self.settings.value("last_dir", os.path.expanduser("~"))

    def open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr(self.lang, "dlg_open_title"), self._last_dir(),
            tr(self.lang, "filter_data"))
        if path:
            self.load_file(path)

    def load_file(self, path):
        try:
            table = core.load_table(path)
        except Exception as exc:  # unreadable file
            self._status(tr(self.lang, "msg_error", detail=str(exc)))
            return
        self.settings.setValue("last_dir", os.path.dirname(path))
        self.engine.load(table, source_path=path)
        self.engine.not_dup |= self._global_notdup
        self.groups = []
        self.current_group = None
        self._render_columns()
        self._render_groups()
        self._clear_preview()
        self._refresh_file_label()
        self._refresh_merged_label()
        self._status(tr(self.lang, "msg_loaded",
                        name=os.path.basename(path),
                        count=len(self.engine.rows)))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.splitext(path)[1].lower() in (
                    ".csv", ".tsv", ".txt", ".xlsx", ".xlsm"):
                self.load_file(path)
                break

    def _refresh_file_label(self):
        if self.engine.source_path:
            self.file_label.setText(os.path.basename(self.engine.source_path))
            self.rows_label.setText(
                tr(self.lang, "lbl_rows_count", count=len(self.engine.rows)))
        else:
            self.file_label.setText(tr(self.lang, "lbl_no_file"))
            self.rows_label.setText("")

    def _refresh_merged_label(self):
        self.merged_label.setText(tr(
            self.lang, "lbl_merged_count",
            count=len(self.engine.merge_log)))

    def _status(self, text):
        self.status_label.setText(text)

    # -- columns / roles ------------------------------------------------------------
    def _render_columns(self):
        eng = self.engine
        self.columns_table.setRowCount(len(eng.headers))
        for ci, header in enumerate(eng.headers):
            item = QTableWidgetItem(header)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.columns_table.setItem(ci, 0, item)
            combo = QComboBox()
            combo.setEditable(True)
            for role in core.ROLES:
                combo.addItem(tr(self.lang, f"role_{role}"), role)
            combo.setCurrentText(tr(self.lang, f"role_{eng.roles[ci]}"))
            combo.currentIndexChanged.connect(
                lambda _i, c=ci, cb=combo: self._role_changed(c, cb))
            if combo.lineEdit() is not None:
                combo.lineEdit().editingFinished.connect(
                    lambda c=ci, cb=combo: self._role_changed(c, cb))
            self.columns_table.setCellWidget(ci, 1, combo)
        self.columns_table.resizeColumnsToContents()

    def _role_changed(self, ci, combo):
        role = combo.currentData()
        text = combo.currentText()
        resolved = resolve_role_input(text)
        if resolved is None:
            if role is None:
                role = "other"
            self._status(tr(self.lang, "msg_role_unresolved", text=text))
            resolved = role if role in core.ROLES else "other"
        if ci < len(self.engine.roles):
            self.engine.roles[ci] = resolved
        combo.blockSignals(True)
        combo.setCurrentText(tr(self.lang, f"role_{resolved}"))
        combo.blockSignals(False)

    def _collect_roles(self):
        roles = []
        for ci in range(self.columns_table.rowCount()):
            combo = self.columns_table.cellWidget(ci, 1)
            role = "other"
            if combo is not None:
                role = resolve_role_input(combo.currentText()) \
                    or combo.currentData() or "other"
            roles.append(role)
        if roles:
            self.engine.set_roles(roles)
        return roles

    # -- detection / groups ------------------------------------------------------------
    def run_detect(self):
        if not self.engine.headers:
            return
        roles = self._collect_roles()
        if not any(r in core.KEY_ROLES for r in roles):
            self._status(tr(self.lang, "msg_no_key_col"))
            return
        self.groups = self.engine.detect()
        self.current_group = None
        self._render_groups()
        self._clear_preview()
        self._refresh_file_label()
        if self.groups:
            self._status(tr(self.lang, "msg_groups_found",
                            count=len(self.groups)))
        else:
            self._status(tr(self.lang, "msg_no_groups"))

    def _reason_text(self, group):
        fields = ", ".join(tr(self.lang, f"role_{r}")
                           for r in group.reasons)
        text = tr(self.lang, "reason_matched", fields=fields)
        if group.tier == "C":
            text += " — " + tr(self.lang, "tier_c_note")
        return text

    def _representative(self, group):
        name_cols = [i for i, r in enumerate(self.engine.roles)
                     if r == "name"]
        if name_cols:
            for idx in group.row_indices:
                v = self.engine.rows[idx]["values"][name_cols[0]]
                if v.strip():
                    return v
        idx = group.row_indices[0]
        return self.engine.rows[idx]["values"][0] if self.engine.headers else ""

    def _render_groups(self):
        t = self.groups_table
        t.setRowCount(len(self.groups))
        for gi, g in enumerate(self.groups):
            tier_item = QTableWidgetItem(tr(self.lang, f"tier_{g.tier}"))
            tier_item.setForeground(QColor(TIER_FG[g.tier]))
            font = tier_item.font()
            font.setBold(True)
            tier_item.setFont(font)
            cells = [tier_item,
                     QTableWidgetItem(self._reason_text(g)),
                     QTableWidgetItem(str(len(g.row_indices))),
                     QTableWidgetItem(self._representative(g))]
            for col, item in enumerate(cells):
                item.setBackground(QColor(TIER_BG[g.tier]))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                t.setItem(gi, col, item)
        t.resizeColumnsToContents()

    def _on_group_selected(self):
        rows = self.groups_table.selectionModel().selectedRows()
        if not rows:
            return
        gi = rows[0].row()
        if 0 <= gi < len(self.groups):
            self.current_group = self.groups[gi]
            self._render_preview(self.current_group)

    # -- merge preview ------------------------------------------------------------------
    def _clear_preview(self):
        self.preview_table.setRowCount(0)
        self.preview_table.setColumnCount(0)
        self._radio_groups = []
        self._merged_labels = []
        self.preview_hint.setText(tr(self.lang, "lbl_select_group"))

    def _render_preview(self, group):
        eng = self.engine
        members = [eng.rows[i] for i in group.row_indices]
        n_fields = len(eng.headers)
        self.preview_table.setColumnCount(len(members) + 2)
        headers = [tr(self.lang, "col_field")]
        for mi, m in enumerate(members):
            headers.append(self._member_title(m, mi))
        headers.append(tr(self.lang, "col_merged"))
        self.preview_table.setHorizontalHeaderLabels(headers)
        self.preview_table.setRowCount(n_fields)
        self._radio_groups = []
        self._merged_labels = []
        self.preview_hint.setText(self._reason_text(group))
        for ci in range(n_fields):
            field_item = QTableWidgetItem(eng.headers[ci])
            field_item.setFlags(
                field_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.preview_table.setItem(ci, 0, field_item)
            group_btns = QButtonGroup(self)
            group_btns.setExclusive(True)
            values = []
            default_btn = None
            for mi, m in enumerate(members):
                value = m["values"][ci]
                values.append(value)
                rb = QRadioButton(value if value.strip() else "—")
                if not value.strip():
                    rb.setEnabled(False)
                rb.toggled.connect(
                    lambda checked, r=ci: self._update_merged_cell(r))
                self.preview_table.setCellWidget(ci, mi + 1, rb)
                group_btns.addButton(rb)
                if default_btn is None and value.strip():
                    default_btn = rb
            if default_btn is not None:
                default_btn.setChecked(True)
            self._radio_groups.append((group_btns, values))
            lbl = QLabel()
            self.preview_table.setCellWidget(ci, len(members) + 1, lbl)
            self._merged_labels.append(lbl)
            self._update_merged_cell(ci)
        self.preview_table.resizeColumnsToContents()

    def _member_title(self, member, mi):
        name_cols = [i for i, r in enumerate(self.engine.roles)
                     if r == "name"]
        if name_cols:
            v = member["values"][name_cols[0]]
            if v.strip():
                return v
        return tr(self.lang, "member_label", n=mi + 1)

    def _update_merged_cell(self, ci):
        if ci >= len(self._radio_groups):
            return
        group_btns, values = self._radio_groups[ci]
        checked = group_btns.checkedButton()
        text = ""
        if checked is not None:
            # find which member the checked button belongs to by order
            for bi, btn in enumerate(group_btns.buttons()):
                if btn is checked:
                    text = values[bi]
                    break
        self._merged_labels[ci].setText(text)

    def _current_choices(self):
        choices = {}
        for ci, (group_btns, values) in enumerate(self._radio_groups):
            checked = group_btns.checkedButton()
            val = ""
            if checked is not None:
                for bi, btn in enumerate(group_btns.buttons()):
                    if btn is checked:
                        val = values[bi]
                        break
            if not val:
                val = self.engine.default_choices(
                    self.current_group).get(ci, "") \
                    if self.current_group else ""
            choices[ci] = val
        return choices

    # -- actions ----------------------------------------------------------------------
    def apply_merge(self):
        if self.current_group is None:
            self._status(tr(self.lang, "msg_select_group"))
            return
        choices = self._current_choices()
        self.engine.apply_merge(self.current_group, choices)
        self.current_group = None
        self._status(tr(self.lang, "msg_merged"))
        self._refresh_merged_label()
        self.run_detect()

    def mark_not_duplicate(self):
        if self.current_group is None:
            self._status(tr(self.lang, "msg_select_group"))
            return
        self.engine.mark_not_duplicate(self.current_group)
        self._save_global_notdup()
        self.current_group = None
        self._status(tr(self.lang, "msg_notdup"))
        self.run_detect()

    def undo_merge(self):
        entry = self.engine.undo_last_merge()
        if entry is not None:
            self._status(tr(self.lang, "msg_undone"))
            self._refresh_merged_label()
            self._refresh_file_label()
            self.run_detect()

    def export_dialog(self):
        if not self.engine.headers:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr(self.lang, "dlg_export_title"), self._last_dir(),
            tr(self.lang, "filter_export"))
        if not path:
            return
        if self.engine.source_path and os.path.abspath(path) == \
                os.path.abspath(self.engine.source_path):
            QMessageBox.warning(self, display_name(self.lang),
                                tr(self.lang, "msg_overwrite_blocked"))
            return
        table = self.engine.export_table()
        try:
            if path.lower().endswith(".csv"):
                core.save_table_csv(table, path)
            else:
                if not path.lower().endswith(".xlsx"):
                    path += ".xlsx"
                core.save_table_xlsx(table, path)
        except Exception as exc:
            self._status(tr(self.lang, "msg_error", detail=str(exc)))
            return
        self._status(tr(self.lang, "msg_exported",
                        name=os.path.basename(path)))

    def export_log_dialog(self):
        if not self.engine.merge_log:
            self._status(tr(self.lang, "msg_no_groups"))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr(self.lang, "dlg_export_title"), self._last_dir(),
            "CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        records = self.engine.log_records()
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                import csv as _csv
                w = _csv.writer(fh, lineterminator="\r\n")
                w.writerow(["when", "tier", "reasons", "members",
                            "member_count", "chosen"])
                for r in records:
                    w.writerow([r["when"], r["tier"], r["reasons"],
                                r["members"], r["member_count"], r["chosen"]])
        except Exception as exc:
            self._status(tr(self.lang, "msg_error", detail=str(exc)))
            return
        self._status(tr(self.lang, "msg_log_exported",
                        name=os.path.basename(path)))

    def save_session_dialog(self):
        if not self.engine.headers:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr(self.lang, "dlg_save_session"), self._last_dir(),
            tr(self.lang, "filter_session"))
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        self._collect_roles()
        try:
            self.engine.save_session(path)
        except Exception as exc:
            self._status(tr(self.lang, "msg_error", detail=str(exc)))
            return
        self._status(tr(self.lang, "msg_session_saved"))

    def load_session_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr(self.lang, "dlg_load_session"), self._last_dir(),
            tr(self.lang, "filter_session"))
        if not path:
            return
        try:
            self.engine.load_session(path)
        except Exception as exc:
            self._status(tr(self.lang, "msg_error", detail=str(exc)))
            return
        self.engine.not_dup |= self._global_notdup
        self.groups = []
        self.current_group = None
        self._render_columns()
        self._render_groups()
        self._clear_preview()
        self._refresh_file_label()
        self._refresh_merged_label()
        self._status(tr(self.lang, "msg_session_loaded"))


def _under_wine():
    """True only under Wine (ntdll exports wine_get_version only there).
    Used solely for Wine-only stability workarounds; real Windows and
    macOS are untouched."""
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
        # at startup. The FreeType engine avoids that path. This branch
        # never runs on real Windows or macOS.
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
    app.setOrganizationName("Muse")
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
