"""Timeline panel: transport, tracks with keyframe diamonds, playhead scrubbing, helpers."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from attractr.core.animation import helpers
from attractr.core.animation.easing import EASINGS
from attractr.gui.controllers.animation_controller import AnimationController
from attractr.gui.state.document import Document
from attractr.i18n import tr

LABEL_W = 150
ROW_H = 22
RULER_H = 24


class TrackArea(QWidget):
    """Draws the ruler, one row per track with key diamonds, and the playhead."""

    seek = Signal(float)
    keySelected = Signal(str, float)  # path, time
    removeKey = Signal(str, float)
    removeTrack = Signal(str)

    def __init__(self, ctrl: AnimationController, parent=None) -> None:
        super().__init__(parent)
        self.ctrl = ctrl
        self.selected: tuple[str, float] | None = None
        self._dragging = False
        self.setMinimumHeight(RULER_H + ROW_H * 2)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    def tracks(self):
        return sorted(self.ctrl.timeline.tracks.values(), key=lambda t: (not t.path.startswith("params."), t.path))

    def refresh(self) -> None:
        self.setMinimumHeight(RULER_H + ROW_H * max(2, len(self.ctrl.timeline.tracks) + 1))
        self.update()

    def _x(self, t: float) -> float:
        d = max(self.ctrl.timeline.duration, 1e-6)
        return LABEL_W + 8 + (self.width() - LABEL_W - 16) * t / d

    def _t(self, x: float) -> float:
        d = self.ctrl.timeline.duration
        return min(max((x - LABEL_W - 8) / max(self.width() - LABEL_W - 16, 1) * d, 0.0), d)

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(14, 14, 20))
        tl = self.ctrl.timeline
        # ruler
        p.fillRect(QRectF(LABEL_W, 0, self.width() - LABEL_W, RULER_H), QColor(22, 22, 32))
        p.setPen(QColor(120, 120, 140))
        step = _nice_step(tl.duration)
        t = 0.0
        while t <= tl.duration + 1e-9:
            x = self._x(t)
            p.drawLine(QPointF(x, RULER_H - 6), QPointF(x, RULER_H))
            p.drawText(QPointF(x + 2, RULER_H - 9), f"{t:g}s")
            t += step
        # frame ticks
        p.setPen(QColor(50, 50, 70))
        if tl.frame_count <= 600:
            for i in range(tl.frame_count + 1):
                x = self._x(tl.frame_time(i))
                p.drawLine(QPointF(x, RULER_H - 3), QPointF(x, RULER_H))
        # tracks
        y = RULER_H
        for trk in self.tracks():
            p.fillRect(QRectF(0, y, self.width(), ROW_H), QColor(18, 18, 26) if (y // ROW_H) % 2 else QColor(16, 16, 23))
            p.setPen(QColor(200, 205, 220))
            p.drawText(QRectF(6, y, LABEL_W - 10, ROW_H), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, trk.label)
            p.setPen(QPen(QColor(60, 60, 90), 1))
            p.drawLine(QPointF(self._x(0), y + ROW_H / 2), QPointF(self._x(tl.duration), y + ROW_H / 2))
            for k in trk.keys:
                x = self._x(k.time)
                cy = y + ROW_H / 2
                sel = self.selected == (trk.path, k.time)
                poly = QPolygonF([QPointF(x, cy - 6), QPointF(x + 6, cy), QPointF(x, cy + 6), QPointF(x - 6, cy)])
                p.setBrush(QColor(255, 200, 80) if sel else QColor(79, 195, 247))
                p.setPen(QPen(QColor(255, 255, 255) if sel else QColor(20, 20, 30), 1))
                p.drawPolygon(poly)
            y += ROW_H
        # playhead
        x = self._x(self.ctrl.time)
        p.setPen(QPen(QColor(255, 90, 90), 1.5))
        p.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        p.setBrush(QColor(255, 90, 90))
        p.drawPolygon(QPolygonF([QPointF(x - 6, 0), QPointF(x + 6, 0), QPointF(x, 9)]))
        p.end()

    def mousePressEvent(self, e) -> None:  # noqa: N802
        pos = e.position()
        if pos.x() < LABEL_W:
            return
        row = int((pos.y() - RULER_H) // ROW_H)
        trs = self.tracks()
        if 0 <= row < len(trs) and e.button() == Qt.MouseButton.LeftButton:
            trk = trs[row]
            for k in trk.keys:
                if abs(self._x(k.time) - pos.x()) <= 7:
                    self.selected = (trk.path, k.time)
                    self.keySelected.emit(trk.path, k.time)
                    self.update()
                    return
        self._dragging = True
        self.seek.emit(self._t(pos.x()))

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._dragging:
            self.seek.emit(self._t(e.position().x()))

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        self._dragging = False

    def _menu(self, pos) -> None:
        row = int((pos.y() - RULER_H) // ROW_H)
        trs = self.tracks()
        m = QMenu(self)
        if 0 <= row < len(trs):
            trk = trs[row]
            t = self._t(pos.x())
            near = [k for k in trk.keys if abs(self._x(k.time) - pos.x()) <= 7]
            if near:
                m.addAction(f"Delete key at {near[0].time:.2f}s", lambda: self.removeKey.emit(trk.path, near[0].time))
            m.addAction(f"Add key here ({t:.2f}s)", lambda: self._add_key(trk.path, t))
            m.addAction(f"Remove track '{trk.label}'", lambda: self.removeTrack.emit(trk.path))
        if m.actions():
            m.exec(self.mapToGlobal(pos))

    def _add_key(self, path: str, t: float) -> None:
        from attractr.core.animation.timeline import get_path

        self.ctrl.timeline.set_key(path, t, get_path(self.ctrl.doc.settings, path))
        self.ctrl.store()


def _nice_step(duration: float) -> float:
    for s in (0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60):
        if duration / s <= 12:
            return s
    return 120.0


class TimelinePanel(QWidget):
    renderRequested = Signal()

    def __init__(self, doc: Document, ctrl: AnimationController, parent=None) -> None:
        super().__init__(parent)
        self.doc = doc
        self.ctrl = ctrl
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        # transport row
        row = QHBoxLayout()
        self.btn_play = QPushButton("▶")
        self.btn_stop = QPushButton("⏹")
        self.btn_start = QPushButton("⏮")
        self.btn_end = QPushButton("⏭")
        for b in (self.btn_start, self.btn_play, self.btn_stop, self.btn_end):
            b.setFixedWidth(36)
            row.addWidget(b)
        self.time_label = QLabel(tr("0.00 s · frame 0"))
        self.time_label.setMinimumWidth(140)
        row.addWidget(self.time_label)
        row.addWidget(QLabel(tr("Duration")))
        self.duration = QDoubleSpinBox()
        self.duration.setRange(0.1, 3600)
        self.duration.setSuffix(tr(" s"))
        self.duration.setDecimals(2)
        row.addWidget(self.duration)
        row.addWidget(QLabel(tr("fps")))
        self.fps = QSpinBox()
        self.fps.setRange(1, 120)
        row.addWidget(self.fps)
        self.loop = QComboBox()
        self.loop.addItems(["none", "loop", "pingpong"])
        row.addWidget(self.loop)
        self.auto_key = QCheckBox(tr("Auto-key"))
        self.auto_key.setToolTip(tr("Record edits of animated properties as keyframes at the playhead"))
        row.addWidget(self.auto_key)
        row.addStretch(1)
        self.btn_render = QPushButton(tr("🎞 Render animation…"))
        row.addWidget(self.btn_render)
        lay.addLayout(row)

        # key row
        row = QHBoxLayout()
        for text, fn in (("◆ Key all", ctrl.key_all), ("◆ Params", ctrl.key_params), ("◆ Camera", ctrl.key_camera), ("◆ Look", ctrl.key_look)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        self.btn_del_key = QPushButton(tr("Delete keys at playhead"))
        row.addWidget(self.btn_del_key)
        row.addWidget(QLabel(tr("Easing")))
        self.easing = QComboBox()
        self.easing.addItems(list(EASINGS))
        self.easing.setToolTip(tr("Easing of the selected key into the next one"))
        row.addWidget(self.easing)
        self.btn_helpers = QToolButton()
        self.btn_helpers.setText(tr("Helpers ▾"))
        self.btn_helpers.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.btn_helpers)
        menu.addAction("Turntable (yaw)…", lambda: self._turntable("yaw"))
        menu.addAction("Turntable (pitch)…", lambda: self._turntable("pitch"))
        menu.addAction("Turntable (roll)…", lambda: self._turntable("roll"))
        menu.addAction("Morph: current → set B…", self._morph)
        menu.addAction("Parameter sweep (random target)", self._sweep)
        menu.addAction("Palette cycle", self._palette_cycle)
        menu.addAction("Zoom in ×4", self._zoom)
        menu.addAction("Orbit trace (single trajectory)", self._orbit)
        menu.addSeparator()
        menu.addAction("Clear timeline", ctrl.clear)
        self.btn_helpers.setMenu(menu)
        row.addWidget(self.btn_helpers)
        row.addStretch(1)
        lay.addLayout(row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.area = TrackArea(ctrl)
        scroll.setWidget(self.area)
        lay.addWidget(scroll, 1)
        self._morph_a = None

        # wiring
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_stop.clicked.connect(ctrl.stop)
        self.btn_start.clicked.connect(lambda: ctrl.set_time(0.0))
        self.btn_end.clicked.connect(lambda: ctrl.set_time(ctrl.timeline.duration))
        self.duration.valueChanged.connect(ctrl.set_duration)
        self.fps.valueChanged.connect(ctrl.set_fps)
        self.loop.currentTextChanged.connect(ctrl.set_loop)
        self.auto_key.toggled.connect(lambda b: setattr(ctrl, "auto_key", b))
        self.btn_del_key.clicked.connect(lambda: ctrl.remove_keys_at(ctrl.time))
        self.btn_render.clicked.connect(self.renderRequested)
        self.area.seek.connect(ctrl.set_time)
        self.area.removeKey.connect(lambda p, t: (ctrl.timeline.track(p).remove_key_at(t), ctrl.store()))
        self.area.removeTrack.connect(ctrl.remove_track)
        self.area.keySelected.connect(self._on_key_selected)
        self.easing.currentTextChanged.connect(self._on_easing)
        ctrl.timelineChanged.connect(self._sync)
        ctrl.timeChanged.connect(self._on_time)
        ctrl.playingChanged.connect(lambda on: self.btn_play.setText("⏸" if on else "▶"))
        self._sync()

    def _sync(self) -> None:
        tl = self.ctrl.timeline
        for w in (self.duration, self.fps, self.loop):
            w.blockSignals(True)
        self.duration.setValue(tl.duration)
        self.fps.setValue(tl.fps)
        self.loop.setCurrentText(tl.loop)
        for w in (self.duration, self.fps, self.loop):
            w.blockSignals(False)
        self.area.refresh()
        self._on_time(self.ctrl.time)

    def _on_time(self, t: float) -> None:
        self.time_label.setText(f"{t:.2f} s · frame {int(round(t * self.ctrl.timeline.fps))}")
        self.area.update()

    def _toggle_play(self) -> None:
        if self.ctrl.playing:
            self.ctrl.pause()
        else:
            self.ctrl.play()

    def _on_key_selected(self, path: str, t: float) -> None:
        trk = self.ctrl.timeline.tracks.get(path)
        if trk:
            for k in trk.keys:
                if abs(k.time - t) < 1e-9:
                    self.easing.blockSignals(True)
                    self.easing.setCurrentText(k.easing)
                    self.easing.blockSignals(False)
        self.ctrl.set_time(t)

    def _on_easing(self, name: str) -> None:
        sel = self.area.selected
        if sel is None:
            return
        trk = self.ctrl.timeline.tracks.get(sel[0])
        if trk:
            for i, k in enumerate(trk.keys):
                if abs(k.time - sel[1]) < 1e-9:
                    from dataclasses import replace

                    trk.keys[i] = replace(k, easing=name)
            self.ctrl.store()

    # ── helpers ────────────────────────────────────────────────────────────────
    def _turntable(self, axis: str) -> None:
        rev, ok = QInputDialog.getDouble(self, tr("Turntable"), tr("Revolutions:"), 1.0, 0.25, 20.0, 2)
        if ok:
            tl = helpers.turntable(self.doc.settings, self.duration.value(), self.fps.value(), axis, rev)
            self.ctrl.set_timeline(tl, self.doc.settings)

    def _morph(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        if self._morph_a is None:
            self._morph_a = self.doc.settings
            QMessageBox.information(self, tr("Morph"), tr("State A captured. Now change parameters / camera to the destination and pick Morph again to capture B."))
            return
        tl = helpers.morph(self._morph_a, self.doc.settings, self.duration.value(), self.fps.value())
        base = self._morph_a
        self._morph_a = None
        self.ctrl.set_timeline(tl, base)

    def _sweep(self) -> None:
        tl = helpers.param_sweep(self.doc.settings, self.doc.spec, self.duration.value(), self.fps.value())
        self.ctrl.set_timeline(tl, self.doc.settings)

    def _palette_cycle(self) -> None:
        self.ctrl.set_timeline(helpers.palette_cycle(self.doc.settings, self.duration.value(), self.fps.value()), self.doc.settings)

    def _zoom(self) -> None:
        self.ctrl.set_timeline(helpers.zoom_in(self.doc.settings, 4.0, self.duration.value(), self.fps.value()), self.doc.settings)

    def _orbit(self) -> None:
        tl, base = helpers.orbit_trace(self.doc.settings, self.duration.value(), self.fps.value())
        self.ctrl.set_timeline(tl, base)
