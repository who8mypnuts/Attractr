"""First-run tips (replaces the Android spotlight tutorial)."""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout

TIPS = """
<h3 style='color:#4fc3f7'>Welcome to Attractr</h3>
<ul>
<li><b>Pick an attractor</b> in the Attractors dock, then drag the <b>Parameters</b> sliders — the preview updates live.</li>
<li><b>Drag the image</b> to rotate (right-drag rolls, wheel zooms, double-click resets, <kbd>Space</kbd> spins).</li>
<li><b>Look</b> changes (palette, gamma, style) are instant — nothing is re-computed.</li>
<li><kbd>R</kbd> randomizes parameters, <kbd>Shift+R</kbd> surprises you, <kbd>M</kbd> opens the Mutate grid, <kbd>Ctrl+F</kbd> searches for chaos.</li>
<li><kbd>F4</kbd> opens the Formula editor: type your own equations and watch them render.</li>
<li><kbd>Ctrl+R</kbd> renders at full size with an optional report; <kbd>T</kbd> opens the Timeline for animations.</li>
</ul>
<p style='color:#888'>Everything is documented in <i>Help → Documentation</i>.</p>
"""


class TipsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tips")
        lay = QVBoxLayout(self)
        label = QLabel(TIPS)
        label.setWordWrap(True)
        lay.addWidget(label)
        self.again = QCheckBox("Show at start-up")
        self.again.setChecked(True)
        lay.addWidget(self.again)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)
        self.resize(520, 360)

    def accept(self) -> None:
        QSettings().setValue("tips/show", self.again.isChecked())
        super().accept()

    @staticmethod
    def maybe_show(parent) -> None:
        from PySide6.QtWidgets import QApplication

        if QApplication.instance().property("attractr_testing"):
            return
        if QSettings().value("tips/show", "true") in ("true", True):
            TipsDialog(parent).show()
