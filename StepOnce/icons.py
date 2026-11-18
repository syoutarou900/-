# -*- coding: utf-8 -*-
"""Hand-drawn button icons (QPainter), no emoji glyphs anywhere.

The previous design prefixed button labels with emoji characters
(camera / book / brush / record dot ...).  Under Wine - and on any
system whose font fallback lands on a colour emoji font - those
glyphs could render as huge colour emoji and break the layout.
Every icon the UI needs is therefore drawn here with QPainter into a
QPixmap, so rendering never depends on font glyph availability.
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

_SIZE = 48  # pixmap is drawn at 48x48 and shown at ~18-20 logical px

_cache = {}


def _pen(color, width):
    pen = QPen(QColor(color))
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _draw_camera(p, color):
    p.setPen(_pen(color, 3.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(6, 15, 36, 22), 4, 4)
    p.drawLine(QPointF(19, 15), QPointF(21, 9))
    p.drawLine(QPointF(29, 15), QPointF(27, 9))
    p.drawLine(QPointF(21, 9), QPointF(27, 9))
    p.drawEllipse(QPointF(24, 26), 6.5, 6.5)
    p.setBrush(QColor(color))
    p.drawEllipse(QPointF(24, 26), 2.4, 2.4)
    p.drawEllipse(QPointF(37.5, 20), 1.8, 1.8)


def _draw_book(p, color):
    p.setPen(_pen(color, 3.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    left = QPainterPath()
    left.moveTo(24, 12)
    left.cubicTo(18, 8, 12, 8, 7, 10)
    left.lineTo(7, 36)
    left.cubicTo(12, 34, 18, 34, 24, 38)
    left.closeSubpath()
    right = QPainterPath()
    right.moveTo(24, 12)
    right.cubicTo(30, 8, 36, 8, 41, 10)
    right.lineTo(41, 36)
    right.cubicTo(36, 34, 30, 34, 24, 38)
    right.closeSubpath()
    p.drawPath(left)
    p.drawPath(right)
    p.drawLine(QPointF(24, 12), QPointF(24, 38))


def _draw_brush(p, color):
    p.setPen(_pen(color, 4.0))
    p.drawLine(QPointF(33, 7), QPointF(20, 26))
    p.setPen(_pen(color, 6.5))
    p.drawLine(QPointF(18, 28), QPointF(14, 34))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    tip = QPainterPath()
    tip.moveTo(17, 32)
    tip.cubicTo(9, 35, 7, 41, 9, 45)
    tip.cubicTo(15, 45, 19, 39, 17, 32)
    tip.closeSubpath()
    p.drawPath(tip)


def _draw_record(p, color):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(QPointF(24, 24), 9.5, 9.5)


def _draw_stop(p, color):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(14, 14, 20, 20), 3, 3)


def _draw_up(p, color):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawPolygon([QPointF(24, 13), QPointF(37, 35), QPointF(11, 35)])


def _draw_down(p, color):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawPolygon([QPointF(24, 35), QPointF(37, 13), QPointF(11, 13)])


_DRAWERS = {
    "camera": _draw_camera,
    "book": _draw_book,
    "brush": _draw_brush,
    "record": _draw_record,
    "stop": _draw_stop,
    "up": _draw_up,
    "down": _draw_down,
}


def icon(kind, color):
    """Return a cached QIcon drawn with QPainter (never a font glyph)."""
    key = (kind, color)
    if key not in _cache:
        pixmap = QPixmap(_SIZE, _SIZE)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        _DRAWERS[kind](painter, color)
        painter.end()
        _cache[key] = QIcon(pixmap)
    return _cache[key]
