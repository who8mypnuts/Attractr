"""A titled, collapsible section used to group controls inside panels."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QToolButton, QVBoxLayout, QWidget


class Collapsible(QWidget):
    def __init__(self, title: str, content: QWidget, expanded: bool = True, parent=None) -> None:
        super().__init__(parent)
        self.toggle = QToolButton()
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.toggle.setStyleSheet("QToolButton { border: none; font-weight: 600; text-align: left; padding: 4px 2px; }")
        self.toggle.setSizePolicy(self.toggle.sizePolicy().horizontalPolicy(), self.toggle.sizePolicy().verticalPolicy())
        self.content = content
        self.content.setVisible(expanded)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #2a2a3a;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 4)
        lay.setSpacing(2)
        lay.addWidget(self.toggle)
        lay.addWidget(self.content)
        lay.addWidget(line)
        self.toggle.toggled.connect(self._on_toggle)

    def _on_toggle(self, on: bool) -> None:
        self.content.setVisible(on)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
