# -*- coding: utf-8 -*-
"""World-time band widgets for GlobalHours.

BandWidget paints one 24-hour band for a timezone: a night -> dawn
-> day -> dusk -> night gradient for the local day, the business
hours as a glowing amber segment, and a shared vertical cursor at
the currently selected instant. Weekend / holiday bands are dimmed
and carry a badge.

Colours come from the active theme (theme.palette()) at paint
time, so the one-click dark/light switch repaints every band in
place. The weekend/holiday veil is painted BEFORE the hour ticks,
the cursor and the badge, so those stay bright and readable on a
dimmed band; the badge text itself uses the theme's high-contrast
badge colours and is elided to always fit inside the band.

RTL note: the band's internal time axis is ALWAYS drawn 00:00 on
the left to 24:00 on the right, in every UI language including
Arabic. A time band is a map-like timeline: keeping one fixed
direction lets the eye compare stacked bands and follow the shared
cursor. Qt's RTL mirroring still applies to the surrounding layout
(labels, buttons), only the painted timeline keeps its direction.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import QLayout, QSizePolicy, QWidget

import fonts
import theme


def _rgba(spec) -> QColor:
    if isinstance(spec, str):
        return QColor(spec)
    return QColor(*spec)


def _minutes(hhmm: str) -> int:
    hh, mm = hhmm.split(":")
    return int(hh) * 60 + int(mm)


class BandWidget(QWidget):
    """One painted 24-hour band. Clicking selects it."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(84)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self._zone = ZoneInfo("UTC")
        self._work_start = "09:00"
        self._work_end = "18:00"
        self._instant: datetime | None = None
        self._dimmed = False
        self._badge = ""
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # -- configuration ------------------------------------------------
    def configure(self, zone_name: str, work_start: str, work_end: str,
                  instant: datetime, dimmed: bool, badge: str,
                  selected: bool):
        self._zone = ZoneInfo(zone_name)
        self._work_start = work_start
        self._work_end = work_end
        self._instant = instant
        self._dimmed = dimmed
        self._badge = badge
        self._selected = selected
        self.update()

    def mousePressEvent(self, event):  # noqa: N802 (Qt naming)
        self.clicked.emit()
        super().mousePressEvent(event)

    # -- painting ------------------------------------------------------
    def paintEvent(self, event):  # noqa: N802 (Qt naming)
        pal = theme.palette()
        amber = QColor(pal["BAND_AMBER"])
        amber_light = QColor(pal["BAND_AMBER_LIGHT"])
        amber_deep = QColor(pal["BAND_AMBER_DEEP"])
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = 12.0
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        p.save()
        p.setClipPath(path)

        # day gradient (stops from the active theme)
        grad = QLinearGradient(rect.left(), 0, rect.right(), 0)
        for hour, colour in pal["BAND_STOPS"]:
            grad.setColorAt(hour / 24.0, QColor(colour))
        p.fillRect(rect, grad)

        w = rect.width()
        def x_of(minutes: float) -> float:
            return rect.left() + w * (minutes / 1440.0)

        # business-hours segment (glowing amber)
        s_min = _minutes(self._work_start)
        e_min = _minutes(self._work_end)
        seg = QRectF(x_of(s_min), rect.top() + 10,
                     x_of(e_min) - x_of(s_min), rect.height() - 26)
        for grow, alpha in ((7, 36), (4, 60), (2, 90)):
            glow = QColor(amber)
            glow.setAlpha(alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawRoundedRect(seg.adjusted(-grow, -grow, grow, grow),
                              10, 10)
        seg_grad = QLinearGradient(0, seg.top(), 0, seg.bottom())
        seg_grad.setColorAt(0.0, amber_light)
        seg_grad.setColorAt(0.5, amber)
        seg_grad.setColorAt(1.0, amber_deep)
        p.setBrush(seg_grad)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(seg, 8, 8)
        if pal["BAND_SEG_PEN"] is not None:
            # light theme: an outline keeps the segment clearly
            # delimited on the bright sky gradient
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(_rgba(pal["BAND_SEG_PEN"]), 1.2))
            p.drawRoundedRect(seg, 8, 8)

        # dim for weekend / holiday — painted now, BEFORE the ticks,
        # cursor and badge, so those stay bright and readable
        if self._dimmed:
            p.fillRect(rect, _rgba(pal["BAND_DIM"]))

        # hour ticks + labels (0, 3, 6 ... 24) along the bottom
        tick_pen = _rgba(pal["BAND_TICK"])
        tick_text = _rgba(pal["BAND_TICK_TEXT"])
        p.setPen(QPen(tick_pen, 1))
        font = QFont(self.font())
        font.setPointSizeF(9.0)
        fonts.polish_font(font, tabular=True)
        p.setFont(font)
        for hour in range(25):
            x = x_of(hour * 60)
            p.drawLine(int(x), int(rect.bottom() - 12),
                       int(x), int(rect.bottom() - (16 if hour % 3 == 0 else 13)))
            if hour % 3 == 0:
                p.setPen(tick_text)
                label = str(hour)
                tw = p.fontMetrics().horizontalAdvance(label)
                p.drawText(int(x - tw / 2), int(rect.bottom() - 1), label)
                p.setPen(QPen(tick_pen, 1))

        # shared cursor at the selected instant (local time here)
        if self._instant is not None:
            local = self._instant.astimezone(self._zone)
            mins = local.hour * 60 + local.minute + local.second / 60.0
            x = x_of(mins)
            glow = QColor(amber)
            glow.setAlpha(90)
            p.setPen(QPen(glow, 5))
            p.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))
            p.setPen(QPen(QColor("#FFFFFF"), 2))
            p.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(amber)
            p.drawEllipse(QPoint(int(x), int(rect.top() + 7)), 5, 5)

        p.restore()

        # badge (holiday name / weekend) at the top-right of the band.
        # High-contrast pill; the text is elided so it can never
        # spill outside the band, however long the holiday name is.
        if self._badge:
            font = QFont(self.font())
            font.setPointSizeF(10.5)
            font.setBold(True)
            fonts.polish_font(font)
            p.setFont(font)
            fm = p.fontMetrics()
            max_text_w = max(40.0, rect.width() - 30)
            text = fm.elidedText(self._badge,
                                 Qt.TextElideMode.ElideRight,
                                 int(max_text_w))
            tw = fm.horizontalAdvance(text)
            badge = QRectF(max(rect.left() + 6,
                               rect.right() - tw - 18),
                           rect.top() + 5, tw + 14, 25)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_rgba(pal["BAND_BADGE_BG"]))
            p.drawRoundedRect(badge, 10, 10)
            p.setPen(_rgba(pal["BAND_BADGE_TEXT_DIM"]) if self._dimmed
                     else _rgba(pal["BAND_BADGE_TEXT"]))
            p.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)

        # frame / selection
        p.setBrush(Qt.BrushStyle.NoBrush)
        if self._selected:
            p.setPen(QPen(amber, 2.5))
        else:
            p.setPen(QPen(QColor(pal["BAND_FRAME"]), 1.2))
        p.drawRoundedRect(rect, radius, radius)
        p.end()


class FlowHost(QWidget):
    """Host widget that reports height-for-width from its FlowLayout,
    so the chips area wraps and sizes correctly inside a QVBoxLayout."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._flow = FlowLayout(self, spacing=10)

    def flow(self) -> "FlowLayout":
        return self._flow

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, width):  # noqa: N802
        return self._flow.heightForWidth(width)


class FlowLayout(QLayout):
    """Simple wrapping layout for the candidate-slot chips."""

    def __init__(self, parent=None, margin=0, spacing=10):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self._spacing = spacing
        self._items = []

    def addItem(self, item):  # noqa: N802
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):  # noqa: N802
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, width):  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):  # noqa: N802
        return self.minimumSize()

    def minimumSize(self):  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_height = eff.x(), eff.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._spacing
            if next_x - self._spacing > eff.right() and line_height > 0:
                x = eff.x()
                y += line_height + self._spacing
                next_x = x + hint.width() + self._spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + m.bottom()
