# -*- coding: utf-8 -*-
"""VersionDetective — main window.

Design: a floating pill command bar on top, a narrow rail of
case-file cards on the side, and a version genealogy (family tree)
as the centrepiece, with a side-by-side "spread" diff underneath.
No band header, no list-and-button-rows house style.

The app only ever READS the files it analyses.  It never deletes a
file and never rewrites one; the only writes are approved moves to an
archive folder (see mover.py) and the app's own settings/log.
"""

from __future__ import annotations

import ctypes
import os
import sys
from datetime import timezone

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

import analyzer
import fonts
import icons
import mover
import theme
from analyzer import FileInfo, Group
from appinfo import APP_ID, display_name
from genealogy import GenealogyCanvas, NodeView
from i18n import LANGS, RTL_LANGS, tr


def _fmt_dt(info: FileInfo) -> str:
    return info.effective_dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")


def _src_key(info: FileInfo) -> str:
    return {"office": "src_office", "pdf": "src_pdf"}.get(
        info.dt_source, "src_mtime")


# ----------------------------------------------------------------------
# Background scan
# ----------------------------------------------------------------------

class ScanWorker(QThread):
    progress = Signal(int, int)
    finished_scan = Signal(list)

    def __init__(self, paths):
        super().__init__()
        self._paths = paths
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        infos = []
        total = len(self._paths)
        for i, path in enumerate(self._paths):
            if self._cancel:
                break
            infos.append(analyzer.extract(path))
            if i % 10 == 0 or i == total - 1:
                self.progress.emit(i + 1, total)
        self.finished_scan.emit(infos)


# ----------------------------------------------------------------------
# Rail case card
# ----------------------------------------------------------------------

class CaseCard(QFrame):
    clicked = Signal(int)

    def __init__(self, gid: int):
        super().__init__()
        self.gid = gid
        self.setObjectName("railCard")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        theme.soft_shadow(self, blur=14, dy=2, alpha=16)
        self.setMinimumHeight(78)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(10)
        self.count = QLabel()
        self.count.setObjectName("railCount")
        lay.addWidget(self.count)
        right = QVBoxLayout()
        right.setSpacing(2)
        self.title = QLabel()
        self.title.setObjectName("railTitle")
        self.title.setWordWrap(False)
        self.badge = QLabel()
        self.meta = QLabel()
        self.meta.setObjectName("railMeta")
        self.meta.setWordWrap(True)
        right.addWidget(self.title)
        right.addWidget(self.badge)
        right.addWidget(self.meta)
        lay.addLayout(right, 1)

    def mousePressEvent(self, event):
        self.clicked.emit(self.gid)
        super().mousePressEvent(event)

    def set_selected(self, on: bool):
        self.setProperty("selected", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)


# ----------------------------------------------------------------------
# Archive proposal dialog
# ----------------------------------------------------------------------

class ArchiveDialog(QDialog):
    def __init__(self, parent, lang, members, archive_dir):
        super().__init__(parent)
        self.lang = lang
        self.members = members
        self.setWindowTitle(tr(lang, "move_title"))
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        hint = QLabel(tr(lang, "move_hint"))
        hint.setWordWrap(True)
        lay.addWidget(hint)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr(lang, "archive_folder")))
        self.dir_edit = QLineEdit(archive_dir)
        row.addWidget(self.dir_edit, 1)
        choose = QPushButton(tr(lang, "choose_folder"))
        choose.clicked.connect(self._choose)
        row.addWidget(choose)
        lay.addLayout(row)
        self.list = QListWidget()
        for info, checked in members:
            item = QListWidgetItem(info.name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if checked
                               else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, info.path)
            self.list.addItem(item)
        lay.addWidget(self.list, 1)
        btns = QHBoxLayout()
        self.undo_btn = QPushButton(tr(lang, "undo_move"))
        self.undo_btn.setIcon(icons.icon("undo", theme.INDIGO_DEEP))
        btns.addWidget(self.undo_btn)
        btns.addStretch(1)
        cancel = QPushButton(tr(lang, "cancel"))
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        self.exec_btn = QPushButton(tr(lang, "move_execute"))
        self.exec_btn.setObjectName("primary")
        self.exec_btn.setIcon(icons.icon("archive", "#FFFFFF"))
        btns.addWidget(self.exec_btn)
        lay.addLayout(btns)

    def _choose(self):
        d = QFileDialog.getExistingDirectory(
            self, tr(self.lang, "archive_folder"),
            self.dir_edit.text())
        if d:
            self.dir_edit.setText(d)

    def checked_paths(self):
        out = []
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                out.append(item.data(Qt.ItemDataRole.UserRole))
        return out


# ----------------------------------------------------------------------
# Main window
# ----------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = mover.load_settings()
        self.lang = self.settings.get("lang", "ja")
        if self.lang not in dict(LANGS):
            self.lang = "ja"
        self.infos: list[FileInfo] = []
        self.groups: list[Group] = []
        self.singles: list[FileInfo] = []
        self.selected_gid = None
        self.selected_path = None
        self.rejected_pairs: set = set()
        self.forced_merges: set = set()
        self.merge_source_gid = None
        self.root_folder = ""
        self.worker: ScanWorker | None = None
        self._build_ui()
        self.retranslate()
        self.setAcceptDrops(True)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        self.setWindowTitle(display_name(self.lang))
        self.resize(1220, 780)
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        # ---- floating pill command bar ----
        bar = QFrame()
        bar.setObjectName("commandBar")
        theme.soft_shadow(bar, blur=24, dy=4, alpha=28)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(20, 10, 14, 10)
        bl.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.cmd_title = QLabel()
        self.cmd_title.setObjectName("cmdTitle")
        self.cmd_tagline = QLabel()
        self.cmd_tagline.setObjectName("cmdTagline")
        titles.addWidget(self.cmd_title)
        titles.addWidget(self.cmd_tagline)
        bl.addLayout(titles)
        bl.addSpacing(8)
        self.open_btn = QPushButton()
        self.open_btn.setObjectName("primary")
        self.open_btn.setIcon(icons.icon("folder", "#FFFFFF"))
        self.open_btn.clicked.connect(self.choose_folder)
        bl.addWidget(self.open_btn)
        self.recursive_chk = QCheckBox()
        self.recursive_chk.setChecked(
            bool(self.settings.get("recursive", True)))
        bl.addWidget(self.recursive_chk)
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("searchEdit")
        self.search_edit.textChanged.connect(self._rebuild_rail)
        bl.addWidget(self.search_edit, 1)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(170)
        self.progress.hide()
        bl.addWidget(self.progress)
        self.cancel_btn = QPushButton()
        self.cancel_btn.hide()
        self.cancel_btn.clicked.connect(self._cancel_scan)
        bl.addWidget(self.cancel_btn)
        self.lang_label = QLabel()
        bl.addWidget(self.lang_label)
        self.lang_combo = QComboBox()
        self.lang_combo.setObjectName("langCombo")
        for code, name in LANGS:
            self.lang_combo.addItem(name, code)
        self.lang_combo.setCurrentIndex(
            [c for c, _ in LANGS].index(self.lang))
        self.lang_combo.currentIndexChanged.connect(self._lang_changed)
        bl.addWidget(self.lang_combo)
        root.addWidget(bar)

        # ---- status row ----
        srow = QHBoxLayout()
        self.root_label = QLabel()
        self.root_label.setObjectName("railMeta")
        srow.addWidget(self.root_label)
        self.status_label = QLabel()
        self.status_label.setObjectName("statusLabel")
        srow.addWidget(self.status_label, 1)
        self.warn_label = QLabel()
        self.warn_label.setObjectName("warnLabel")
        srow.addWidget(self.warn_label)
        root.addLayout(srow)

        # ---- body: rail + main panel ----
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        root.addWidget(split, 1)

        rail = QWidget()
        rail.setFixedWidth(272)
        rl = QVBoxLayout(rail)
        rl.setContentsMargins(2, 2, 6, 2)
        rl.setSpacing(8)
        self.rail_head = QLabel()
        self.rail_head.setObjectName("railHead")
        rl.addWidget(self.rail_head)
        self.rail_scroll = QScrollArea()
        self.rail_scroll.setWidgetResizable(True)
        self.rail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.rail_host = QWidget()
        self.rail_lay = QVBoxLayout(self.rail_host)
        self.rail_lay.setContentsMargins(0, 0, 0, 0)
        self.rail_lay.setSpacing(8)
        self.rail_lay.addStretch(1)
        self.rail_scroll.setWidget(self.rail_host)
        rl.addWidget(self.rail_scroll, 1)
        self.singles_head = QLabel()
        self.singles_head.setObjectName("railHead")
        rl.addWidget(self.singles_head)
        self.singles_list = QListWidget()
        self.singles_list.setMaximumHeight(110)
        rl.addWidget(self.singles_list)
        self.errors_head = QLabel()
        self.errors_head.setObjectName("railHead")
        rl.addWidget(self.errors_head)
        self.errors_list = QListWidget()
        self.errors_list.setMaximumHeight(110)
        rl.addWidget(self.errors_list)
        split.addWidget(rail)

        panel = QFrame()
        panel.setObjectName("panel")
        theme.soft_shadow(panel, blur=24, dy=4, alpha=22)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(18, 14, 18, 14)
        pl.setSpacing(10)

        head = QHBoxLayout()
        self.group_title = QLabel()
        self.group_title.setObjectName("bigTitle")
        self.group_title.setWordWrap(True)
        head.addWidget(self.group_title, 1)
        self.kind_badge = QLabel()
        head.addWidget(self.kind_badge)
        self.branch_badge = QLabel()
        self.branch_badge.setObjectName("branchBadge")
        self.branch_badge.hide()
        head.addWidget(self.branch_badge)
        self.merge_btn = QPushButton()
        self.merge_btn.setIcon(icons.icon("branch", theme.INDIGO_DEEP))
        self.merge_btn.clicked.connect(self._toggle_merge_mode)
        head.addWidget(self.merge_btn)
        self.archive_btn = QPushButton()
        self.archive_btn.setObjectName("accent")
        self.archive_btn.setIcon(icons.icon("archive", theme.AMBER))
        self.archive_btn.clicked.connect(self.open_archive)
        head.addWidget(self.archive_btn)
        pl.addLayout(head)

        self.sim_label = QLabel()
        self.sim_label.setObjectName("reasonText")
        pl.addWidget(self.sim_label)

        self.reasons_title = QLabel()
        self.reasons_title.setObjectName("panelTitle")
        pl.addWidget(self.reasons_title)
        self.reasons_label = QLabel()
        self.reasons_label.setObjectName("reasonText")
        self.reasons_label.setWordWrap(True)
        pl.addWidget(self.reasons_label)

        self.canvas = GenealogyCanvas()
        self.canvas.nodeClicked.connect(self._node_clicked)
        self.gene_scroll = QScrollArea()
        self.gene_scroll.setWidget(self.canvas)
        self.gene_scroll.setWidgetResizable(False)
        self.gene_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.gene_scroll.setMinimumHeight(160)
        pl.addWidget(self.gene_scroll)

        drow = QHBoxLayout()
        self.node_detail = QLabel()
        self.node_detail.setObjectName("nodeDetail")
        self.node_detail.setWordWrap(True)
        drow.addWidget(self.node_detail, 1)
        self.set_latest_btn = QPushButton()
        self.set_latest_btn.setIcon(icons.icon("star", theme.INDIGO_DEEP))
        self.set_latest_btn.clicked.connect(self._set_latest)
        drow.addWidget(self.set_latest_btn)
        self.remove_btn = QPushButton()
        self.remove_btn.clicked.connect(self._remove_selected)
        drow.addWidget(self.remove_btn)
        pl.addLayout(drow)

        crow = QHBoxLayout()
        self.from_label = QLabel()
        crow.addWidget(self.from_label)
        self.from_combo = QComboBox()
        self.from_combo.setMinimumWidth(170)
        crow.addWidget(self.from_combo)
        crow.addWidget(QLabel("→"))
        self.to_label = QLabel()
        crow.addWidget(self.to_label)
        self.to_combo = QComboBox()
        self.to_combo.setMinimumWidth(170)
        crow.addWidget(self.to_combo)
        self.compare_btn = QPushButton()
        self.compare_btn.setObjectName("primary")
        self.compare_btn.setIcon(icons.icon("diff", "#FFFFFF"))
        self.compare_btn.clicked.connect(self._show_diff)
        crow.addWidget(self.compare_btn)
        crow.addStretch(1)
        self.diff_summary = QLabel()
        self.diff_summary.setObjectName("reasonText")
        crow.addWidget(self.diff_summary)
        pl.addLayout(crow)

        srow2 = QHBoxLayout()
        self.spread_old_head = QLabel()
        self.spread_old_head.setObjectName("spreadHead")
        srow2.addWidget(self.spread_old_head, 1)
        self.spread_new_head = QLabel()
        self.spread_new_head.setObjectName("spreadHead")
        srow2.addWidget(self.spread_new_head, 1)
        pl.addLayout(srow2)
        self.spread = QTableWidget(0, 2)
        self.spread.verticalHeader().setVisible(False)
        self.spread.horizontalHeader().setVisible(False)
        self.spread.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        pl.addWidget(self.spread, 1)
        split.addWidget(panel)
        split.setStretchFactor(1, 1)

    # ------------------------------------------------------------------
    # i18n
    # ------------------------------------------------------------------
    def t(self, key, **params):
        return tr(self.lang, key, **params)

    def _lang_changed(self, idx):
        code = self.lang_combo.itemData(idx)
        if code and code != self.lang:
            self.lang = code
            self.settings["lang"] = code
            mover.save_settings(self.settings)
            self.retranslate()

    def retranslate(self):
        app = QApplication.instance()
        if app is not None:
            fonts.apply_language_font(app, self.lang)
            # Re-polish the whole tree so existing widgets adopt the
            # (possibly new) font stack at once.  On some platforms
            # (seen with the frozen build under Wine) an application
            # font change alone does not re-resolve the families of
            # widgets that already exist; an explicit re-polish does.
            style = self.style()
            for widget in [self, *self.findChildren(QWidget)]:
                style.unpolish(widget)
                style.polish(widget)
            if self.lang in RTL_LANGS:
                app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            else:
                app.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setWindowTitle(display_name(self.lang))
        self.cmd_title.setText(display_name(self.lang))
        self.cmd_tagline.setText(self.t("app_tagline"))
        self.open_btn.setText(self.t("open_folder"))
        self.recursive_chk.setText(self.t("recursive"))
        self.search_edit.setPlaceholderText(self.t("search_groups"))
        self.cancel_btn.setText(self.t("cancel"))
        self.lang_label.setText(self.t("language"))
        self.rail_head.setText(self.t("rail_groups"))
        self.singles_head.setText(self.t("singles_title"))
        self.errors_head.setText(self.t("errors_title"))
        self.reasons_title.setText(self.t("reasons_title"))
        self.merge_btn.setText(self.t("merge_groups"))
        self.archive_btn.setText(self.t("archive_button"))
        self.set_latest_btn.setText(self.t("set_latest"))
        self.remove_btn.setText(self.t("remove_from_group"))
        self.from_label.setText(self.t("compare_from"))
        self.to_label.setText(self.t("compare_to"))
        self.compare_btn.setText(self.t("compare_button"))
        if not self.groups:
            self.status_label.setText(self.t("status_ready"))
            self.group_title.setText(self.t("genealogy"))
            self.reasons_label.setText(self.t("genealogy_empty"))
            self.canvas.set_data([], rtl=self.lang in RTL_LANGS,
                                 empty_text=self.t("empty_hint"))
        self._rebuild_rail()
        if self.selected_gid is not None and \
                self._group_by_id(self.selected_gid) is not None:
            self._show_group(self.selected_gid)
        self._update_root_label()

    def _update_root_label(self):
        if self.root_folder:
            self.root_label.setText(
                f"{self.t('root_label')}: {self.root_folder}")
        else:
            self.root_label.setText("")

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------
    def choose_folder(self):
        d = QFileDialog.getExistingDirectory(
            self, self.t("open_folder"), self.root_folder)
        if d:
            self.start_scan(d)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isdir(path):
                self.start_scan(path)
                return

    def start_scan(self, folder):
        if self.worker and self.worker.isRunning():
            return
        self.root_folder = folder
        self._update_root_label()
        paths = list(analyzer.scan_folder(
            folder, self.recursive_chk.isChecked()))
        self.settings["recursive"] = self.recursive_chk.isChecked()
        mover.save_settings(self.settings)
        if len(paths) > analyzer.WARN_FILE_COUNT:
            self.warn_label.setText(
                self.t("warn_many_files", n=len(paths)))
            ans = QMessageBox.question(
                self, self.t("group_candidate"),
                self.t("warn_many_files", n=len(paths)))
            if ans != QMessageBox.StandardButton.Yes:
                return
        else:
            self.warn_label.setText("")
        self.progress.setMaximum(max(1, len(paths)))
        self.progress.setValue(0)
        self.progress.show()
        self.cancel_btn.show()
        self.open_btn.setEnabled(False)
        self.status_label.setText(self.t("analyzing"))
        self.worker = ScanWorker(paths)
        self.worker.progress.connect(self._scan_progress)
        self.worker.finished_scan.connect(self._scan_done)
        self.worker.start()

    def _scan_progress(self, done, total):
        self.progress.setValue(done)
        self.status_label.setText(
            self.t("analyzing_count", done=done, total=total))

    def _cancel_scan(self):
        if self.worker:
            self.worker.cancel()

    def _scan_done(self, infos):
        self.progress.hide()
        self.cancel_btn.hide()
        self.open_btn.setEnabled(True)
        self.infos = infos
        self.selected_gid = None
        self.selected_path = None
        self.merge_source_gid = None
        self._regroup()
        self.status_label.setText(self.t(
            "status_done", files=len(infos), groups=len(self.groups)))
        if self.groups:
            self._show_group(self.groups[0].gid)

    def _regroup(self):
        self.groups, self.singles = analyzer.build_groups(
            self.infos, self.rejected_pairs, self.forced_merges)
        self._rebuild_rail()
        self._rebuild_singles_errors()

    # ------------------------------------------------------------------
    # Rail
    # ------------------------------------------------------------------
    @staticmethod
    def _clear_layout(lay):
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                # hide + unparent immediately: a deleteLater-only
                # widget can keep painting at its stale geometry
                # until the event loop gets to it
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def _rebuild_rail(self):
        self._clear_layout(self.rail_lay)
        query = self.search_edit.text().strip().lower()
        shown = 0
        for g in self.groups:
            title = g.title()
            if query and query not in title.lower() and not any(
                    query in m.name.lower() for m in g.members):
                continue
            shown += 1
            card = CaseCard(g.gid)
            card.count.setText(str(len(g.members)))
            card.title.setText(title)
            card.title.setToolTip(title)
            if g.kind == "exact":
                card.badge.setText(self.t("group_exact"))
                card.badge.setObjectName("kindExact")
            else:
                card.badge.setText(self.t("group_candidate"))
                card.badge.setObjectName("kindCandidate")
            card.badge.style().unpolish(card.badge)
            card.badge.style().polish(card.badge)
            card.meta.setText(self.t("group_files", n=len(g.members)))
            card.set_selected(g.gid == self.selected_gid)
            card.clicked.connect(self._card_clicked)
            self.rail_lay.addWidget(card)
        if self.groups and not shown:
            lbl = QLabel(self.t("no_groups_found"))
            lbl.setObjectName("railMeta")
            lbl.setWordWrap(True)
            self.rail_lay.addWidget(lbl)
        self.rail_lay.addStretch(1)

    def _rebuild_singles_errors(self):
        self.singles_list.clear()
        for info in self.singles:
            self.singles_list.addItem(QListWidgetItem(info.name))
        self.errors_list.clear()
        for info in self.infos:
            if info.status == "error":
                reason = self.t(
                    "err_" + (info.error_reason or "unreadable"))
                self.errors_list.addItem(
                    QListWidgetItem(f"{info.name} — {reason}"))

    def _card_clicked(self, gid):
        if self.merge_source_gid is not None and \
                gid != self.merge_source_gid:
            src = self._group_by_id(self.merge_source_gid)
            dst = self._group_by_id(gid)
            if src and dst and src.members and dst.members:
                self.forced_merges.add(frozenset(
                    (src.members[0].path, dst.members[0].path)))
            self.merge_source_gid = None
            self._regroup()
            self.status_label.setText(self.t("merge_done"))
            self._show_group(gid)
            return
        self.merge_source_gid = None
        self._show_group(gid)

    def _group_by_id(self, gid):
        for g in self.groups:
            if g.gid == gid:
                return g
        return None

    def _toggle_merge_mode(self):
        if self.selected_gid is None:
            return
        if self.merge_source_gid == self.selected_gid:
            self.merge_source_gid = None
            self.status_label.setText(self.t("status_ready"))
        else:
            self.merge_source_gid = self.selected_gid
            self.status_label.setText(self.t("merge_mode_on"))

    # ------------------------------------------------------------------
    # Group detail + genealogy
    # ------------------------------------------------------------------
    def _current_group(self):
        return self._group_by_id(self.selected_gid)

    def _caption_for(self, group, idx):
        members = group.members
        if idx == 0:
            return self.t("first_version")
        prev, cur = members[idx - 1], members[idx]
        s = analyzer.summarize_pair(prev, cur)
        if s["kind"] == "text":
            return self.t("chg_lines", a=s["added"], d=s["deleted"])
        if s["kind"] == "cells":
            n = s["changed_cells"] + s["added_cells"] + s["removed_cells"]
            return self.t("chg_cells", n=n)
        return ""

    def _show_group(self, gid):
        group = self._group_by_id(gid)
        if group is None:
            return
        self.selected_gid = gid
        verdict = analyzer.rank_latest(group)
        self._verdict = verdict
        self.group_title.setText(group.title())
        if group.kind == "exact":
            self.kind_badge.setText(self.t("group_exact"))
            self.kind_badge.setObjectName("kindExact")
            self.sim_label.setText("")
        else:
            self.kind_badge.setText(self.t("group_candidate"))
            self.kind_badge.setObjectName("kindCandidate")
            self.sim_label.setText(self.t(
                "similarity", pct=round(group.similarity * 100)))
        self.kind_badge.style().unpolish(self.kind_badge)
        self.kind_badge.style().polish(self.kind_badge)
        if verdict.branch:
            self.branch_badge.setText(self.t("branch_warning"))
            self.branch_badge.show()
        else:
            self.branch_badge.hide()

        # reasons text
        lines = []
        if verdict.candidate is not None:
            lines.append(
                f"{self.t('latest_candidate')}: {verdict.candidate.name}")
            if group.manual_latest:
                lines.append(self.t("manual_latest_badge"))
        for key, params in verdict.reasons:
            lines.append("• " + self.t(key, **params))
        self.reasons_label.setText("\n".join(lines))

        # genealogy nodes (chronological; members already sorted)
        branch_path = verdict.branch_with.path if verdict.branch else None
        cand_path = verdict.candidate.path if verdict.candidate else None
        member_paths = [m.path for m in group.members]
        if self.selected_path not in member_paths:
            self.selected_path = cand_path or (
                member_paths[-1] if member_paths else None)
        nodes = []
        for i, m in enumerate(group.members):
            # short datetime under the node; the source of the
            # datetime is spelled out in the reasons and the detail
            # line, so the tree itself stays readable
            dt_text = _fmt_dt(m)
            nodes.append(NodeView(
                path=m.path,
                number=i + 1,
                name=m.name,
                dt_text=dt_text,
                caption=self._caption_for(group, i),
                is_latest=(m.path == cand_path),
                is_manual=(m.path == group.manual_latest),
                is_branch=(m.path == branch_path),
                selected=(m.path == self.selected_path)))
        self.canvas.set_data(
            nodes, rtl=self.lang in RTL_LANGS,
            branch_label=self.t("branch_from") if verdict.branch else "")
        self.gene_scroll.setMinimumHeight(
            272 if verdict.branch else 172)
        self.gene_scroll.verticalScrollBar().setValue(0)
        self.gene_scroll.horizontalScrollBar().setValue(0)

        # compare combos
        self.from_combo.clear()
        self.to_combo.clear()
        for m in group.members:
            self.from_combo.addItem(m.name, m.path)
            self.to_combo.addItem(m.name, m.path)
        if group.members:
            self.from_combo.setCurrentIndex(0)
            if cand_path:
                self.to_combo.setCurrentIndex(
                    [m.path for m in group.members].index(cand_path))
            else:
                self.to_combo.setCurrentIndex(len(group.members) - 1)
        self._rebuild_rail()
        self._update_node_detail()
        self._show_diff()

    def _member(self, path):
        for info in self.infos:
            if info.path == path:
                return info
        return None

    def _node_clicked(self, path):
        self.selected_path = path
        group = self._current_group()
        if group is not None:
            self._show_group(group.gid)

    def _update_node_detail(self):
        info = self._member(self.selected_path) if self.selected_path \
            else None
        if info is None:
            self.node_detail.setText(self.t("detail_empty"))
            self.set_latest_btn.setEnabled(False)
            self.remove_btn.setEnabled(False)
            return
        bits = [self.t("selected_version", name=info.name),
                self.t("version_dt", dt=_fmt_dt(info),
                       src=self.t(_src_key(info))),
                f"{info.size / 1024:.1f} KB"]
        if info.status == "hash_only":
            bits.append(self.t("hash_only"))
        self.node_detail.setText("   ".join(bits))
        self.set_latest_btn.setEnabled(True)
        self.remove_btn.setEnabled(True)

    def _set_latest(self):
        group = self._current_group()
        if group is None or not self.selected_path:
            return
        group.manual_latest = self.selected_path
        self._show_group(group.gid)

    def _remove_selected(self):
        group = self._current_group()
        if group is None or not self.selected_path:
            return
        target = self.selected_path
        for m in group.members:
            if m.path != target:
                self.rejected_pairs.add(frozenset((target, m.path)))
        if group.manual_latest == target:
            group.manual_latest = ""
        self.selected_path = None
        keep = group.gid
        self._regroup()
        self.status_label.setText(self.t("removed_done"))
        g2 = self._group_by_id(keep)
        if g2 is not None:
            self._show_group(keep)
        elif self.groups:
            self._show_group(self.groups[0].gid)

    # ------------------------------------------------------------------
    # Spread diff
    # ------------------------------------------------------------------
    def _combo_path(self, combo):
        return combo.currentData()

    def _show_diff(self):
        group = self._current_group()
        if group is None:
            return
        a_path = self._combo_path(self.from_combo)
        b_path = self._combo_path(self.to_combo)
        a = self._member(a_path) if a_path else None
        b = self._member(b_path) if b_path else None
        self.spread.setRowCount(0)
        if a is None or b is None:
            self.diff_summary.setText("")
            return
        self.spread_old_head.setText(f"{self.t('spread_old')}: {a.name}")
        self.spread_new_head.setText(f"{self.t('spread_new')}: {b.name}")
        d = analyzer.diff_infos(a, b)
        if d.kind == "cells":
            self.spread.setColumnCount(4)
            self.spread.setHorizontalHeaderLabels([
                self.t("col_sheet"), self.t("col_cell"),
                self.t("col_before"), self.t("col_after")])
            self.spread.horizontalHeader().setVisible(True)
            self.diff_summary.setText("  ".join([
                self.t("diff_cells_changed", n=len(d.changed_cells)),
                self.t("diff_cells_added", n=d.added_cells),
                self.t("diff_cells_removed", n=d.removed_cells)]))
            rows = d.changed_cells[:400]
            self.spread.setRowCount(len(rows))
            for r, (sheet, coord, old, new) in enumerate(rows):
                for c, val in enumerate((sheet, coord, old, new)):
                    item = QTableWidgetItem(val)
                    if c == 2 and old:
                        item.setBackground(QColor(theme.DEL_BG))
                    if c == 3 and new:
                        item.setBackground(QColor(theme.ADD_BG))
                    self.spread.setItem(r, c, item)
            self.spread.resizeColumnsToContents()
            self.spread.horizontalHeader().setStretchLastSection(True)
            return
        self.spread.setColumnCount(2)
        self.spread.horizontalHeader().setVisible(False)
        if d.kind == "none":
            self.diff_summary.setText(self.t("diff_none"))
            return
        self.diff_summary.setText("  ".join([
            self.t("diff_added", n=d.added),
            self.t("diff_deleted", n=d.deleted)]))
        rows = self._spread_rows(a, b)
        self.spread.setRowCount(len(rows))
        for r, (left, right, kind) in enumerate(rows):
            li = QTableWidgetItem(left)
            ri = QTableWidgetItem(right)
            if kind == "del":
                li.setBackground(QColor(theme.DEL_BG))
            elif kind == "add":
                ri.setBackground(QColor(theme.ADD_BG))
            elif kind == "rep":
                li.setBackground(QColor(theme.DEL_BG))
                ri.setBackground(QColor(theme.ADD_BG))
            elif kind == "gap":
                li.setForeground(QColor(theme.SUBINK))
                ri.setForeground(QColor(theme.SUBINK))
            self.spread.setItem(r, 0, li)
            self.spread.setItem(r, 1, ri)
        from PySide6.QtWidgets import QHeaderView
        hdr = self.spread.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    @staticmethod
    def _spread_rows(a: FileInfo, b: FileInfo, context=2, cap=500):
        """Aligned (left, right, kind) rows: changed lines face each
        other across the spread; equal lines appear only as short
        context around the changes."""
        import difflib
        sm = difflib.SequenceMatcher(a=a.lines, b=b.lines,
                                     autojunk=False)
        rows = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                seg_a = a.lines[i1:i2]
                if len(seg_a) <= context * 2 + 1:
                    for line in seg_a:
                        rows.append((line, line, "ctx"))
                else:
                    for line in seg_a[:context]:
                        rows.append((line, line, "ctx"))
                    rows.append(("…", "…", "gap"))
                    for line in seg_a[-context:]:
                        rows.append((line, line, "ctx"))
                continue
            dels = a.lines[i1:i2]
            adds = b.lines[j1:j2]
            for k in range(max(len(dels), len(adds))):
                left = dels[k] if k < len(dels) else ""
                right = adds[k] if k < len(adds) else ""
                kind = "rep" if (k < len(dels) and k < len(adds)) else \
                    ("del" if k < len(dels) else "add")
                rows.append((left, right, kind))
            if len(rows) >= cap:
                break
        return rows[:cap]

    # ------------------------------------------------------------------
    # Archive moves
    # ------------------------------------------------------------------
    def open_archive(self):
        group = self._current_group()
        if group is None:
            return
        verdict = self._verdict if hasattr(self, "_verdict") else \
            analyzer.rank_latest(group)
        keep_path = None
        if verdict.candidate is not None:
            keep_path = verdict.candidate.path
        members = []
        for m in group.members:
            if keep_path is not None:
                members.append((m, m.path != keep_path))
            else:
                # branch: nothing pre-checked; the human decides all
                members.append((m, False))
        dlg = ArchiveDialog(self, self.lang, members,
                            self.settings.get("archive_dir", ""))
        dlg.exec_btn.clicked.connect(lambda: self._exec_archive(dlg))
        dlg.undo_btn.clicked.connect(lambda: self._undo_archive(dlg))
        dlg.exec()

    def _exec_archive(self, dlg):
        archive_dir = dlg.dir_edit.text().strip()
        if not archive_dir:
            QMessageBox.warning(self, self.t("move_title"),
                                self.t("no_archive"))
            return
        paths = dlg.checked_paths()
        if not paths:
            QMessageBox.warning(self, self.t("move_title"),
                                self.t("nothing_checked"))
            return
        ans = QMessageBox.question(
            self, self.t("confirm_move_title"),
            self.t("confirm_move_body", n=len(paths)))
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.settings["archive_dir"] = archive_dir
        mover.save_settings(self.settings)
        done, errors = mover.execute_moves(
            [(p, archive_dir) for p in paths])
        dlg.accept()
        if errors:
            QMessageBox.warning(
                self, self.t("move_title"),
                self.t("move_errors", n=len(errors)))
        self.status_label.setText(self.t("move_done", n=len(done)))
        if self.root_folder:
            self.start_scan(self.root_folder)

    def _undo_archive(self, dlg):
        done, errors = mover.undo_last_batch()
        if not done and not errors:
            QMessageBox.information(self, self.t("undo_move"),
                                    self.t("nothing_to_undo"))
            return
        dlg.accept()
        if errors:
            QMessageBox.warning(
                self, self.t("move_title"),
                self.t("move_errors", n=len(errors)))
        self.status_label.setText(self.t("undo_done", n=len(done)))
        if self.root_folder:
            self.start_scan(self.root_folder)


# ----------------------------------------------------------------------
# Entry point (with the Wine-only font workaround used by the family)
# ----------------------------------------------------------------------

def _under_wine():
    """True only under Wine (ntdll exports wine_get_version there).
    Used solely for Wine-only stability workarounds; real Windows is
    completely unaffected."""
    if sys.platform != "win32":
        return False
    try:
        return hasattr(ctypes.WinDLL("ntdll"), "wine_get_version")
    except Exception:
        return False


def main():
    args = list(sys.argv)
    if _under_wine():
        # Wine-only: Qt's native (DirectWrite) font engine can fault
        # in Wine 9.0 during font fallback; FreeType avoids it.
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
    fonts.register_fonts()
    theme.apply_theme(app)
    # Set the UI font BEFORE any widget exists: widgets resolve
    # their font families when they are first polished, and on some
    # platforms a later application-font change does not re-resolve
    # them (the frozen build under Wine kept the system default).
    _initial_lang = mover.load_settings().get("lang", "ja")
    if _initial_lang not in dict(LANGS):
        _initial_lang = "ja"
    fonts.apply_language_font(app, _initial_lang)
    if _under_wine():
        try:
            # The bundled fonts are registered above; only if they
            # somehow failed to load, fall back to a plain system
            # font (Wine's fallback chain was the crash risk, and
            # naming one concrete family avoids it).
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
    raise SystemExit(main())
