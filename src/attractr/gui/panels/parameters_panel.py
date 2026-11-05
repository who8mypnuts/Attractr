"""Parameters panel: a SliderSpin per attractor parameter + integrator controls."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from attractr.core.attractors.spec import AttractorSpec
from attractr.core.render.settings import INTEGRATORS, RenderSettings
from attractr.gui.state.document import Document
from attractr.gui.widgets.collapsible import Collapsible
from attractr.gui.widgets.slider_spin import SliderSpin
from attractr.gui.widgets.xy_pad import XYPad
from attractr.i18n import tr


class ParametersPanel(QWidget):
    def __init__(self, doc: Document, parent=None) -> None:
        super().__init__(parent)
        self.doc = doc
        self.sliders: dict[str, SliderSpin] = {}
        self.locked: set[str] = set()
        self._building = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        self.title = QLabel("")
        self.title.setStyleSheet("font-weight: 600; color: #9fd8ff;")
        outer.addWidget(self.title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        self.body_lay = QVBoxLayout(body)
        self.body_lay.setContentsMargins(0, 0, 0, 0)
        self.body_lay.setSpacing(4)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self.params_box = QWidget()
        self.params_lay = QVBoxLayout(self.params_box)
        self.params_lay.setContentsMargins(0, 0, 0, 0)
        self.params_lay.setSpacing(3)
        self.body_lay.addWidget(Collapsible("Parameters", self.params_box))

        # integrator group (flows only)
        integ = QWidget()
        form = QFormLayout(integ)
        form.setContentsMargins(0, 0, 0, 0)
        self.integrator = QComboBox()
        self.integrator.addItems(list(INTEGRATORS))
        self.integrator.setToolTip(tr("RK4 is accurate; Euler (legacy) reproduces the Android Chaoscope look at the same dt"))
        self.dt = SliderSpin("dt", 1e-4, 0.1, 0.01, decimals=6, log_scale=True, hint="Integration time step")
        self.substeps = QSpinBox()
        self.substeps.setRange(1, 32)
        self.substeps.setToolTip(tr("Integrator steps per plotted point (smoother curves without changing dt)"))
        form.addRow(tr("Integrator"), self.integrator)
        form.addRow(self.dt)
        form.addRow(tr("Sub-steps"), self.substeps)
        self.integ_section = Collapsible("Integration", integ, expanded=False)
        self.body_lay.addWidget(self.integ_section)
        self.xy_pad = XYPad(doc)
        self.body_lay.addWidget(Collapsible("XY pad", self.xy_pad, expanded=False))
        self.body_lay.addStretch(1)

        btns = QHBoxLayout()
        self.btn_random = QPushButton(tr("🎲 Randomize"))
        self.btn_random.setToolTip(tr("Random values for all unlocked parameters"))
        self.btn_reset = QPushButton(tr("Reset"))
        self.btn_surprise = QPushButton(tr("✨ Surprise me"))
        self.btn_surprise.setToolTip(tr("Random attractor, parameters, camera and palette"))
        btns.addWidget(self.btn_random)
        btns.addWidget(self.btn_reset)
        btns.addWidget(self.btn_surprise)
        outer.addLayout(btns)

        self.btn_random.clicked.connect(lambda: self.doc.randomize_params(self.locked))
        self.btn_reset.clicked.connect(self.doc.reset_params)
        self.btn_surprise.clicked.connect(self.doc.randomize_all)
        self.integrator.currentTextChanged.connect(self._on_integrator)
        self.dt.valueChanged.connect(self._on_dt)
        self.dt.interactionStarted.connect(self.doc.begin_interaction)
        self.dt.interactionEnded.connect(self.doc.end_interaction)
        self.substeps.valueChanged.connect(self._on_substeps)

        doc.attractorChanged.connect(self.rebuild)
        doc.changed.connect(self.sync)
        self.rebuild(doc.spec)

    # ── build ──────────────────────────────────────────────────────────────────
    def rebuild(self, spec: AttractorSpec) -> None:
        self._building = True
        for s in self.sliders.values():
            s.setParent(None)
            s.deleteLater()
        self.sliders.clear()
        self.locked.clear()
        self.title.setText(f"{spec.name}  ·  {spec.kind} · {spec.dims}-D")
        vals = self.doc.settings.param_dict
        for p in spec.params:
            s = SliderSpin(p.name, p.lo, p.hi, vals.get(p.name, p.default), is_int=p.is_int, hint=p.hint,
                           default=p.default, show_lock=True)
            s.valueChanged.connect(lambda v, n=p.name: self._on_param(n, v))
            s.interactionStarted.connect(self.doc.begin_interaction)
            s.interactionEnded.connect(self.doc.end_interaction)
            s.lockToggled.connect(lambda on, n=p.name: self.locked.add(n) if on else self.locked.discard(n))
            s.seed_history(self.doc.history_for(p.name))
            s.valueCommitted.connect(lambda v, n=p.name: self.doc.remember_param(n, v))
            self.params_lay.addWidget(s)
            self.sliders[p.name] = s
        if not spec.params:
            lbl = QLabel(tr("This system has no free parameters."))
            lbl.setStyleSheet("color: #888;")
            self.params_lay.addWidget(lbl)
            self.sliders["__none__"] = lbl  # type: ignore[assignment]
        self.integ_section.setVisible(spec.is_flow)
        q = self.doc.settings.quality
        self.dt.set_range(spec.dt / 20.0, spec.dt * 10.0)
        self.dt.set_value(q.dt or spec.dt)
        self.dt.default = spec.dt
        self._building = False
        self.sync(self.doc.settings, frozenset({"params", "quality"}))

    def sync(self, settings: RenderSettings, tags: frozenset) -> None:
        if self._building:
            return
        if "params" in tags or "attractor" in tags:
            for name, v in settings.param_dict.items():
                s = self.sliders.get(name)
                if isinstance(s, SliderSpin) and abs(s.value() - v) > 1e-12:
                    s.set_value(v)
        if "quality" in tags or "attractor" in tags:
            q = settings.quality
            self.integrator.blockSignals(True)
            self.integrator.setCurrentText(q.integrator)
            self.integrator.blockSignals(False)
            self.dt.set_value(q.dt or self.doc.spec.dt)
            self.substeps.blockSignals(True)
            self.substeps.setValue(q.substeps)
            self.substeps.blockSignals(False)

    # ── slots ──────────────────────────────────────────────────────────────────
    def _on_param(self, name: str, v: float) -> None:
        if self._building:
            return
        self.doc.set_param(name, v, interactive=True)

    def _on_integrator(self, text: str) -> None:
        if not self._building:
            self.doc.set_quality(replace(self.doc.settings.quality, integrator=text), "Integrator")

    def _on_dt(self, v: float) -> None:
        if not self._building:
            self.doc.apply(replace(self.doc.settings, quality=replace(self.doc.settings.quality, dt=v)), "dt", {"quality"}, merge_key="dt")

    def _on_substeps(self, n: int) -> None:
        if not self._building:
            self.doc.set_quality(replace(self.doc.settings.quality, substeps=n), "Sub-steps")
