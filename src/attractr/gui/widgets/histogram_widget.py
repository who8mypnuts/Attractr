"""Log-scale bar plot of the density histogram with the tone curve overlaid."""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class HistogramWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.counts: list[int] = []
        self.edges: list[float] = []
        self.norm = 1.0
        self.gamma = 1.0
        self.setMinimumHeight(90)

    def set_data(self, counts: list[int], edges: list[float], norm: float, gamma: float) -> None:
        self.counts, self.edges, self.norm, self.gamma = counts, edges, norm, gamma
        self.update()

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(16, 16, 22))
        if not self.counts:
            p.setPen(QColor(120, 120, 140))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "no data")
            return
        W, H = self.width(), self.height()
        pad = 6
        n = len(self.counts)
        m = max(self.counts) or 1
        bw = (W - 2 * pad) / n
        p.setPen(Qt.PenStyle.NoPen)
        for i, c in enumerate(self.counts):
            h = 0 if c == 0 else (math.log1p(c) / math.log1p(m)) * (H - 2 * pad)
            p.setBrush(QColor(79, 195, 247, 200))
            p.drawRect(QPointF(pad + i * bw, H - pad - h).x(), H - pad - h, max(bw - 1, 1), h)
        # tone curve: x = density bin edge → y = log1p(c)/log1p(norm) ^ gamma
        if self.edges and self.norm > 0:
            path = QPainterPath()
            xs = np.linspace(0, 1, 128)
            for k, t in enumerate(xs):
                c = self.edges[0] + t * (self.edges[-1] - self.edges[0])
                d = min(1.0, math.log1p(max(c, 0)) / math.log1p(self.norm)) ** max(self.gamma, 1e-3)
                x = pad + t * (W - 2 * pad)
                y = H - pad - d * (H - 2 * pad)
                path.moveTo(x, y) if k == 0 else path.lineTo(x, y)
            p.setPen(QPen(QColor(255, 170, 60), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        p.end()
