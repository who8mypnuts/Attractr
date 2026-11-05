"""Preferences: preview budget, engines, memory, folders."""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
)

from attractr.core.render.engines import selector
from attractr.gui.state.render_prefs import DEFAULT_CHECKPOINT_MINUTES, KEY_CHECKPOINT_MINUTES
from attractr.i18n import tr


class PreferencesDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Preferences"))
        qs = QSettings()
        form = QFormLayout(self)
        self.preview_engine = QComboBox()
        self.preview_engine.addItem(tr("auto"), "auto")
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
        self.thumb_mb = QSpinBox()
        self.thumb_mb.setRange(0, 100000)
        self.thumb_mb.setSuffix(tr(" MB"))
        self.thumb_mb.setSpecialValueText(tr("unlimited"))
        self.thumb_mb.setValue(int(qs.value("thumbs/max_mb", 256)))
        self.thumb_mb.setToolTip(tr("The thumbnail cache (~/.attractr/cache/thumbs) is pruned to this size at start-up (oldest first)"))
        self.ckpt = QDoubleSpinBox()
        self.ckpt.setRange(0, 120)
        self.ckpt.setDecimals(1)
        self.ckpt.setSuffix(tr(" min"))
        self.ckpt.setSpecialValueText(tr("off"))
        self.ckpt.setValue(float(qs.value(KEY_CHECKPOINT_MINUTES, DEFAULT_CHECKPOINT_MINUTES)))
        self.ckpt.setToolTip(tr("Long renders write a resumable checkpoint (.npz next to the output, in checkpoints/) this often"))
        self.gpu_develop = QCheckBox(tr("Develop large images (≥ 1.5 Mpixel) on the GPU when possible"))
        self.gpu_develop.setChecked(qs.value("develop/gpu", "true") in ("true", True))
        self.ffmpeg = QLineEdit(qs.value("ffmpeg/path", ""))
        self.ffmpeg.setPlaceholderText(tr("auto-detect on PATH"))
        form.addRow(tr("Preview engine"), self.preview_engine)
        form.addRow(tr("Preview max side (px)"), self.preview_side)
        form.addRow(tr("Preview points / pixel"), self.preview_ppp)
        form.addRow(tr("Interactive points / pixel"), self.interactive_ppp)
        form.addRow(tr("Thumbnail cache limit"), self.thumb_mb)
        form.addRow(tr("Render checkpoint every"), self.ckpt)
        form.addRow(tr("GPU develop"), self.gpu_develop)
        form.addRow(tr("ffmpeg executable"), self.ffmpeg)
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
        qs.setValue("thumbs/max_mb", self.thumb_mb.value())
        qs.setValue(KEY_CHECKPOINT_MINUTES, self.ckpt.value())
        qs.setValue("develop/gpu", self.gpu_develop.isChecked())
        qs.setValue("ffmpeg/path", self.ffmpeg.text())
        self.accept()
