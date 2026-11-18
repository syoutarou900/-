# -*- coding: utf-8 -*-
"""GlobalHours — world-time band checker (main window).

Design: a "world time band" map. Each partner gets one 24-hour
band (night -> dawn -> day -> dusk -> night gradient) with their
business hours glowing amber; your own band is pinned on top. One
shared cursor — set by the date/time field or the time slider —
sweeps every band at once, so each partner's local time, day/night
and business-hours status is visible at a glance. Weekend and
holiday bands are dimmed and badged. Overlapping candidate slots
appear as glowing chips under the bands; clicking a chip copies a
proposal message in the partner's language. Partner details and
editing live in an overlay card opened from the band.

Semi-automatic by design: the app only checks and proposes. It
never sends anything; the human decides when to make contact.

RTL note: surrounding layout mirrors for Arabic, but the painted
band timeline always runs 00:00 (left) -> 24:00 (right) so stacked
bands stay comparable (see bands.py).
"""

from __future__ import annotations

import math
import os
import sys
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, available_timezones

from PySide6.QtCore import (
    QDate, QDateTime, QPointF, QRectF, QSize, QTime, Qt, Signal,
)
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QIcon, QPainter, QPainterPath,
    QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDateEdit, QDateTimeEdit, QDialog,
    QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QSlider,
    QSpinBox, QTextEdit, QTimeEdit, QVBoxLayout, QWidget,
)

import appinfo
import bands as bandmod
import data as master
import fonts
import i18n
import theme
import tzcore
from tzcore import AppState, Partner, OwnSettings


def fmt_dt(dt: datetime, lang: str = "en") -> str:
    return i18n.fmt_datetime(dt, lang)


def fmt_range(start: datetime, end: datetime, lang: str = "en") -> str:
    return f"{fmt_dt(start, lang)} – {end.strftime('%H:%M')}"


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _theme_icon(theme_name: str) -> QIcon:
    """QPainter-drawn icon for the theme toggle button (no emoji
    glyphs). Shows the theme you switch TO: a sun while the dark
    theme is active, a crescent moon while the light theme is."""
    size = 52
    pm = QPixmap(size, size)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx = cy = size / 2.0
    if theme_name == "dark":
        amber = QColor("#F5A623")
        p.setPen(QPen(amber, 3.2, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        for deg in range(0, 360, 45):
            rad = math.radians(deg)
            p.drawLine(QPointF(cx + 13.5 * math.cos(rad),
                               cy + 13.5 * math.sin(rad)),
                       QPointF(cx + 18.5 * math.cos(rad),
                               cy + 18.5 * math.sin(rad)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(amber)
        p.drawEllipse(QRectF(cx - 8.5, cy - 8.5, 17, 17))
    else:
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        path.addEllipse(QRectF(cx - 12, cy - 12, 24, 24))
        path.addEllipse(QRectF(cx - 4, cy - 15, 24, 24))
        p.fillPath(path, QColor("#42538A"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#F5A623"))
        p.drawEllipse(QRectF(cx + 7, cy - 10, 4.5, 4.5))
    p.end()
    return QIcon(pm)


# ----------------------------------------------------------------------
# Partner overlay card (details + add / edit form)
# ----------------------------------------------------------------------

class PartnerDialog(QDialog):
    def __init__(self, lang: str, partner: Partner | None = None,
                 detail_lines: list | None = None, parent=None):
        super().__init__(parent)
        self.lang = lang
        self.delete_requested = False
        self.setWindowTitle(i18n.t(lang, "dlg_edit" if partner else "dlg_add"))
        self.setModal(True)
        layout = QVBoxLayout(self)

        if detail_lines:
            card = QLabel("\n".join(detail_lines))
            card.setStyleSheet(
                f"background: {theme.PANEL}; border: 1px solid {theme.LINE};"
                "border-radius: 10px; padding: 10px 12px;")
            layout.addWidget(card)

        form = QFormLayout()
        layout.addLayout(form)
        self.name_edit = QLineEdit(partner.name if partner else "")
        form.addRow(i18n.t(lang, "f_name"), self.name_edit)

        self.country_combo = QComboBox()
        for c in master.COUNTRIES:
            self.country_combo.addItem(f"{c['name']} ({c['code']})",
                                       c["code"])
        form.addRow(i18n.t(lang, "f_country"), self.country_combo)

        self.city_combo = QComboBox()
        form.addRow(i18n.t(lang, "f_city"), self.city_combo)

        self.zone_label = QLabel()
        form.addRow(i18n.t(lang, "f_zone"), self.zone_label)

        self.start_edit = QTimeEdit()
        self.start_edit.setDisplayFormat("HH:mm")
        self.start_edit.setMinimumWidth(86)
        self.end_edit = QTimeEdit()
        self.end_edit.setDisplayFormat("HH:mm")
        self.end_edit.setMinimumWidth(86)
        hours = QWidget()
        hl = QHBoxLayout(hours)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(self.start_edit)
        hl.addWidget(QLabel("–"))
        hl.addWidget(self.end_edit)
        hl.addStretch(1)
        form.addRow(i18n.t(lang, "work_hours"), hours)

        self.lang_combo = QComboBox()
        self.lang_combo.addItem(i18n.t(lang, "auto"), "")
        for code, name in i18n.LANGS:
            self.lang_combo.addItem(name, code)
        form.addRow(i18n.t(lang, "f_lang"), self.lang_combo)

        self.country_combo.currentIndexChanged.connect(self._fill_cities)
        self.city_combo.currentIndexChanged.connect(self._update_zone)

        if partner:
            idx = self.country_combo.findData(partner.country_code)
            self.country_combo.setCurrentIndex(max(idx, 0))
            self._fill_cities()
            cidx = self.city_combo.findText(partner.city)
            self.city_combo.setCurrentIndex(max(cidx, 0))
            self.start_edit.setTime(QTime.fromString(partner.work_start, "HH:mm"))
            self.end_edit.setTime(QTime.fromString(partner.work_end, "HH:mm"))
            lidx = self.lang_combo.findData(partner.lang)
            self.lang_combo.setCurrentIndex(max(lidx, 0))
        else:
            self._fill_cities()
            self.start_edit.setTime(QTime(9, 0))
            self.end_edit.setTime(QTime(18, 0))
        self._update_zone()

        btn_row = QHBoxLayout()
        if partner:
            del_btn = QPushButton(i18n.t(lang, "delete"))
            del_btn.clicked.connect(self._on_delete)
            btn_row.addWidget(del_btn)
        btn_row.addStretch(1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            i18n.t(lang, "save"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            i18n.t(lang, "cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        btn_row.addWidget(buttons)
        layout.addLayout(btn_row)

    def _on_delete(self):
        ans = QMessageBox.question(
            self, self.windowTitle(), i18n.t(self.lang, "delete_confirm"))
        if ans == QMessageBox.StandardButton.Yes:
            self.delete_requested = True
            self.accept()

    def _fill_cities(self):
        code = self.country_combo.currentData()
        country = master.country_by_code(code)
        self.city_combo.clear()
        if country:
            for city, zone in country["cities"]:
                self.city_combo.addItem(city, zone)
        self._update_zone()

    def _update_zone(self):
        self.zone_label.setText(self.city_combo.currentData() or "")

    def result_partner(self) -> Partner:
        return Partner(
            name=self.name_edit.text().strip() or self.city_combo.currentText(),
            country_code=self.country_combo.currentData(),
            city=self.city_combo.currentText(),
            zone=self.city_combo.currentData(),
            work_start=self.start_edit.time().toString("HH:mm"),
            work_end=self.end_edit.time().toString("HH:mm"),
            lang=self.lang_combo.currentData() or "",
        )


# ----------------------------------------------------------------------
# Own-settings overlay card
# ----------------------------------------------------------------------

class OwnSettingsDialog(QDialog):
    def __init__(self, lang: str, own: OwnSettings, parent=None):
        super().__init__(parent)
        self.lang = lang
        self.setWindowTitle(i18n.t(lang, "own_group"))
        self.setModal(True)
        form = QFormLayout(self)
        self.country_combo = QComboBox()
        for c in master.COUNTRIES:
            self.country_combo.addItem(f"{c['name']} ({c['code']})",
                                       c["code"])
        idx = self.country_combo.findData(own.country_code)
        self.country_combo.setCurrentIndex(max(idx, 0))
        form.addRow(i18n.t(lang, "own_country"), self.country_combo)

        self.zone_combo = QComboBox()
        self.zone_combo.setEditable(True)
        for z in sorted(available_timezones()):
            self.zone_combo.addItem(z)
        zidx = self.zone_combo.findText(own.zone)
        if zidx >= 0:
            self.zone_combo.setCurrentIndex(zidx)
        else:
            self.zone_combo.setCurrentText(own.zone)
        form.addRow(i18n.t(lang, "own_zone"), self.zone_combo)

        self.start_edit = QTimeEdit(QTime.fromString(own.work_start, "HH:mm"))
        self.start_edit.setDisplayFormat("HH:mm")
        self.end_edit = QTimeEdit(QTime.fromString(own.work_end, "HH:mm"))
        self.end_edit.setDisplayFormat("HH:mm")
        hours = QWidget()
        hl = QHBoxLayout(hours)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(self.start_edit)
        hl.addWidget(QLabel("–"))
        hl.addWidget(self.end_edit)
        hl.addStretch(1)
        form.addRow(i18n.t(lang, "work_hours"), hours)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            i18n.t(lang, "save"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            i18n.t(lang, "cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def accept(self):
        zone_name = self.zone_combo.currentText().strip()
        try:
            ZoneInfo(zone_name)
        except Exception:
            QMessageBox.warning(self, self.windowTitle(),
                                i18n.t(self.lang, "invalid_zone"))
            return
        super().accept()

    def result_own(self) -> OwnSettings:
        return OwnSettings(
            zone=self.zone_combo.currentText().strip() or "UTC",
            country_code=self.country_combo.currentData() or "JP",
            work_start=self.start_edit.time().toString("HH:mm"),
            work_end=self.end_edit.time().toString("HH:mm"),
        )


# ----------------------------------------------------------------------
# One band row: label block + painted band
# ----------------------------------------------------------------------

class BandRow(QWidget):
    edit_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        label_box = QWidget()
        label_box.setFixedWidth(252)
        lv = QVBoxLayout(label_box)
        lv.setContentsMargins(10, 6, 6, 6)
        lv.setSpacing(1)
        name_row = QHBoxLayout()
        self.name_label = QLabel()
        self.name_label.setStyleSheet("font-size: 15px; font-weight: 700;")
        name_row.addWidget(self.name_label)
        name_row.addStretch(1)
        self.edit_btn = QPushButton()
        # width follows the label text (e.g. German "Bearbeiten"
        # is much wider than 64px) with 64px as the minimum
        self.edit_btn.setMinimumWidth(64)
        self.edit_btn.clicked.connect(self.edit_clicked.emit)
        name_row.addWidget(self.edit_btn)
        lv.addLayout(name_row)
        self.place_label = QLabel()
        lv.addWidget(self.place_label)
        time_row = QHBoxLayout()
        self.time_label = QLabel("00:00")
        # The clock gets a real font object (not a stylesheet) so it
        # can carry the tabular-numbers feature: every digit is the
        # same width and the time never jitters as it changes.
        self.apply_time_font("ja")
        time_row.addWidget(self.time_label)
        self.date_label = QLabel()
        time_row.addWidget(self.date_label)
        time_row.addStretch(1)
        lv.addLayout(time_row)
        self.status_label = QLabel()
        # long holiday names wrap instead of being clipped
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-size: 13px; font-weight: 600;")
        lv.addWidget(self.status_label)
        self.dst_label = QLabel()
        self.dst_label.setWordWrap(True)
        lv.addWidget(self.dst_label)
        lv.addStretch(1)
        lay.addWidget(label_box)

        self.band = bandmod.BandWidget()
        lay.addWidget(self.band, 1)
        self.restyle()

    def apply_time_font(self, lang: str):
        """(Re-)set the big clock font for `lang`: Bold (a real face
        in both bundled families — the old stylesheet asked for
        weight 800, which neither family ships, so Qt synthesised
        a smeared fake bold), 30 px, tabular digits, antialiased."""
        self.time_label.setFont(fonts.make_font(
            lang, pixel_size=30,
            weight=fonts.ROLE_WEIGHTS["heading"], tabular=True))

    def restyle(self):
        """(Re-)apply the theme-dependent label colours. Called on
        construction and whenever the theme is toggled."""
        pal = theme.palette()
        soft = f"font-size: 12px; color: {pal['SUBINK']};"
        self.place_label.setStyleSheet(soft)
        self.date_label.setStyleSheet(soft)
        self.dst_label.setStyleSheet(
            f"font-size: 12px; color: {pal['WARN_AMBER']};")


# ----------------------------------------------------------------------
# Main window
# ----------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.lang = state.lang if state.lang in i18n.LANG_CODES else "ja"
        self.theme_name = (state.theme if state.theme in theme.THEME_NAMES
                           else "dark")
        self._selected = 0 if state.partners else -1
        self._slots: list[tzcore.Slot] = []
        self._proposal_dt: tuple[datetime, datetime] | None = None
        self._partner_rows: list[BandRow] = []
        self._build_ui()
        self.retranslate()
        self.refresh_all()

    # ---------------- construction ----------------

    def _build_ui(self):
        self.setWindowIcon(QIcon(os.path.join(
            fonts.assets_dir(), "icon.png")))
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # header
        header = QWidget()
        header.setObjectName("headerBar")
        self.header = header
        hl = QHBoxLayout(header)
        hl.setContentsMargins(14, 9, 14, 9)
        icon_label = QLabel()
        icon_label.setPixmap(QPixmap(os.path.join(
            fonts.assets_dir(), "icon.png")).scaled(
                30, 30, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        hl.addWidget(icon_label)
        self.title_label = QLabel()
        hl.addWidget(self.title_label)
        hl.addStretch(1)
        self.add_btn = QPushButton()
        self.add_btn.setProperty("class", "primary")
        self.add_btn.clicked.connect(self._add_partner)
        hl.addWidget(self.add_btn)
        self.theme_btn = QPushButton()
        self.theme_btn.setFixedSize(44, 34)
        self.theme_btn.setIconSize(QSize(26, 26))
        self.theme_btn.clicked.connect(self._toggle_theme)
        hl.addWidget(self.theme_btn)
        self.lang_combo = QComboBox()
        for code, name in i18n.LANGS:
            self.lang_combo.addItem(name, code)
        self.lang_combo.setCurrentIndex(
            max(self.lang_combo.findData(self.lang), 0))
        self.lang_combo.currentIndexChanged.connect(self._on_lang_changed)
        hl.addWidget(self.lang_combo)
        root.addWidget(header)

        # cursor controls
        controls = QWidget()
        cl = QHBoxLayout(controls)
        cl.setContentsMargins(14, 10, 14, 2)
        self.dt_label = QLabel()
        self.dt_label.setStyleSheet("font-size: 15px; font-weight: 700;")
        cl.addWidget(self.dt_label)
        self.dt_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self.dt_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.dt_edit.setCalendarPopup(True)
        self.dt_edit.dateTimeChanged.connect(self._on_dt_changed)
        cl.addWidget(self.dt_edit)
        self.now_btn = QPushButton()
        self.now_btn.clicked.connect(
            lambda: self.dt_edit.setDateTime(QDateTime.currentDateTime()))
        cl.addWidget(self.now_btn)
        cl.addStretch(1)
        root.addWidget(controls)

        slider_row = QWidget()
        sl = QHBoxLayout(slider_row)
        sl.setContentsMargins(14, 0, 14, 6)
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, 1439)
        self.time_slider.setValue(
            QDateTime.currentDateTime().time().hour() * 60
            + QDateTime.currentDateTime().time().minute())
        self.time_slider.valueChanged.connect(self._on_slider)
        sl.addWidget(self.time_slider)
        root.addWidget(slider_row)

        self.time_warn_label = QLabel()
        root.addWidget(self.time_warn_label)

        # bands (scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.bands_host = QWidget()
        self.bands_layout = QVBoxLayout(self.bands_host)
        self.bands_layout.setContentsMargins(14, 4, 14, 8)
        self.bands_layout.setSpacing(10)
        scroll.setWidget(self.bands_host)
        root.addWidget(scroll, 1)

        self.own_row = BandRow()
        self.own_row.edit_btn.clicked.connect(self._edit_own)
        self.bands_layout.addWidget(self.own_row)
        self.no_partners_label = QLabel()
        self.bands_layout.addWidget(self.no_partners_label)
        self.bands_layout.addStretch(1)

        # candidate chips + proposal
        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(14, 2, 14, 12)
        srow = QHBoxLayout()
        self.slots_title = QLabel()
        self.slots_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        srow.addWidget(self.slots_title)
        self.slot_date = QDateEdit(QDate.currentDate())
        self.slot_date.setCalendarPopup(True)
        self.slot_date.setDisplayFormat("yyyy-MM-dd")
        srow.addWidget(self.slot_date)
        self.slot_days = QSpinBox()
        self.slot_days.setRange(1, 14)
        self.slot_days.setValue(5)
        srow.addWidget(self.slot_days)
        self.slot_duration = QComboBox()
        for m in (30, 45, 60, 90, 120):
            self.slot_duration.addItem(f"{m}", m)
        self.slot_duration.setCurrentIndex(2)
        srow.addWidget(self.slot_duration)
        self.find_btn = QPushButton()
        self.find_btn.setProperty("class", "primary")
        self.find_btn.clicked.connect(self.refresh_slots)
        srow.addWidget(self.find_btn)
        self.slot_status = QLabel()
        srow.addWidget(self.slot_status)
        srow.addStretch(1)
        bl.addLayout(srow)

        self.chips_host = bandmod.FlowHost()
        self.chips_layout = self.chips_host.flow()
        chips_scroll = QScrollArea()
        chips_scroll.setWidgetResizable(True)
        chips_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        chips_scroll.setFixedHeight(162)
        chips_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        chips_scroll.setWidget(self.chips_host)
        bl.addWidget(chips_scroll)

        prow = QHBoxLayout()
        self.proposal_title = QLabel()
        self.proposal_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        prow.addWidget(self.proposal_title)
        self.proposal_lang_combo = QComboBox()
        self.proposal_lang_combo.addItem("Auto", "")
        for code, name in i18n.LANGS:
            self.proposal_lang_combo.addItem(name, code)
        self.proposal_lang_combo.currentIndexChanged.connect(
            lambda _i: self.refresh_proposal())
        prow.addWidget(self.proposal_lang_combo)
        self.copy_btn = QPushButton()
        self.copy_btn.clicked.connect(self._copy_proposal)
        prow.addWidget(self.copy_btn)
        self.copied_label = QLabel()
        prow.addWidget(self.copied_label)
        prow.addStretch(1)
        bl.addLayout(prow)
        self.proposal_edit = QTextEdit()
        self.proposal_edit.setMinimumHeight(104)
        self.proposal_edit.setMaximumHeight(130)
        bl.addWidget(self.proposal_edit)
        root.addWidget(bottom)
        self._apply_theme_styles()

    # ---------------- theme ----------------

    def _apply_theme_styles(self):
        """(Re-)apply every theme-dependent inline style. The app
        stylesheet itself is swapped by theme.apply_theme(); the
        labels below carry per-widget stylesheets, so they are
        refreshed here on construction and on every toggle."""
        pal = theme.palette()
        self.header.setStyleSheet(
            f"#headerBar {{ background: {pal['HEADER']}; }}")
        self.title_label.setStyleSheet(
            f"color: {pal['HEADER_INK']}; font-size: 20px;"
            " font-weight: 700;")
        self.time_warn_label.setStyleSheet(
            f"color: {pal['WARN_AMBER']}; font-size: 13px;"
            "padding: 0 14px 4px 14px;")
        self.slot_status.setStyleSheet(f"color: {pal['SUBINK']};")
        self.copied_label.setStyleSheet(f"color: {pal['OK_GREEN']};")
        self.no_partners_label.setStyleSheet(
            f"color: {pal['SUBINK']};")
        self.theme_btn.setIcon(_theme_icon(self.theme_name))
        self.theme_btn.setToolTip(i18n.t(self.lang, "theme_button"))
        self.own_row.restyle()
        for row in self._partner_rows:
            row.restyle()

    def _toggle_theme(self):
        """One click: swap dark <-> light instantly, in place, and
        remember the choice for the next launch."""
        self.theme_name = ("light" if self.theme_name == "dark"
                           else "dark")
        self.state.theme = self.theme_name
        theme.apply_theme(QApplication.instance(), self.theme_name)
        self._save()
        self._apply_theme_styles()
        self.refresh_bands()
        self.refresh_slots()
        self._settle_layout()

    # ---------------- helpers ----------------

    def _own(self) -> OwnSettings:
        return self.state.own

    def _instant(self) -> datetime:
        own = self._own()
        qdt = self.dt_edit.dateTime()
        naive = datetime(qdt.date().year(), qdt.date().month(),
                         qdt.date().day(), qdt.time().hour(),
                         qdt.time().minute())
        try:
            zone = ZoneInfo(own.zone)
        except Exception:
            zone = ZoneInfo("UTC")
        return naive.replace(tzinfo=zone)

    def _save(self):
        self.state.lang = self.lang
        tzcore.save_state(self.state)

    def _selected_partner(self) -> Partner | None:
        if 0 <= self._selected < len(self.state.partners):
            return self.state.partners[self._selected]
        return None

    # ---------------- refresh ----------------

    def _settle_layout(self):
        """Force the window layout to recompute now. Rebuilding the
        band rows / chips (or flipping the layout direction for RTL
        languages) invalidates layouts; without this, one frame can
        be painted with stale, compressed geometry."""
        lay = self.centralWidget().layout()
        if lay is not None:
            lay.activate()

    def refresh_all(self):
        self._rebuild_partner_rows()
        self.refresh_bands()
        self.refresh_slots()
        self.refresh_proposal()
        self._settle_layout()

    def _rebuild_partner_rows(self):
        for row in self._partner_rows:
            self.bands_layout.removeWidget(row)
            row.hide()  # never paint a ghost while deletion pends
            row.setParent(None)
            row.deleteLater()
        self._partner_rows = []
        # insert after own_row (index 1..), before hint/stretch
        for idx, _p in enumerate(self.state.partners):
            row = BandRow()
            row.apply_time_font(self.lang)
            row.band.clicked.connect(
                lambda i=idx: self._select_partner(i))
            row.edit_btn.clicked.connect(
                lambda _checked=False, i=idx: self._edit_partner(i))
            self.bands_layout.insertWidget(1 + idx, row)
            self._partner_rows.append(row)
        self.no_partners_label.setVisible(not self.state.partners)

    def _status_for(self, zone_name, country_code, weekend,
                    work_start, work_end, instant):
        """(local_dt, status_kind, holiday_name, dst_date) for a side.
        status_kind in {"ok", "outside", "weekend", "holiday"}."""
        local = instant.astimezone(ZoneInfo(zone_name))
        day = local.date()
        hol = tzcore.holiday_on(country_code, day)
        weekend = tzcore.is_weekend(weekend, day)
        in_hours = tzcore._within(day, local, work_start, work_end)
        if hol:
            kind = "holiday"
        elif weekend:
            kind = "weekend"
        elif in_hours:
            kind = "ok"
        else:
            kind = "outside"
        dst = tzcore.dst_change_near(zone_name, day, within_days=7)
        return local, kind, hol, dst

    def _paint_row(self, row: BandRow, name, place, zone_name,
                   country_code, weekend, work_start, work_end,
                   instant, selected):
        local, kind, hol, dst = self._status_for(
            zone_name, country_code, weekend, work_start, work_end,
            instant)
        lang = self.lang
        row.name_label.setText(name)
        row.place_label.setText(place)
        row.time_label.setText(local.strftime("%H:%M"))
        row.date_label.setText(i18n.fmt_date(local, lang))
        if kind == "ok":
            text, colour = i18n.t(lang, "status_ok"), theme.OK_GREEN
        elif kind == "weekend":
            text, colour = i18n.t(lang, "status_weekend"), theme.BAD_RED
        elif kind == "holiday":
            text = f"{i18n.t(lang, 'status_holiday')}: {hol}"
            colour = theme.BAD_RED
        else:
            text, colour = i18n.t(lang, "status_outside"), theme.WARN_AMBER
        row.status_label.setText(f"● {text}")
        row.status_label.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {colour};")
        row.dst_label.setText(
            i18n.t(lang, "dst_warning", date=dst.strftime("%Y-%m-%d"))
            if dst else "")
        badge = ""
        if kind == "holiday":
            badge = hol or ""
        elif kind == "weekend":
            badge = i18n.t(lang, "status_weekend")
        row.band.configure(zone_name, work_start, work_end, instant,
                           dimmed=kind in ("weekend", "holiday"),
                           badge=badge, selected=selected)
        row.edit_btn.setText(i18n.t(lang, "edit"))

    def refresh_bands(self):
        instant = self._instant()
        own = self._own()
        # input guidance: nonexistent / duplicated wall times (DST)
        naive = instant.replace(tzinfo=None)
        kind = tzcore.classify_local(own.zone, naive)
        if kind == "gap":
            self.time_warn_label.setText(i18n.t(self.lang, "time_gap"))
        elif kind == "ambiguous":
            self.time_warn_label.setText(
                i18n.t(self.lang, "time_ambiguous"))
        else:
            self.time_warn_label.setText("")
        oc = own.country
        place = f"{own.zone} · {oc['name'] if oc else own.country_code}"
        self._paint_row(self.own_row, i18n.t(self.lang, "own_label"),
                        place, own.zone, own.country_code, own.weekend,
                        own.work_start, own.work_end, instant,
                        selected=False)
        for idx, partner in enumerate(self.state.partners):
            if idx >= len(self._partner_rows):
                break
            place = (f"{partner.city}, {partner.country_code} · "
                     f"{partner.zone}")
            self._paint_row(self._partner_rows[idx], partner.name, place,
                            partner.zone, partner.country_code,
                            partner.weekend, partner.work_start,
                            partner.work_end, instant,
                            selected=(idx == self._selected))

    def _select_partner(self, idx: int):
        self._selected = idx
        self._proposal_dt = None
        self.refresh_bands()
        self.refresh_slots()
        self.refresh_proposal()

    # ---------------- cursor controls ----------------

    def _on_dt_changed(self, qdt: QDateTime):
        self.time_slider.blockSignals(True)
        self.time_slider.setValue(qdt.time().hour() * 60 + qdt.time().minute())
        self.time_slider.blockSignals(False)
        self._proposal_dt = None
        self.refresh_bands()
        self.refresh_proposal()

    def _on_slider(self, value: int):
        qdt = self.dt_edit.dateTime()
        qdt.setTime(QTime(value // 60, value % 60))
        self.dt_edit.setDateTime(qdt)   # triggers _on_dt_changed

    # ---------------- partners CRUD ----------------

    def _detail_lines(self, partner: Partner) -> list:
        instant = self._instant()
        res = tzcore.check_partner(instant, self._own(), partner)
        lang = self.lang
        if res.holiday_name:
            status = f"{i18n.t(lang, 'status_holiday')}: {res.holiday_name}"
        elif res.is_weekend:
            status = i18n.t(lang, "status_weekend")
        elif res.in_business_hours:
            status = i18n.t(lang, "status_ok")
        else:
            status = i18n.t(lang, "status_outside")
        lines = [
            f"{partner.name} — {partner.city}, {partner.country_code}",
            f"{i18n.t(lang, 'col_local_time')}: {fmt_dt(res.local_dt, lang)} "
            f"({res.offset_label}, {tzcore.fmt_diff_hours(res.diff_hours)})",
            f"{i18n.t(lang, 'col_status')}: {status}",
        ]
        if res.dst_change_date:
            lines.append(i18n.t(
                lang, "dst_warning",
                date=res.dst_change_date.strftime("%Y-%m-%d")))
        return lines

    def _add_partner(self):
        dlg = PartnerDialog(self.lang, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.state.partners.append(dlg.result_partner())
            self._selected = len(self.state.partners) - 1
            self._save()
            self.refresh_all()

    def _edit_partner(self, idx: int):
        if not (0 <= idx < len(self.state.partners)):
            return
        partner = self.state.partners[idx]
        dlg = PartnerDialog(self.lang, partner,
                            detail_lines=self._detail_lines(partner),
                            parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if dlg.delete_requested:
                del self.state.partners[idx]
                self._selected = min(self._selected,
                                     len(self.state.partners) - 1)
            else:
                self.state.partners[idx] = dlg.result_partner()
                self._selected = idx
            self._save()
            self.refresh_all()

    def _edit_own(self):
        dlg = OwnSettingsDialog(self.lang, self._own(), parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.state.own = dlg.result_own()
            self._save()
            self.refresh_all()

    # ---------------- slots & chips ----------------

    def refresh_slots(self):
        # clear old chips
        while self.chips_layout.count():
            item = self.chips_layout.takeAt(0)
            if item and item.widget():
                item.widget().hide()  # no ghost while deletion pends
                item.widget().deleteLater()
        self._slots = []
        partner = self._selected_partner()
        if partner is None:
            self.slot_status.setText(i18n.t(self.lang, "select_partner"))
            return
        qd = self.slot_date.date()
        start_day = date(qd.year(), qd.month(), qd.day())
        slots = tzcore.find_candidate_slots(
            self._own(), partner, start_day, self.slot_days.value(),
            duration_min=self.slot_duration.currentData(), max_results=24)
        self._slots = slots
        for s in slots:
            text = (f"{i18n.fmt_chip(s.own_start, self.lang)}"
                    f"–{s.own_end.strftime('%H:%M')}"
                    f"  →  {s.partner_start.strftime('%H:%M')}"
                    f"–{s.partner_end.strftime('%H:%M')}")
            chip = QPushButton(text)
            chip.setProperty("class", "primary")
            # Time strings read left-to-right in every UI language
            # (same rule as the band axis), even in RTL layouts.
            chip.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            # Size the chip from the real font metrics of the font
            # it will render with, plus its padding, so the full
            # text is always visible — no clipping, uniform height.
            cfont = QFont(chip.font())
            cfont.setPixelSize(15)
            cfont.setWeight(QFont.Weight.Bold)
            fonts.polish_font(cfont, tabular=True)
            chip.setFont(cfont)
            text_w = QFontMetrics(cfont).horizontalAdvance(text)
            chip.setFixedSize(text_w + 48, 44)
            # the local font-size pins the rendered size to the
            # measured font (the app stylesheet's button rule would
            # otherwise override it and clip the text)
            chip.setStyleSheet("font-size: 15px; padding: 6px 16px;")
            chip.clicked.connect(
                lambda _c=False, slot=s: self._chip_clicked(slot))
            self.chips_layout.addWidget(chip)
        if slots:
            self.slot_status.setText(
                i18n.t(self.lang, "slot_count", count=len(slots)))
        else:
            self.slot_status.setText(i18n.t(self.lang, "no_slots"))

    def _chip_clicked(self, slot: tzcore.Slot):
        self._proposal_dt = (slot.own_start, slot.partner_start)
        self.refresh_proposal()
        self._copy_proposal()

    # ---------------- proposal ----------------

    def refresh_proposal(self):
        partner = self._selected_partner()
        if partner is None:
            self.proposal_edit.setPlainText("")
            return
        own = self._own()
        if self._proposal_dt:
            own_dt, partner_dt = self._proposal_dt
        else:
            own_dt = self._instant()
            partner_dt = own_dt.astimezone(ZoneInfo(partner.zone))
        lang = (self.proposal_lang_combo.currentData()
                or partner.proposal_lang)
        own_city = own.zone.split("/")[-1].replace("_", " ")
        text = i18n.proposal(
            lang, name=partner.name,
            own_time=fmt_dt(own_dt, lang), own_city=own_city,
            partner_time=fmt_dt(partner_dt, lang),
            partner_city=partner.city)
        self.proposal_edit.setPlainText(text)

    def _copy_proposal(self):
        QApplication.clipboard().setText(self.proposal_edit.toPlainText())
        self.copied_label.setText(i18n.t(self.lang, "copied"))

    # ---------------- language ----------------

    def _on_lang_changed(self):
        code = self.lang_combo.currentData()
        if code and code != self.lang:
            self.lang = code
            self._save()
            self.retranslate()
            self.refresh_all()

    def retranslate(self):
        lang = self.lang
        app = QApplication.instance()
        fonts.apply_language_font(app, lang)
        self.own_row.apply_time_font(lang)
        for row in self._partner_rows:
            row.apply_time_font(lang)
        app.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if lang in i18n.RTL_LANGS
            else Qt.LayoutDirection.LeftToRight)
        self.setWindowTitle(appinfo.display_name(lang))
        self.title_label.setText(appinfo.display_name(lang))
        self.add_btn.setText(i18n.t(lang, "add"))
        self.theme_btn.setToolTip(i18n.t(lang, "theme_button"))
        self.dt_label.setText(i18n.t(lang, "date_time"))
        self.now_btn.setText(i18n.t(lang, "now_button"))
        self.slots_title.setText(i18n.t(lang, "slots_group"))
        self.find_btn.setText(i18n.t(lang, "find_slots"))
        self.proposal_title.setText(i18n.t(lang, "proposal_group"))
        self.copy_btn.setText(i18n.t(lang, "copy_button"))
        self.copied_label.setText("")
        self.no_partners_label.setText(i18n.t(lang, "no_partners"))


def main() -> int:
    app = QApplication(sys.argv)
    state = tzcore.load_state()
    theme.apply_theme(app, state.theme)
    fonts.apply_language_font(app, "ja")
    win = MainWindow(state)
    win.resize(1280, 880)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
