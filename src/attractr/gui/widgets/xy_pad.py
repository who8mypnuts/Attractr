"""XY pad: drag one point to change two parameters at once."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from attractr.core.attractors.spec import AttractorSpec
from attractr.gui.state.document import Document


class PadArea(QWidget):
    moved = Signal(float, float)  # normalised 0..1
    pressed = Signal()
    released = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.pos = (0.5, 0.5)
        self.setMinimumSize(160, 160)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_pos(self, u: float, v: float) -> None:
        self.pos = (u, v)
        self.update()

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        p.fillRect(r, QColor(16, 16, 22))
        p.setPen(QPen(QColor(50, 50, 70), 1))
        for i in range(1, 4):
            x = r.left() + r.width() * i / 4
            y = r.top() + r.height() * i / 4
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        p.setPen(QPen(QColor(90, 90, 110), 1))
        p.drawRect(r)
        cx = r.left() + self.pos[0] * r.width()
        cy = r.bottom() - self.pos[1] * r.height()
        p.setPen(QPen(QColor(79, 195, 247), 1.5))
        p.drawLine(QPointF(cx, r.top()), QPointF(cx, r.bottom()))
        p.drawLine(QPointF(r.left(), cy), QPointF(r.right(), cy))
        p.setBrush(QColor(79, 195, 247))
        p.drawEllipse(QRectF(cx - 5, cy - 5, 10, 10))
        p.end()

    def _emit(self, e) -> None:
        r = self.rect().adjusted(1, 1, -1, -1)
        u = min(max((e.position().x() - r.left()) / r.width(), 0.0), 1.0)
        v = min(max((r.bottom() - e.position().y()) / r.height(), 0.0), 1.0)
        self.set_pos(u, v)
        self.moved.emit(u, v)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        self.pressed.emit()
        self._emit(e)

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if e.buttons():
            self._emit(e)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        self.released.emit()


class XYPad(QWidget):
    def __init__(self, doc: Document, parent=None) -> None:
        super().__init__(parent)
        self.doc = doc
        self._syncing = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.cx = QComboBox()
        self.cy = QComboBox()
        row.addWidget(QLabel("X"))
        row.addWidget(self.cx, 1)
        row.addWidget(QLabel("Y"))
        row.addWidget(self.cy, 1)
        lay.addLayout(row)
        self.pad = PadArea()
        lay.addWidget(self.pad)
        self.pad.moved.connect(self._on_move)
        self.pad.pressed.connect(doc.begin_interaction)
        self.pad.released.connect(doc.end_interaction)
        self.cx.currentIndexChanged.connect(lambda _: self.sync())
        self.cy.currentIndexChanged.connect(lambda _: self.sync())
        doc.attractorChanged.connect(self.rebuild)
        doc.changed.connect(lambda s, t: self.sync() if "params" in t else None)
        self.rebuild(doc.spec)

    def rebuild(self, spec: AttractorSpec) -> None:
        self._syncing = True
        for c in (self.cx, self.cy):
            c.clear()
            for p in spec.params:
                c.addItem(p.name)
        if self.cy.count() > 1:
            self.cy.setCurrentIndex(1)
        self._syncing = False
        self.setEnabled(len(spec.params) >= 2)
        self.sync()

    def _params(self):
        spec = self.doc.spec
        px = next((p for p in spec.params if p.name == self.cx.currentText()), None)
        py = next((p for p in spec.params if p.name == self.cy.currentText()), None)
        return px, py

    def sync(self) -> None:
        if self._syncing:
            return
        px, py = self._params()
        if px is None or py is None:
            return
        vals = self.doc.settings.param_dict
        u = (vals.get(px.name, px.default) - px.lo) / max(px.span, 1e-12)
        v = (vals.get(py.name, py.default) - py.lo) / max(py.span, 1e-12)
        self.pad.set_pos(min(max(u, 0), 1), min(max(v, 0), 1))

    def _on_move(self, u: float, v: float) -> None:
        px, py = self._params()
        if px is None or py is None:
            return
        vx = px.lo + u * px.span
        vy = py.lo + v * py.span
        if px.is_int:
            vx = round(vx)
        if py.is_int:
            vy = round(vy)
        self.doc.apply(self.doc.settings.with_params(**{px.name: vx, py.name: vy}), "XY pad", {"params"}, merge_key="xypad")
