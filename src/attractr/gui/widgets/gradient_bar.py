"""A widget painting a Gradient (used as palette preview and as the editor's bar)."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QWidget

from attractr.core.color.gradient import Gradient


def gradient_image(g: Gradient, width: int, height: int = 1, phase: float = 0.0, cycles: float = 1.0) -> QImage:
    lut = g.lut(max(width, 2), phase, cycles)
    img = QImage(width, height, QImage.Format.Format_RGBA8888)
    rgba = (lut[:, :4] * 255 + 0.5).astype("uint8")
    if lut.shape[0] != width:
        idx = (np_linspace(width) * (lut.shape[0] - 1)).astype(int)
        rgba = rgba[idx]
    row = bytes(rgba.tobytes())
    for y in range(height):
        ptr = img.scanLine(y)
        ptr[: len(row)] = row  # type: ignore[index]
    return img


def np_linspace(n: int):
    import numpy as np

    return np.linspace(0.0, 1.0, n)


class GradientBar(QWidget):
    clicked = Signal()

    def __init__(self, gradient: Gradient | None = None, parent=None, height: int = 18) -> None:
        super().__init__(parent)
        self.gradient = gradient or Gradient()
        self.phase = 0.0
        self.cycles = 1.0
        self.setMinimumHeight(height)
        self.setMaximumHeight(height + 8)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_gradient(self, g: Gradient, phase: float = 0.0, cycles: float = 1.0) -> None:
        self.gradient, self.phase, self.cycles = g, phase, cycles
        self.update()

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        w = max(self.width(), 2)
        img = gradient_image(self.gradient, w, 1, self.phase, self.cycles)
        p.drawImage(QRectF(0, 0, self.width(), self.height()), img)
        p.setPen(QColor(70, 70, 90))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.end()

    def mousePressEvent(self, e) -> None:  # noqa: N802
        self.clicked.emit()
