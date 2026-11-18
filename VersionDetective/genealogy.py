# -*- coding: utf-8 -*-
"""Version genealogy canvas.

Draws one document family as a family tree of versions: nodes on a
horizontal line, oldest to newest, each node captioned with its
content-changed datetime and the size of the change from the previous
version.  The latest candidate is a larger node with a double ring.
When the analyser flags a possible branch, the branch partner is drawn
on a forked lower line instead of being forced onto the main line.

Pure QPainter work: no text glyphs are used as icons, so rendering
never depends on an emoji font.  In RTL locales the caller sets
rtl=True and the tree is mirrored (newest on the left).
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

import theme

_SPACING = 184
_MARGIN = 64
_MAIN_Y = 58
_BRANCH_Y = 176
_R = 17
_R_LATEST = 25


@dataclass
class NodeView:
    path: str
    number: int            # 1-based version number (chronological)
    name: str              # file name
    dt_text: str           # formatted content-changed datetime + source
    caption: str           # change size vs previous version / first
    is_latest: bool = False
    is_manual: bool = False
    is_branch: bool = False
    selected: bool = False


class GenealogyCanvas(QWidget):
    nodeClicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodes: list[NodeView] = []
        self._rtl = False
        self._empty_text = ""
        self._branch_label = ""
        self._hit: list[tuple[QRectF, str]] = []
        self.setMinimumHeight(150)
        self.setMouseTracking(True)

    # -- data ---------------------------------------------------------
    def set_data(self, nodes, rtl=False, branch_label="",
                 empty_text=""):
        self._nodes = list(nodes)
        self._rtl = rtl
        self._branch_label = branch_label
        self._empty_text = empty_text
        has_branch = any(n.is_branch for n in self._nodes)
        self.setMinimumHeight(258 if has_branch else 156)
        n = max(1, len(self._nodes))
        self.setMinimumWidth(int(_MARGIN * 2 + _SPACING * (n - 1) + 40))
        self.resize(self.minimumSize())
        self.update()

    # -- geometry -----------------------------------------------------
    def _x(self, idx: int) -> float:
        x = _MARGIN + _SPACING * idx
        if self._rtl:
            total = _MARGIN * 2 + _SPACING * max(0, len(self._nodes) - 1)
            x = total - x
        return x

    def _pos(self, idx: int, node: NodeView) -> QPointF:
        y = _BRANCH_Y if node.is_branch else _MAIN_Y
        return QPointF(self._x(idx), y)

    # -- painting -----------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        if not self._nodes:
            p.setPen(QColor(theme.SUBINK))
            f = QFont(self.font())
            f.setPointSize(11)
            p.setFont(f)
            box = self.rect().adjusted(24, 12, -24, -12)
            p.drawText(box,
                       Qt.AlignmentFlag.AlignCenter |
                       Qt.TextFlag.TextWordWrap,
                       self._empty_text)
            p.end()
            return

        indigo = QColor(theme.INDIGO)
        deep = QColor(theme.INDIGO_DEEP)
        line = QColor(theme.LINE)
        amber = QColor(theme.AMBER)

        main_idx = [i for i, n in enumerate(self._nodes)
                    if not n.is_branch]
        # connectors on the main line
        pen = QPen(line)
        pen.setWidthF(2.5)
        p.setPen(pen)
        for a, b in zip(main_idx, main_idx[1:]):
            pa = self._pos(a, self._nodes[a])
            pb = self._pos(b, self._nodes[b])
            p.drawLine(pa, pb)
        # fork connectors to branch nodes
        for i, node in enumerate(self._nodes):
            if not node.is_branch:
                continue
            prev_main = max([j for j in main_idx if j < i],
                            default=main_idx[0] if main_idx else i)
            start = self._pos(prev_main, self._nodes[prev_main])
            end = self._pos(i, node)
            path = QPainterPath(start)
            midx = (start.x() + end.x()) / 2
            path.cubicTo(QPointF(midx, start.y()),
                         QPointF(midx, end.y()), end)
            p.setPen(QPen(amber, 2.5, Qt.PenStyle.DashLine))
            p.drawPath(path)
            if self._branch_label:
                p.setPen(amber)
                f = QFont(self.font())
                f.setPointSize(9)
                f.setBold(True)
                p.setFont(f)
                lx = (start.x() + end.x()) / 2 - 14
                p.drawText(QPointF(lx, end.y() - 40),
                           self._branch_label)

        self._hit = []
        name_font = QFont(self.font())
        name_font.setPointSize(10)
        name_font.setBold(True)
        cap_font = QFont(self.font())
        cap_font.setPointSize(9)
        num_font = QFont(self.font())
        num_font.setBold(True)

        for i, node in enumerate(self._nodes):
            c = self._pos(i, node)
            r = _R_LATEST if node.is_latest else _R
            if node.is_branch:
                ring = amber
            elif node.is_latest:
                ring = indigo
            else:
                ring = deep
            if node.is_latest:
                # double ring
                p.setPen(QPen(indigo, 2.0))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(c, r + 6, r + 6)
            p.setPen(QPen(ring, 3.0 if node.selected else 2.2))
            fill = QColor(theme.INDIGO_SOFT if node.is_latest
                          else theme.PANEL)
            if node.selected:
                fill = QColor(theme.INDIGO_SOFT)
            p.setBrush(fill)
            p.drawEllipse(c, r, r)
            # version number inside the node
            num_font.setPointSize(13 if node.is_latest else 11)
            p.setFont(num_font)
            p.setPen(deep if not node.is_latest else indigo)
            p.drawText(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r),
                       Qt.AlignmentFlag.AlignCenter, str(node.number))
            self._hit.append(
                (QRectF(c.x() - r - 8, c.y() - r - 8,
                        2 * r + 16, 2 * r + 16), node.path))
            # file name under the node
            p.setFont(name_font)
            p.setPen(QColor(theme.INK))
            fm = QFontMetrics(name_font)
            elided = fm.elidedText(node.name,
                                   Qt.TextElideMode.ElideMiddle, 168)
            w = fm.horizontalAdvance(elided)
            p.drawText(QPointF(c.x() - w / 2, c.y() + r + 20), elided)
            # datetime + change caption
            p.setFont(cap_font)
            p.setPen(QColor(theme.SUBINK))
            for k, txt in enumerate((node.dt_text, node.caption)):
                if not txt:
                    continue
                fm2 = QFontMetrics(cap_font)
                w2 = fm2.horizontalAdvance(txt)
                p.drawText(QPointF(c.x() - w2 / 2,
                                   c.y() + r + 36 + 13 * k), txt)
        p.end()

    # -- interaction ----------------------------------------------------
    def mousePressEvent(self, event):
        pos = event.position()
        for rect, path in self._hit:
            if rect.contains(pos):
                self.nodeClicked.emit(path)
                return
        super().mousePressEvent(event)
