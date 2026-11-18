# -*- coding: utf-8 -*-
"""Hand-drawn icons (QPainter pixmaps).  No emoji glyphs anywhere:
icon rendering must never depend on a colour-emoji font fallback."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

_SIZE = 48
_cache = {}


def _pen(color, width=3.0):
    pen = QPen(QColor(color))
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _folder(p, color):
    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(6, 16, 36, 22), 3, 3)
    p.drawLine(QPointF(6, 20), QPointF(18, 20))
    p.drawLine(QPointF(18, 20), QPointF(21, 12))
    p.drawLine(QPointF(21, 12), QPointF(33, 12))
    p.drawLine(QPointF(33, 12), QPointF(36, 20))


def _search(p, color):
    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(21, 21), 10, 10)
    p.drawLine(QPointF(28.5, 28.5), QPointF(40, 40))


def _file(p, color):
    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(13, 6, 22, 36), 3, 3)
    p.drawLine(QPointF(19, 17), QPointF(29, 17))
    p.drawLine(QPointF(19, 24), QPointF(29, 24))
    p.drawLine(QPointF(19, 31), QPointF(25, 31))


def _check(p, color):
    p.setPen(_pen(color, 4.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(10, 25), QPointF(20, 35))
    p.drawLine(QPointF(20, 35), QPointF(39, 13))


def _undo(p, color):
    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(10, 12, 28, 28), 40 * 16, 260 * 16)
    p.drawLine(QPointF(10, 20), QPointF(10, 32))
    p.drawLine(QPointF(10, 32), QPointF(21, 30))


def _diff(p, color):
    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(7, 8, 15, 32), 2.5, 2.5)
    p.drawRoundedRect(QRectF(26, 8, 15, 32), 2.5, 2.5)
    p.drawLine(QPointF(11, 18), QPointF(18, 18))
    p.drawLine(QPointF(30, 30), QPointF(37, 30))
    p.drawLine(QPointF(33.5, 26.5), QPointF(33.5, 33.5))


def _archive(p, color):
    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(7, 10, 34, 10))
    p.drawRoundedRect(QRectF(10, 20, 28, 18), 2.5, 2.5)
    p.drawLine(QPointF(20, 26), QPointF(28, 26))


def _branch(p, color):
    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(13, 11), 4.5, 4.5)
    p.drawEllipse(QPointF(13, 37), 4.5, 4.5)
    p.drawEllipse(QPointF(35, 24), 4.5, 4.5)
    p.drawLine(QPointF(13, 15.5), QPointF(13, 32.5))
    p.drawArc(QRectF(13, 11, 22, 26), 0, 90 * 16)
    p.drawLine(QPointF(30.5, 24), QPointF(24, 24))


def _star(p, color):
    p.setPen(_pen(color))
    p.setBrush(QColor(color))
    import math
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        r = 15 if i % 2 == 0 else 6.5
        pts.append(QPointF(24 + r * math.cos(ang), 24 + r * math.sin(ang)))
    from PySide6.QtGui import QPolygonF
    p.drawPolygon(QPolygonF(pts))


_DRAWERS = {"folder": _folder, "search": _search, "file": _file,
            "check": _check, "undo": _undo, "diff": _diff,
            "archive": _archive, "branch": _branch, "star": _star}


def icon(name: str, color: str = "#4F46E5") -> QIcon:
    key = (name, color)
    if key in _cache:
        return _cache[key]
    pm = QPixmap(_SIZE, _SIZE)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    _DRAWERS[name](painter, color)
    painter.end()
    ic = QIcon(pm)
    _cache[key] = ic
    return ic
