"""About dialog with attributions."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QVBoxLayout

from attractr.core.io.paths import resources_dir
from attractr.i18n import tr
from attractr.version import __version__

TEXT = f"""
<h2 style='color:#4fc3f7;margin-bottom:0'>Attractr <span style='color:#888;font-size:12px'>{__version__}</span></h2>
<p>A strange-attractor studio: explore, edit, animate and render chaotic systems.</p>
<p style='color:#aaa'>Built on ideas from <b>Chaoscope</b> (Android/C++ re-imagining by Lucas Balancin, Apache-2.0),
<b>chaoscope</b> (pure-C renderer by Shpati Koleka) and <b>strange-attractors-webgl</b> (Jérémie Piellard),
all tributes to Nicolas Desprez's original Chaoscope.</p>
<p style='color:#aaa'>Attractr is MIT licensed. Python · PySide6 · NumPy · numba · ModernGL · pyopencl.</p>
"""


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("About Attractr"))
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        logo = resources_dir() / "logo" / "attractr_256.png"
        if logo.exists():
            pic = QLabel()
            pic.setPixmap(QPixmap(str(logo)).scaled(128, 128, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            row.addWidget(pic, 0, Qt.AlignmentFlag.AlignTop)
        text = QLabel(TEXT)
        text.setWordWrap(True)
        text.setOpenExternalLinks(True)
        row.addWidget(text, 1)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)
        self.resize(520, 260)
