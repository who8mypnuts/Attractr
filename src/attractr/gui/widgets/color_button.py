"""A button showing a colour swatch that opens QColorDialog."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QPushButton


class ColorButton(QPushButton):
    colorChanged = Signal(object)  # (r, g, b) floats 0..1

    def __init__(self, rgb=(0.0, 0.0, 0.0), parent=None) -> None:
        super().__init__(parent)
        self._rgb = tuple(float(c) for c in rgb)
        self.setFixedWidth(64)
        self.clicked.connect(self._pick)
        self._refresh()

    def rgb(self) -> tuple[float, float, float]:
        return self._rgb  # type: ignore[return-value]

    def set_rgb(self, rgb) -> None:
        self._rgb = tuple(float(c) for c in rgb)
        self._refresh()

    def _refresh(self) -> None:
        c = QColor.fromRgbF(*self._rgb)
        self.setStyleSheet(f"background-color: {c.name()}; border: 1px solid #555; border-radius: 3px;")
        self.setToolTip(c.name())

    def _pick(self) -> None:
        c = QColorDialog.getColor(QColor.fromRgbF(*self._rgb), self, "Pick a colour")
        if c.isValid():
            self.set_rgb((c.redF(), c.greenF(), c.blueF()))
            self.colorChanged.emit(self._rgb)
