"""Animation render dialog → AnimationJob (frames + ffmpeg) on the job queue."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSettings, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from attractr.core.animation.ffmpeg import PRESETS, find_ffmpeg
from attractr.core.animation.sequence import SequenceOptions, render_sequence
from attractr.core.animation.timeline import Timeline
from attractr.core.jobs.cancel import CancelToken
from attractr.core.jobs.job import Job
from attractr.core.jobs.progress import ProgressTracker
from attractr.core.render.engines import selector
from attractr.core.render.settings import RenderSettings
from attractr.gui.dialogs.render_dialog import QUALITY_TIERS, SIZE_PRESETS


class AnimationJob(Job):
    def __init__(self, base: RenderSettings, timeline: Timeline, opts: SequenceOptions) -> None:
        super().__init__(f"Animation {timeline.frame_count} frames")
        self.base, self.timeline, self.opts = base, timeline, opts
        self.result = None

    def run(self, cancel: CancelToken, tracker: ProgressTracker):
        def on_frame(i, path, dev):
            self.partial.emit((i, path))

        self.result = render_sequence(self.base, self.timeline, self.opts, cancel=cancel, tracker=tracker, on_frame=on_frame)
        return self.result


class AnimateDialog(QDialog):
    jobCreated = Signal(object)

    def __init__(self, get_base, get_timeline, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Render animation")
        self.setModal(False)
        self.get_base, self.get_timeline = get_base, get_timeline
        qs = QSettings()
        lay = QVBoxLayout(self)

        g = QGroupBox("Frames")
        f = QFormLayout(g)
        self.size_preset = QComboBox()
        for name, w, h in SIZE_PRESETS:
            self.size_preset.addItem(name, (w, h))
        self.width = QSpinBox()
        self.width.setRange(16, 8192)
        self.height = QSpinBox()
        self.height.setRange(16, 8192)
        row = QHBoxLayout()
        row.addWidget(self.width)
        row.addWidget(QLabel("×"))
        row.addWidget(self.height)
        self.tier = QComboBox()
        for name, ppp in QUALITY_TIERS:
            self.tier.addItem(name, ppp)
        self.ppp = QDoubleSpinBox()
        self.ppp.setRange(0.1, 1000)
        self.engine = QComboBox()
        self.engine.addItem("auto", "auto")
        for eid in selector.engine_ids():
            self.engine.addItem(eid, eid)
        self.ss = QSpinBox()
        self.ss.setRange(1, 4)
        self.ss.setValue(1)
        self.blur = QSpinBox()
        self.blur.setRange(1, 8)
        self.blur.setToolTip("Motion blur: sub-frame samples averaged per frame (multiplies render time)")
        self.lock = QCheckBox("Lock framing across the whole animation")
        self.lock.setChecked(True)
        self.info = QLabel("")
        f.addRow("Size preset", self.size_preset)
        f.addRow("Pixels", row)
        f.addRow("Quality tier", self.tier)
        f.addRow("Points / pixel", self.ppp)
        f.addRow("Engine", self.engine)
        f.addRow("Supersampling", self.ss)
        f.addRow("Motion blur", self.blur)
        f.addRow(self.lock)
        f.addRow("", self.info)
        lay.addWidget(g)

        g = QGroupBox("Output")
        f = QFormLayout(g)
        row = QHBoxLayout()
        self.folder = QLineEdit(qs.value("anim/folder", str(Path.home() / "Attractr" / "animations")))
        self.btn_folder = QPushButton("…")
        self.btn_folder.setFixedWidth(32)
        row.addWidget(self.folder, 1)
        row.addWidget(self.btn_folder)
        self.name = QLineEdit(qs.value("anim/name", "anim"))
        self.resume = QCheckBox("Resume (skip existing frames)")
        self.resume.setChecked(True)
        f.addRow("Folder", row)
        f.addRow("Name", self.name)
        f.addRow(self.resume)
        lay.addWidget(g)

        g = QGroupBox("Encode")
        f = QFormLayout(g)
        self.preset = QComboBox()
        for k, v in PRESETS.items():
            self.preset.addItem(v["label"], k)
        self.crf = QSpinBox()
        self.crf.setRange(0, 51)
        self.crf.setValue(18)
        self.crf.setToolTip("Constant rate factor — lower is higher quality / bigger (H.264/H.265/VP9)")
        ff = find_ffmpeg(qs.value("ffmpeg/path", "") or None)
        self.ff_label = QLabel(f"ffmpeg: {ff}" if ff else "ffmpeg not found — only PNG frames will be written")
        self.ff_label.setStyleSheet("color:#9aa5b1" if ff else "color:#ff7a7a")
        f.addRow("Format", self.preset)
        f.addRow("CRF", self.crf)
        f.addRow(self.ff_label)
        lay.addWidget(g)

        btns = QHBoxLayout()
        self.btn_render = QPushButton("▶ Render animation")
        self.btn_close = QPushButton("Close")
        btns.addStretch(1)
        btns.addWidget(self.btn_render)
        btns.addWidget(self.btn_close)
        lay.addLayout(btns)

        self.size_preset.currentIndexChanged.connect(self._on_preset)
        self.tier.currentIndexChanged.connect(self._on_tier)
        self.btn_folder.clicked.connect(self._pick_folder)
        self.btn_render.clicked.connect(self._render)
        self.btn_close.clicked.connect(self.close)
        for w in (self.width, self.height, self.ppp, self.blur):
            w.valueChanged.connect(self._update_info)
        self.size_preset.setCurrentIndex(int(qs.value("anim/size_preset", 1)))
        self._on_preset(self.size_preset.currentIndex())
        self.tier.setCurrentIndex(int(qs.value("anim/tier", 0)))
        self._on_tier(self.tier.currentIndex())
        if not ff:
            self.preset.setCurrentIndex(list(PRESETS).index("png_only"))

    def _on_preset(self, idx: int) -> None:
        w, h = self.size_preset.itemData(idx)
        custom = w == 0
        self.width.setEnabled(custom)
        self.height.setEnabled(custom)
        if not custom:
            self.width.setValue(w)
            self.height.setValue(h)
        self._update_info()

    def _on_tier(self, idx: int) -> None:
        ppp = self.tier.itemData(idx)
        self.ppp.setEnabled(ppp == 0.0)
        if ppp:
            self.ppp.setValue(ppp)
        self._update_info()

    def _update_info(self) -> None:
        tl = self.get_timeline()
        pts = self.ppp.value() * self.width.value() * self.height.value() * self.blur.value()
        self.info.setText(f"{tl.frame_count} frames × {pts / 1e6:.0f} M points = {tl.frame_count * pts / 1e9:.1f} G points")

    def _pick_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Output folder", self.folder.text())
        if d:
            self.folder.setText(d)

    def _render(self) -> None:
        base: RenderSettings = self.get_base()
        tl: Timeline = self.get_timeline()
        tl = Timeline.from_dict(tl.to_dict())
        tl.motion_blur = self.blur.value()
        tl.lock_framing = self.lock.isChecked()
        q = replace(base.quality, width=self.width.value(), height=self.height.value(), points_per_pixel=self.ppp.value(),
                    supersample=self.ss.value(), engine=self.engine.currentData())
        base = replace(base, quality=q)
        qs = QSettings()
        opts = SequenceOptions(out_dir=Path(self.folder.text()).expanduser() / self.name.text(), name=self.name.text() or "anim",
                               engine=self.engine.currentData(), resume=self.resume.isChecked(), encode_preset=self.preset.currentData(),
                               crf=self.crf.value(), ffmpeg=qs.value("ffmpeg/path", "") or None)
        for k, v in (("anim/folder", self.folder.text()), ("anim/name", self.name.text()), ("anim/size_preset", self.size_preset.currentIndex()), ("anim/tier", self.tier.currentIndex())):
            qs.setValue(k, v)
        self.jobCreated.emit(AnimationJob(base, tl, opts))
