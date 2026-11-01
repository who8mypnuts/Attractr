"""Look panel: style, colour source, palette, tone mapping, depth/lights, background."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from attractr.core.color.palettes import palettes
from attractr.core.render.settings import (
    BACKGROUND_MODES,
    COLOR_SOURCES,
    PROCEDURAL_BACKGROUNDS,
    STYLES,
    Look,
    RenderSettings,
)
from attractr.gui.state.document import Document
from attractr.gui.widgets.collapsible import Collapsible
from attractr.gui.widgets.color_button import ColorButton
from attractr.gui.widgets.gradient_bar import GradientBar
from attractr.gui.widgets.slider_spin import SliderSpin

STYLE_HELP = {
    "gas": "Log-density accumulation — the classic Chaoscope look.",
    "dust": "4th-root density — diffuse starfield / dust-cloud look.",
    "light": "Colour by orbit speed (or another source) × density, with optional bloom.",
    "liquid": "Depth-attenuated density with lighting from the nearest surface.",
    "solid": "Opaque lit surface where density exceeds the threshold.",
    "plasma": "Cyclic colour bands of density with optional glow.",
}


class LookPanel(QWidget):
    def __init__(self, doc: Document, parent=None) -> None:
        super().__init__(parent)
        self.doc = doc
        self._updating = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        scroll.setWidget(body)
        outer.addWidget(scroll)

        # ── style & colour ──────────────────────────────────────────────────────
        w = QWidget()
        f = QFormLayout(w)
        f.setContentsMargins(0, 0, 0, 0)
        self.style = QComboBox()
        self.style.addItems(list(STYLES))
        self.style_help = QLabel("")
        self.style_help.setWordWrap(True)
        self.style_help.setStyleSheet("color: #999; font-size: 11px;")
        self.color_source = QComboBox()
        self.color_source.addItems(list(COLOR_SOURCES))
        self.color_source.setToolTip("What drives the palette index (density = classic)")
        f.addRow("Style", self.style)
        f.addRow("", self.style_help)
        f.addRow("Colour by", self.color_source)
        lay.addWidget(Collapsible("Style", w))

        # ── palette ────────────────────────────────────────────────────────────
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.palette = QComboBox()
        for pid, g in palettes.items():
            self.palette.addItem(g.name, pid)
        self.palette.setToolTip("Built-in and user palettes")
        self.btn_edit_gradient = QPushButton("Edit…")
        self.btn_edit_gradient.setToolTip("Open the gradient editor")
        row.addWidget(self.palette, 1)
        row.addWidget(self.btn_edit_gradient)
        v.addLayout(row)
        self.gradient_bar = GradientBar(doc.settings.look.gradient)
        v.addWidget(self.gradient_bar)
        self.phase = SliderSpin("Phase", 0, 1, 0, decimals=3, hint="Rotate the palette (animatable)")
        self.cycles = SliderSpin("Cycles", 0.25, 8, 1, decimals=2, hint="Repeat the palette")
        v.addWidget(self.phase)
        v.addWidget(self.cycles)
        lay.addWidget(Collapsible("Palette", w))

        # ── tone ───────────────────────────────────────────────────────────────
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        self.percentile = SliderSpin("Percentile", 0.90, 1.0, 0.998, decimals=4, hint="Density percentile mapped to full brightness (lower = brighter, more clipping)")
        self.gamma = SliderSpin("Gamma", 0.2, 3.0, 1.0, decimals=2, log_scale=True)
        self.brightness = SliderSpin("Bright.", 0.2, 3.0, 1.0, decimals=2, log_scale=True)
        self.contrast = SliderSpin("Contrast", -0.9, 0.9, 0.0, decimals=2)
        for s in (self.percentile, self.gamma, self.brightness, self.contrast):
            v.addWidget(s)
        row = QHBoxLayout()
        self.equalize = QCheckBox("Full range (equalise)")
        self.invert = QCheckBox("Invert")
        self.caption = QCheckBox("Caption")
        self.caption.setToolTip("Draw the attractor name, formula and parameters on exported images")
        row.addWidget(self.equalize)
        row.addWidget(self.invert)
        row.addWidget(self.caption)
        v.addLayout(row)
        lay.addWidget(Collapsible("Tone mapping", w))

        # ── style extras ───────────────────────────────────────────────────────
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        self.depth_cue = SliderSpin("Depth cue", 0, 1, 0.5, decimals=2, hint="Dim far parts (3-D attractors)")
        self.bands = SliderSpin("Bands", 1, 16, 4, decimals=1, hint="Plasma: colour cycles across the density range")
        self.glow = SliderSpin("Glow", 0, 1, 0, decimals=2, hint="Bloom for Light / Plasma")
        self.solid_thr = SliderSpin("Threshold", 0.01, 0.8, 0.15, decimals=3, hint="Solid: density below this is background")
        for s in (self.depth_cue, self.bands, self.glow, self.solid_thr):
            v.addWidget(s)
        self.extras_section = Collapsible("Depth && style options", w, expanded=False)
        lay.addWidget(self.extras_section)

        # ── light ──────────────────────────────────────────────────────────────
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        self.l_az = SliderSpin("Azimuth", 0, 360, 135, decimals=0)
        self.l_el = SliderSpin("Elevation", 0, 90, 45, decimals=0)
        self.l_amb = SliderSpin("Ambient", 0, 1, 0.25, decimals=2)
        self.l_dif = SliderSpin("Diffuse", 0, 1.5, 0.75, decimals=2)
        self.l_spec = SliderSpin("Specular", 0, 1.5, 0.35, decimals=2)
        self.l_shin = SliderSpin("Shininess", 1, 128, 24, decimals=0, log_scale=True)
        for s in (self.l_az, self.l_el, self.l_amb, self.l_dif, self.l_spec, self.l_shin):
            v.addWidget(s)
        row = QHBoxLayout()
        row.addWidget(QLabel("Light colour"))
        self.l_color = ColorButton((1, 1, 1))
        row.addWidget(self.l_color)
        row.addStretch(1)
        v.addLayout(row)
        self.light_section = Collapsible("Lighting (Liquid / Solid)", w, expanded=False)
        lay.addWidget(self.light_section)

        # ── background ─────────────────────────────────────────────────────────
        w = QWidget()
        f = QFormLayout(w)
        f.setContentsMargins(0, 0, 0, 0)
        self.bg_mode = QComboBox()
        self.bg_mode.addItems(list(BACKGROUND_MODES))
        self.bg_color = ColorButton((0, 0, 0))
        self.bg_color2 = ColorButton((0.05, 0.02, 0.12))
        self.bg_proc = QComboBox()
        self.bg_proc.addItems(list(PROCEDURAL_BACKGROUNDS))
        self.bg_image = QPushButton("Choose image…")
        f.addRow("Mode", self.bg_mode)
        f.addRow("Colour", self.bg_color)
        f.addRow("Colour 2", self.bg_color2)
        f.addRow("Procedural", self.bg_proc)
        f.addRow("Image", self.bg_image)
        lay.addWidget(Collapsible("Background", w, expanded=False))
        lay.addStretch(1)

        # ── wiring ─────────────────────────────────────────────────────────────
        self.style.currentTextChanged.connect(lambda t: self._set(style=t))
        self.color_source.currentTextChanged.connect(lambda t: self._set(color_source=t))
        self.palette.currentIndexChanged.connect(self._on_palette)
        self.equalize.toggled.connect(lambda b: self._set(equalize=b))
        self.invert.toggled.connect(lambda b: self._set(invert=b))
        self.caption.toggled.connect(lambda b: self._set(caption=b))
        for name, s in (("phase", self.phase), ("cycles", self.cycles), ("percentile", self.percentile),
                        ("gamma", self.gamma), ("brightness", self.brightness), ("contrast", self.contrast),
                        ("depth_cue", self.depth_cue), ("bands", self.bands), ("glow", self.glow),
                        ("solid_threshold", self.solid_thr)):
            s.valueChanged.connect(lambda v, n=name: self._set(**{n: v}, merge=n))
            s.interactionStarted.connect(doc.begin_interaction)
            s.interactionEnded.connect(doc.end_interaction)
        for name, s in (("azimuth", self.l_az), ("elevation", self.l_el), ("ambient", self.l_amb),
                        ("diffuse", self.l_dif), ("specular", self.l_spec), ("shininess", self.l_shin)):
            s.valueChanged.connect(lambda v, n=name: self._set_light(**{n: v}))
            s.interactionStarted.connect(doc.begin_interaction)
            s.interactionEnded.connect(doc.end_interaction)
        self.l_color.colorChanged.connect(lambda c: self._set_light(color=c))
        self.bg_mode.currentTextChanged.connect(lambda t: self._set_bg(mode=t))
        self.bg_color.colorChanged.connect(lambda c: self._set_bg(color=c))
        self.bg_color2.colorChanged.connect(lambda c: self._set_bg(color2=c))
        self.bg_proc.currentTextChanged.connect(lambda t: self._set_bg(procedural=t))
        self.bg_image.clicked.connect(self._pick_image)
        self.btn_edit_gradient.clicked.connect(self.open_gradient_editor)
        self.gradient_bar.clicked.connect(self.open_gradient_editor)
        self._editor = None
        doc.changed.connect(self.sync)
        self.sync(doc.settings, frozenset({"look"}))

    # ── sync from document ─────────────────────────────────────────────────────
    def sync(self, settings: RenderSettings, tags: frozenset) -> None:
        if "look" not in tags and "attractor" not in tags:
            return
        look = settings.look
        self._updating = True
        try:
            self.style.setCurrentText(look.style)
            self.style_help.setText(STYLE_HELP.get(look.style, ""))
            self.color_source.setCurrentText(look.color_source)
            self.gradient_bar.set_gradient(look.gradient, look.phase, look.cycles)
            idx = self.palette.findText(look.gradient.name)
            self.palette.setCurrentIndex(idx if idx >= 0 else -1)
            self.phase.set_value(look.phase)
            self.cycles.set_value(look.cycles)
            self.percentile.set_value(look.percentile)
            self.gamma.set_value(look.gamma)
            self.brightness.set_value(look.brightness)
            self.contrast.set_value(look.contrast)
            self.equalize.setChecked(look.equalize)
            self.invert.setChecked(look.invert)
            self.caption.setChecked(look.caption)
            self.depth_cue.set_value(look.depth_cue)
            self.bands.set_value(look.bands)
            self.glow.set_value(look.glow)
            self.solid_thr.set_value(look.solid_threshold)
            li = look.light
            self.l_az.set_value(li.azimuth)
            self.l_el.set_value(li.elevation)
            self.l_amb.set_value(li.ambient)
            self.l_dif.set_value(li.diffuse)
            self.l_spec.set_value(li.specular)
            self.l_shin.set_value(li.shininess)
            self.l_color.set_rgb(li.color)
            bg = look.background
            self.bg_mode.setCurrentText(bg.mode)
            self.bg_color.set_rgb(bg.color)
            self.bg_color2.set_rgb(bg.color2)
            self.bg_proc.setCurrentText(bg.procedural)
            self.light_section.setVisible(look.style in ("liquid", "solid"))
            self.bands.setVisible(look.style == "plasma")
            self.glow.setVisible(look.style in ("plasma", "light"))
            self.solid_thr.setVisible(look.style == "solid")
        finally:
            self._updating = False

    # ── mutations ──────────────────────────────────────────────────────────────
    def _set(self, merge: str | None = None, **kw) -> None:
        if self._updating:
            return
        look: Look = replace(self.doc.settings.look, **kw)
        self.doc.set_look(look, text=f"Look: {', '.join(kw)}", merge_key=merge)

    def _set_light(self, **kw) -> None:
        if self._updating:
            return
        look = self.doc.settings.look
        self.doc.set_look(replace(look, light=replace(look.light, **kw)), text="Light", merge_key="light")

    def _set_bg(self, **kw) -> None:
        if self._updating:
            return
        look = self.doc.settings.look
        self.doc.set_look(replace(look, background=replace(look.background, **kw)), text="Background")

    def _on_palette(self, idx: int) -> None:
        if self._updating or idx < 0:
            return
        pid = self.palette.itemData(idx)
        self._set(gradient=palettes.get(pid))

    def open_gradient_editor(self) -> None:
        from attractr.gui.widgets.gradient_editor import GradientEditor

        if self._editor is None:
            self._editor = GradientEditor(self.doc.settings.look.gradient, self)
            self._editor.gradientChanged.connect(lambda g: self._set(gradient=g, merge="gradient"))
            self._editor.editingFinished.connect(self.doc.end_merge)
        else:
            self._editor.set_gradient(self.doc.settings.look.gradient)
        self._editor.show()
        self._editor.raise_()

    def _pick_image(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(self, "Background image", "", "Images (*.png *.jpg *.jpeg *.webp *.tif)")
        if path:
            self._set_bg(mode="image", image_path=path)
