"""Preferences: preview budget, engines, memory, folders."""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
)

from attractr.core.render.engines import selector


class PreferencesDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        qs = QSettings()
        form = QFormLayout(self)
        self.preview_engine = QComboBox()
        self.preview_engine.addItem("auto", "auto")
        for eid in selector.engine_ids():
            self.preview_engine.addItem(eid, eid)
        self.preview_engine.setCurrentIndex(max(0, self.preview_engine.findData(qs.value("preview/engine", "auto"))))
        self.preview_side = QSpinBox()
        self.preview_side.setRange(128, 4096)
        self.preview_side.setValue(int(qs.value("preview/max_side", 1024)))
        self.preview_ppp = QDoubleSpinBox()
        self.preview_ppp.setRange(0.1, 64)
        self.preview_ppp.setValue(float(qs.value("preview/ppp", 2.0)))
        self.interactive_ppp = QDoubleSpinBox()
        self.interactive_ppp.setRange(0.05, 16)
        self.interactive_ppp.setValue(float(qs.value("preview/interactive_ppp", 0.4)))
        self.ffmpeg = QLineEdit(qs.value("ffmpeg/path", ""))
        self.ffmpeg.setPlaceholderText("auto-detect on PATH")
        form.addRow("Preview engine", self.preview_engine)
        form.addRow("Preview max side (px)", self.preview_side)
        form.addRow("Preview points / pixel", self.preview_ppp)
        form.addRow("Interactive points / pixel", self.interactive_ppp)
        form.addRow("ffmpeg executable", self.ffmpeg)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _save(self) -> None:
        qs = QSettings()
        qs.setValue("preview/engine", self.preview_engine.currentData())
        qs.setValue("preview/max_side", self.preview_side.value())
        qs.setValue("preview/ppp", self.preview_ppp.value())
        qs.setValue("preview/interactive_ppp", self.interactive_ppp.value())
        qs.setValue("ffmpeg/path", self.ffmpeg.text())
        self.accept()
