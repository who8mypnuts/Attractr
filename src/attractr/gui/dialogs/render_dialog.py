"""Render dialog (non-modal): size, quality, engine, output, report options → job queue."""

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

from attractr.core.io.naming import DEFAULT_TEMPLATE
from attractr.core.render.engines import selector
from attractr.core.render.settings import REPORT_FORMATS, RenderSettings
from attractr.gui.controllers.render_job import RenderJob

SIZE_PRESETS = [
    ("Preview 768²", 768, 768), ("HD 1920×1080", 1920, 1080), ("Square 2048²", 2048, 2048),
    ("4K UHD 3840×2160", 3840, 2160), ("4K square 3840²", 3840, 3840), ("Portrait 1080×1920", 1080, 1920),
    ("8K 7680×4320", 7680, 4320), ("Print A3 300dpi 4961×3508", 4961, 3508), ("Custom", 0, 0),
]
QUALITY_TIERS = [("Draft", 4.0), ("Standard", 12.0), ("High", 30.0), ("Ultra", 75.0), ("Custom", 0.0)]
REPORT_LABELS = {"md": "Markdown (.md)", "txt": "Text (.txt)", "html": "HTML (.html)", "pdf": "PDF (.pdf)"}


class RenderDialog(QDialog):
    jobCreated = Signal(object)  # RenderJob

    def __init__(self, get_settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Render")
        self.setModal(False)
        self.get_settings = get_settings
        self.qs = QSettings()
        lay = QVBoxLayout(self)

        # size
        g = QGroupBox("Output size")
        f = QFormLayout(g)
        self.size_preset = QComboBox()
        for name, w, h in SIZE_PRESETS:
            self.size_preset.addItem(name, (w, h))
        self.width = QSpinBox()
        self.width.setRange(16, 32768)
        self.height = QSpinBox()
        self.height.setRange(16, 32768)
        row = QHBoxLayout()
        row.addWidget(self.width)
        row.addWidget(QLabel("×"))
        row.addWidget(self.height)
        f.addRow("Preset", self.size_preset)
        f.addRow("Pixels", row)
        lay.addWidget(g)

        # quality
        g = QGroupBox("Quality")
        f = QFormLayout(g)
        self.tier = QComboBox()
        for name, ppp in QUALITY_TIERS:
            self.tier.addItem(name, ppp)
        self.ppp = QDoubleSpinBox()
        self.ppp.setRange(0.1, 10000)
        self.ppp.setDecimals(1)
        self.points_label = QLabel("")
        self.engine = QComboBox()
        self.engine.addItem("auto (best available)", "auto")
        for eid in selector.engine_ids():
            self.engine.addItem(eid, eid)
        self.ss = QSpinBox()
        self.ss.setRange(1, 4)
        self.ss.setToolTip("Supersampling: accumulate at N× resolution and box-filter down")
        self.splat = QSpinBox()
        self.splat.setRange(0, 4)
        self.splat.setToolTip("0 = bilinear anti-aliased sub-pixel splat; 1–4 = soft disk radius")
        f.addRow("Tier", self.tier)
        f.addRow("Points / pixel", self.ppp)
        f.addRow("", self.points_label)
        f.addRow("Engine", self.engine)
        f.addRow("Supersampling", self.ss)
        f.addRow("Splat radius", self.splat)
        lay.addWidget(g)

        # output
        g = QGroupBox("Output")
        f = QFormLayout(g)
        row = QHBoxLayout()
        self.folder = QLineEdit(self.qs.value("render/folder", str(Path.home() / "Attractr")))
        self.btn_folder = QPushButton("…")
        self.btn_folder.setFixedWidth(32)
        row.addWidget(self.folder, 1)
        row.addWidget(self.btn_folder)
        self.template = QLineEdit(self.qs.value("render/template", DEFAULT_TEMPLATE))
        self.template.setToolTip("Fields: {name} {date} {time} {datetime} {w} {h} {seed} {style} {ppp}")
        self.fmt = QComboBox()
        self.fmt.addItems(["png", "jpg", "webp", "tif"])
        self.bits = QComboBox()
        self.bits.addItems(["8", "16"])
        self.bits.setToolTip("16-bit applies to PNG only")
        f.addRow("Folder", row)
        f.addRow("Name template", self.template)
        f.addRow("Format", self.fmt)
        f.addRow("Bit depth", self.bits)
        lay.addWidget(g)

        # report
        g = QGroupBox("Render report")
        f = QFormLayout(g)
        self.report_on = QCheckBox("Write a render report next to the image")
        self.report_on.setChecked(self.qs.value("render/report", "true") == "true")
        self.report_fmt = QComboBox()
        for k in REPORT_FORMATS:
            self.report_fmt.addItem(REPORT_LABELS[k], k)
        self.report_fmt.setCurrentIndex(max(0, list(REPORT_FORMATS).index(self.qs.value("render/report_fmt", "md"))))
        self.report_dyn = QCheckBox("Include dynamics (Lyapunov exponent, dimension)")
        f.addRow(self.report_on)
        f.addRow("Format", self.report_fmt)
        f.addRow(self.report_dyn)
        lay.addWidget(g)

        btns = QHBoxLayout()
        self.estimate = QLabel("")
        self.estimate.setStyleSheet("color:#999")
        self.btn_render = QPushButton("▶ Render")
        self.btn_render.setDefault(True)
        self.btn_close = QPushButton("Close")
        btns.addWidget(self.estimate, 1)
        btns.addWidget(self.btn_render)
        btns.addWidget(self.btn_close)
        lay.addLayout(btns)

        # wiring
        self.size_preset.currentIndexChanged.connect(self._on_preset)
        self.tier.currentIndexChanged.connect(self._on_tier)
        for w in (self.width, self.height):
            w.valueChanged.connect(self._update_estimate)
        self.ppp.valueChanged.connect(self._update_estimate)
        self.ss.valueChanged.connect(self._update_estimate)
        self.btn_folder.clicked.connect(self._pick_folder)
        self.btn_render.clicked.connect(self._render)
        self.btn_close.clicked.connect(self.close)
        self.report_on.toggled.connect(self.report_fmt.setEnabled)
        self.report_on.toggled.connect(self.report_dyn.setEnabled)

        self.size_preset.setCurrentIndex(int(self.qs.value("render/size_preset", 2)))
        self._on_preset(self.size_preset.currentIndex())
        self.tier.setCurrentIndex(int(self.qs.value("render/tier", 1)))
        self._on_tier(self.tier.currentIndex())
        self.ss.setValue(int(self.qs.value("render/ss", 2)))
        self.splat.setValue(int(self.qs.value("render/splat", 0)))
        self._update_estimate()

    def _on_preset(self, idx: int) -> None:
        w, h = self.size_preset.itemData(idx)
        custom = w == 0
        self.width.setEnabled(custom)
        self.height.setEnabled(custom)
        if not custom:
            self.width.setValue(w)
            self.height.setValue(h)
        self._update_estimate()

    def _on_tier(self, idx: int) -> None:
        ppp = self.tier.itemData(idx)
        self.ppp.setEnabled(ppp == 0.0)
        if ppp:
            self.ppp.setValue(ppp)
        self._update_estimate()

    def _update_estimate(self) -> None:
        pts = self.ppp.value() * self.width.value() * self.height.value()
        self.points_label.setText(f"≈ {pts / 1e6:.0f} M points" if pts < 1e9 else f"≈ {pts / 1e9:.2f} G points")
        caps = selector.probe("cpu")
        rate = 0.0
        for eid in ("gl_precision", "opencl"):
            c = selector.probe(eid)
            if c.available and c.mpts_per_second:
                rate = max(rate, c.mpts_per_second)
        est = f"~{pts / (rate * 1e6):.0f} s on GPU" if rate else ""
        mem = self.width.value() * self.height.value() * self.ss.value() ** 2 * 4 * 4 / (1024 * 1024)
        self.estimate.setText(f"{est}  · accumulation buffers ≈ {mem:.0f} MB{' (tiled)' if mem > 768 else ''}".strip(" ·"))
        _ = caps

    def _pick_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Output folder", self.folder.text())
        if d:
            self.folder.setText(d)

    def _render(self) -> None:
        s: RenderSettings = self.get_settings()
        q = replace(s.quality, width=self.width.value(), height=self.height.value(), points_per_pixel=self.ppp.value(),
                    supersample=self.ss.value(), splat_radius=self.splat.value(), engine=self.engine.currentData())
        s = replace(s, quality=q)
        reports = [self.report_fmt.currentData()] if self.report_on.isChecked() else []
        job = RenderJob(s, Path(self.folder.text()).expanduser(), self.template.text() or DEFAULT_TEMPLATE,
                        fmt=self.fmt.currentText(), bit_depth=int(self.bits.currentText()), report_formats=reports,
                        dynamics=self.report_dyn.isChecked())
        for k, v in (("render/folder", self.folder.text()), ("render/template", self.template.text()),
                     ("render/report", "true" if self.report_on.isChecked() else "false"),
                     ("render/report_fmt", self.report_fmt.currentData()), ("render/size_preset", self.size_preset.currentIndex()),
                     ("render/tier", self.tier.currentIndex()), ("render/ss", self.ss.value()), ("render/splat", self.splat.value())):
            self.qs.setValue(k, v)
        self.jobCreated.emit(job)
