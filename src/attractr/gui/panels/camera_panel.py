"""Camera panel: yaw / pitch / roll / zoom / pan / perspective / fit."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from attractr.core.render.camera import FIT_MODES
from attractr.core.render.settings import RenderSettings
from attractr.gui.state.document import Document
from attractr.gui.widgets.slider_spin import SliderSpin


class CameraPanel(QWidget):
    def __init__(self, doc: Document, parent=None) -> None:
        super().__init__(parent)
        self.doc = doc
        self._updating = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        self.yaw = SliderSpin("Yaw", -180, 180, 0, decimals=1, hint="Rotation about the vertical axis (°)")
        self.pitch = SliderSpin("Pitch", -90, 90, 0, decimals=1, hint="Tilt (°)")
        self.roll = SliderSpin("Roll", -180, 180, 0, decimals=1, hint="Rotation in the screen plane (°)")
        self.zoom = SliderSpin("Zoom", 0.1, 8, 1, decimals=3, log_scale=True)
        self.pan_u = SliderSpin("Pan X", -1, 1, 0, decimals=3)
        self.pan_v = SliderSpin("Pan Y", -1, 1, 0, decimals=3)
        self.persp = SliderSpin("Persp.", 0, 1, 0, decimals=2, hint="0 = orthographic … 1 = strong perspective")
        for s in (self.yaw, self.pitch, self.roll, self.zoom, self.pan_u, self.pan_v, self.persp):
            lay.addWidget(s)
            s.valueChanged.connect(self._on_change)
            s.interactionStarted.connect(doc.begin_interaction)
            s.interactionEnded.connect(doc.end_interaction)
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)
        self.fit = QComboBox()
        self.fit.addItems(list(FIT_MODES))
        self.fit.setToolTip("bbox: tight 2-D fit for stills · sphere: rotation-invariant framing for animations")
        form.addRow("Framing", self.fit)
        lay.addLayout(form)
        btns = QHBoxLayout()
        self.btn_reset = QPushButton("Reset camera")
        self.btn_front = QPushButton("Front")
        self.btn_top = QPushButton("Top")
        self.btn_side = QPushButton("Side")
        for b in (self.btn_reset, self.btn_front, self.btn_top, self.btn_side):
            btns.addWidget(b)
        lay.addLayout(btns)
        lay.addStretch(1)
        self.fit.currentTextChanged.connect(self._on_fit)
        self.btn_reset.clicked.connect(doc.reset_camera)
        self.btn_front.clicked.connect(lambda: self._preset(0, 0, 0))
        self.btn_top.clicked.connect(lambda: self._preset(0, 89.9, 0))
        self.btn_side.clicked.connect(lambda: self._preset(90, 0, 0))
        doc.changed.connect(self.sync)
        self.sync(doc.settings, frozenset({"camera"}))

    def sync(self, settings: RenderSettings, tags: frozenset) -> None:
        if "camera" not in tags and "attractor" not in tags:
            return
        cam = settings.camera
        yaw, pitch, roll = cam.euler
        self._updating = True
        self.yaw.set_value(yaw)
        self.pitch.set_value(pitch)
        self.roll.set_value(roll)
        self.zoom.set_value(cam.zoom)
        self.pan_u.set_value(cam.pan_u)
        self.pan_v.set_value(cam.pan_v)
        self.persp.set_value(cam.perspective)
        self.fit.blockSignals(True)
        self.fit.setCurrentText(cam.fit)
        self.fit.blockSignals(False)
        is3d = self.doc.spec.is_3d
        for s in (self.yaw, self.pitch, self.roll, self.persp):
            s.setEnabled(is3d)
        self._updating = False

    def _on_change(self, _v: float) -> None:
        if self._updating:
            return
        cam = self.doc.settings.camera.with_euler(self.yaw.value(), self.pitch.value(), self.roll.value())
        cam = replace(cam, zoom=self.zoom.value(), pan_u=self.pan_u.value(), pan_v=self.pan_v.value(),
                      perspective=self.persp.value())
        self.doc.set_camera(cam, interactive=True)

    def _on_fit(self, text: str) -> None:
        if not self._updating:
            self.doc.set_camera(replace(self.doc.settings.camera, fit=text), text="Framing mode")

    def _preset(self, yaw: float, pitch: float, roll: float) -> None:
        self.doc.set_camera(self.doc.settings.camera.with_euler(yaw, pitch, roll), text="Camera preset")
