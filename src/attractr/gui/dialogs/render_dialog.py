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
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from attractr.core.io.naming import DEFAULT_TEMPLATE
from attractr.core.project.render_presets import RenderPreset, render_presets
from attractr.core.render.engines import selector
from attractr.core.render.settings import REPORT_FORMATS, RenderSettings
from attractr.gui.controllers.render_job import RenderJob
from attractr.i18n import tr

SIZE_PRESETS = [
    ("Preview 768²", 768, 768), ("HD 1920×1080", 1920, 1080), ("Square 2048²", 2048, 2048),
    ("4K UHD 3840×2160", 3840, 2160), ("4K square 3840²", 3840, 3840), ("Portrait 1080×1920", 1080, 1920),
    ("8K 7680×4320", 7680, 4320), ("Print A3 300dpi 4961×3508", 4961, 3508), ("Custom", 0, 0),
]
QUALITY_TIERS = [("Draft", 4.0), ("Standard", 12.0), ("High", 30.0), ("Ultra", 75.0), ("Custom", 0.0)]
# points per pixel below which a style visibly suffers (Solid needs a dense surface, Liquid a smooth depth field)
RECOMMENDED_PPP = {"gas": 8.0, "dust": 6.0, "light": 8.0, "plasma": 8.0, "liquid": 20.0, "solid": 30.0}
REPORT_LABELS = {"md": "Markdown (.md)", "txt": "Text (.txt)", "html": "HTML (.html)", "pdf": "PDF (.pdf)"}


class RenderDialog(QDialog):
    jobCreated = Signal(object)  # RenderJob

    def __init__(self, get_settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Render"))
        self.setModal(False)
        self.get_settings = get_settings
        self.qs = QSettings()
        lay = QVBoxLayout(self)

        # render presets (named recipes for everything below)
        g = QGroupBox(tr("Render preset"))
        row = QHBoxLayout(g)
        self.preset = QComboBox()
        self.preset.setToolTip(tr("Named output recipes: size, quality, engine, format and report. Also used by Batch render and `attractr batch`."))
        self.btn_preset_save = QPushButton(tr("Save as…"))
        self.btn_preset_del = QPushButton(tr("Delete"))
        row.addWidget(self.preset, 1)
        row.addWidget(self.btn_preset_save)
        row.addWidget(self.btn_preset_del)
        lay.addWidget(g)

        # size
        g = QGroupBox(tr("Output size"))
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
        row.addWidget(QLabel(tr("×")))
        row.addWidget(self.height)
        f.addRow(tr("Preset"), self.size_preset)
        f.addRow(tr("Pixels"), row)
        lay.addWidget(g)

        # quality
        g = QGroupBox(tr("Quality"))
        f = QFormLayout(g)
        self.tier = QComboBox()
        for name, ppp in QUALITY_TIERS:
            self.tier.addItem(name, ppp)
        self.ppp = QDoubleSpinBox()
        self.ppp.setRange(0.1, 10000)
        self.ppp.setDecimals(1)
        self.points_label = QLabel("")
        self.hint_label = QLabel("")
        self.hint_label.setStyleSheet("color:#e0a040")
        self.hint_label.setWordWrap(True)
        self.engine = QComboBox()
        self.engine.addItem(tr("auto (best available)"), "auto")
        for eid in selector.engine_ids():
            self.engine.addItem(eid, eid)
        self.precision = QComboBox()
        self.precision.addItem(tr("auto (fp32)"), "auto")
        self.precision.addItem(tr("fp32"), "fp32")
        self.precision.addItem(tr("fp64 — double precision trajectories (GPU: needs fp64 support, slower)"), "fp64")
        self.ss = QSpinBox()
        self.ss.setRange(1, 4)
        self.ss.setToolTip(tr("Supersampling: accumulate at N× resolution and box-filter down"))
        self.splat = QSpinBox()
        self.splat.setRange(0, 4)
        self.splat.setToolTip(tr("0 = bilinear anti-aliased sub-pixel splat; 1–4 = soft disk radius"))
        f.addRow(tr("Tier"), self.tier)
        f.addRow(tr("Points / pixel"), self.ppp)
        f.addRow("", self.points_label)
        f.addRow("", self.hint_label)
        f.addRow(tr("Engine"), self.engine)
        f.addRow(tr("Precision"), self.precision)
        f.addRow(tr("Supersampling"), self.ss)
        f.addRow(tr("Splat radius"), self.splat)
        lay.addWidget(g)

        # output
        g = QGroupBox(tr("Output"))
        f = QFormLayout(g)
        row = QHBoxLayout()
        self.folder = QLineEdit(self.qs.value("render/folder", str(Path.home() / "Attractr")))
        self.btn_folder = QPushButton("…")
        self.btn_folder.setFixedWidth(32)
        row.addWidget(self.folder, 1)
        row.addWidget(self.btn_folder)
        self.template = QLineEdit(self.qs.value("render/template", DEFAULT_TEMPLATE))
        self.template.setToolTip(tr("Fields: {name} {date} {time} {datetime} {w} {h} {seed} {style} {ppp}"))
        self.fmt = QComboBox()
        self.fmt.addItems(["png", "jpg", "webp", "tif"])
        self.bits = QComboBox()
        self.bits.addItems(["8", "16"])
        self.bits.setToolTip(tr("16-bit applies to PNG only"))
        f.addRow(tr("Folder"), row)
        f.addRow(tr("Name template"), self.template)
        f.addRow(tr("Format"), self.fmt)
        f.addRow(tr("Bit depth"), self.bits)
        lay.addWidget(g)

        # report
        g = QGroupBox(tr("Render report"))
        f = QFormLayout(g)
        self.report_on = QCheckBox(tr("Write a render report next to the image"))
        self.report_on.setChecked(self.qs.value("render/report", "true") == "true")
        self.report_fmt = QComboBox()
        for k in REPORT_FORMATS:
            self.report_fmt.addItem(REPORT_LABELS[k], k)
        self.report_fmt.setCurrentIndex(max(0, list(REPORT_FORMATS).index(self.qs.value("render/report_fmt", "md"))))
        self.report_dyn = QCheckBox(tr("Include dynamics (Lyapunov exponent, dimension)"))
        f.addRow(self.report_on)
        f.addRow(tr("Format"), self.report_fmt)
        f.addRow(self.report_dyn)
        lay.addWidget(g)

        btns = QHBoxLayout()
        self.estimate = QLabel("")
        self.estimate.setStyleSheet("color:#999")
        self.btn_render = QPushButton(tr("▶ Render"))
        self.btn_render.setDefault(True)
        self.btn_close = QPushButton(tr("Close"))
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
        self.preset.activated.connect(self._on_render_preset)
        self.btn_preset_save.clicked.connect(self._save_render_preset)
        self.btn_preset_del.clicked.connect(self._delete_render_preset)
        self.btn_close.clicked.connect(self.close)
        self.report_on.toggled.connect(self.report_fmt.setEnabled)
        self.report_on.toggled.connect(self.report_dyn.setEnabled)

        self.size_preset.setCurrentIndex(int(self.qs.value("render/size_preset", 2)))
        self._on_preset(self.size_preset.currentIndex())
        self.tier.setCurrentIndex(int(self.qs.value("render/tier", 1)))
        self._on_tier(self.tier.currentIndex())
        self.ss.setValue(int(self.qs.value("render/ss", 2)))
        self.splat.setValue(int(self.qs.value("render/splat", 0)))
        self._fill_render_presets()
        self._update_estimate()

    # ── render presets ─────────────────────────────────────────────────────────
    def _fill_render_presets(self) -> None:
        self.preset.clear()
        self.preset.addItem(tr("— current settings —"), None)
        for p in render_presets.all():
            self.preset.addItem(p.name + ("" if p.builtin else " (user)"), p.name)
            self.preset.setItemData(self.preset.count() - 1, p.summary, 3)  # Qt.ToolTipRole

    def current_preset(self, name: str = "custom") -> RenderPreset:
        """The dialog's values as a preset."""
        return RenderPreset(
            name, self.width.value(), self.height.value(), self.ppp.value(), self.ss.value(), self.splat.value(),
            self.engine.currentData(), self.precision.currentData(), self.fmt.currentText(), int(self.bits.currentText()),
            (self.report_fmt.currentData(),) if self.report_on.isChecked() else (), self.report_dyn.isChecked(),
        )

    def apply_preset(self, p: RenderPreset) -> None:
        self.size_preset.setCurrentIndex(len(SIZE_PRESETS) - 1)  # Custom
        self.width.setValue(p.width)
        self.height.setValue(p.height)
        self.tier.setCurrentIndex(len(QUALITY_TIERS) - 1)  # Custom
        self.ppp.setValue(p.points_per_pixel)
        self.ss.setValue(p.supersample)
        self.splat.setValue(p.splat_radius)
        self.engine.setCurrentIndex(max(0, self.engine.findData(p.engine)))
        self.precision.setCurrentIndex(max(0, self.precision.findData(p.precision)))
        self.fmt.setCurrentText(p.fmt)
        self.bits.setCurrentText(str(p.bit_depth))
        self.report_on.setChecked(bool(p.report_formats))
        if p.report_formats:
            self.report_fmt.setCurrentIndex(max(0, self.report_fmt.findData(p.report_formats[0])))
        self.report_dyn.setChecked(p.dynamics)
        self._update_estimate()

    def _on_render_preset(self, idx: int) -> None:
        name = self.preset.itemData(idx)
        if name and name in render_presets:
            self.apply_preset(render_presets.get(name))
            self.btn_preset_del.setEnabled(not render_presets.get(name).builtin)

    def _save_render_preset(self) -> None:
        name, ok = QInputDialog.getText(self, tr("Save render preset"), tr("Name:"), text=f"{self.width.value()}×{self.height.value()} {self.ppp.value():g} ppp")
        if not ok or not name.strip():
            return
        render_presets.save(self.current_preset(name.strip()))
        self._fill_render_presets()
        self.preset.setCurrentIndex(max(0, self.preset.findData(name.strip())))

    def _delete_render_preset(self) -> None:
        name = self.preset.currentData()
        if name and render_presets.delete(name):
            self._fill_render_presets()

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

    def _budget_boost(self) -> float:
        """Iteration multiplier of the current attractor (Poincaré sections plot sparsely)."""
        try:
            from attractr.core.render.pipeline import resolve_spec

            return float(resolve_spec(self.get_settings()).boost)
        except Exception:  # noqa: BLE001
            return 1.0

    def _update_estimate(self) -> None:
        boost = self._budget_boost()
        pts = self.ppp.value() * self.width.value() * self.height.value() * boost
        text = f"≈ {pts / 1e6:.0f} M points" if pts < 1e9 else f"≈ {pts / 1e9:.2f} G points"
        if boost > 1:
            text += f" (×{boost:g} — this attractor plots only a fraction of its steps)"
        self.points_label.setText(text)
        self.hint_label.setText(self.quality_hint(self.ppp.value()))
        self.hint_label.setVisible(bool(self.hint_label.text()))
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

    def quality_hint(self, ppp: float) -> str:
        """A warning when the current style wants more points per pixel than set."""
        try:
            style = self.get_settings().look.style
        except Exception:  # noqa: BLE001 — settings provider may not be ready
            return ""
        rec = RECOMMENDED_PPP.get(style, 8.0)
        if ppp >= rec:
            return ""
        return f"⚠ the {style.capitalize()} style looks best with ≥ {rec:g} points / pixel (now {ppp:g}); expect noise or holes"

    def showEvent(self, e) -> None:  # noqa: N802 — the style may have changed since the dialog was built
        super().showEvent(e)
        self._update_estimate()

    def _pick_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Output folder"), self.folder.text())
        if d:
            self.folder.setText(d)

    def _render(self) -> None:
        s: RenderSettings = self.get_settings()
        q = replace(s.quality, width=self.width.value(), height=self.height.value(), points_per_pixel=self.ppp.value(),
                    supersample=self.ss.value(), splat_radius=self.splat.value(), engine=self.engine.currentData(),
                    precision=self.precision.currentData())
        s = replace(s, quality=q)
        reports = [self.report_fmt.currentData()] if self.report_on.isChecked() else []
        job = RenderJob(s, Path(self.folder.text()).expanduser(), self.template.text() or DEFAULT_TEMPLATE,
                        fmt=self.fmt.currentText(), bit_depth=int(self.bits.currentText()), report_formats=reports,
                        dynamics=self.report_dyn.isChecked(), checkpoint_every=60.0 * float(self.qs.value("render/checkpoint_minutes", 2.0)))
        for k, v in (("render/folder", self.folder.text()), ("render/template", self.template.text()),
                     ("render/report", "true" if self.report_on.isChecked() else "false"),
                     ("render/report_fmt", self.report_fmt.currentData()), ("render/size_preset", self.size_preset.currentIndex()),
                     ("render/tier", self.tier.currentIndex()), ("render/ss", self.ss.value()), ("render/splat", self.splat.value())):
            self.qs.setValue(k, v)
        self.jobCreated.emit(job)
