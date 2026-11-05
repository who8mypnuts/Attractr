"""SliderSpin: label + slider + spin box with an editable soft range, lock and reset.

Scrubbing ergonomics (all relative to the soft range):

* mouse wheel over the slider or the spin box: 1 % per notch — **Ctrl** 0.1 % (fine),
  **Shift** 10 % (coarse);
* ← / → on the slider: 1 % — **Shift** 10 %, **Ctrl** 0.1 %; Page Up/Down 10 %;
* the − / + nudge buttons: 1 % per click (auto-repeat) with the same modifiers;
* the context menu keeps the last 20 committed values ("Recent values"), plus copy/paste.
"""

from __future__ import annotations

import math
from collections import deque

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QSlider,
    QToolButton,
    QWidget,
)

from attractr.i18n import tr

SLIDER_STEPS = 20000
NUDGE = 0.01  # fraction of the soft range per wheel notch / arrow key / nudge click
HISTORY = 20


def modifier_scale(mods) -> float:
    """Ctrl → ×0.1 (fine), Shift → ×10 (coarse)."""
    if mods & Qt.KeyboardModifier.ControlModifier:
        return 0.1
    if mods & Qt.KeyboardModifier.ShiftModifier:
        return 10.0
    return 1.0


class RangeDialog(QDialog):
    def __init__(self, lo: float, hi: float, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Slider range"))
        form = QFormLayout(self)
        self.lo = QDoubleSpinBox()
        self.hi = QDoubleSpinBox()
        for sb, v in ((self.lo, lo), (self.hi, hi)):
            sb.setDecimals(6)
            sb.setRange(-1e9, 1e9)
            sb.setValue(v)
        form.addRow(tr("Minimum"), self.lo)
        form.addRow(tr("Maximum"), self.hi)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)


class SliderSpin(QWidget):
    valueChanged = Signal(float)
    interactionStarted = Signal()
    interactionEnded = Signal()
    lockToggled = Signal(bool)
    resetRequested = Signal()
    valueCommitted = Signal(float)  # a value entered the history (release, spin edit, nudge, paste)

    def __init__(self, label: str, lo: float, hi: float, value: float, *, decimals: int = 4,
                 is_int: bool = False, log_scale: bool = False, hint: str = "", default: float | None = None,
                 show_lock: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.lo, self.hi = float(lo), float(hi)
        if self.hi <= self.lo:
            self.hi = self.lo + 1.0
        self.is_int = is_int
        self.log_scale = log_scale and self.lo > 0
        self.default = value if default is None else default
        self.locked = False
        self._updating = False

        self.label = QLabel(label)
        self.label.setMinimumWidth(44)
        self.label.setToolTip(hint)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, SLIDER_STEPS)
        self.slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.spin = QDoubleSpinBox()
        self.spin.setDecimals(0 if is_int else decimals)
        self.spin.setRange(-1e12, 1e12)
        self.spin.setSingleStep(1 if is_int else (self.hi - self.lo) / 200.0)
        self.spin.setKeyboardTracking(False)
        self.spin.setMinimumWidth(86)
        self.spin.setToolTip(hint)
        self.lock_btn = QToolButton()
        self.lock_btn.setText("🔒")
        self.lock_btn.setCheckable(True)
        self.lock_btn.setToolTip(tr("Lock (excluded from randomize)"))
        self.lock_btn.setVisible(show_lock)
        self.lock_btn.toggled.connect(self._on_lock)
        self.nudge_down = QToolButton()
        self.nudge_up = QToolButton()
        for b, txt, sign in ((self.nudge_down, "−", -1), (self.nudge_up, "+", 1)):
            b.setText(txt)
            b.setFixedWidth(18)
            b.setAutoRepeat(True)
            b.setAutoRepeatDelay(300)
            b.setAutoRepeatInterval(60)
            b.setToolTip(tr("Nudge by 1 % of the range (Shift: 10 %, Ctrl: 0.1 %)"))
            b.clicked.connect(lambda _=False, sg=sign: self.nudge(sg * NUDGE * modifier_scale(QGuiApplication.keyboardModifiers())))
        self.history: deque[float] = deque(maxlen=HISTORY)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self.label)
        lay.addWidget(self.nudge_down)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.nudge_up)
        lay.addWidget(self.spin)
        lay.addWidget(self.lock_btn)

        self.set_value(value)
        self._apply_steps()
        self.slider.valueChanged.connect(self._on_slider)
        self.slider.sliderPressed.connect(self.interactionStarted)
        self.slider.sliderReleased.connect(self._on_release)
        self.spin.valueChanged.connect(self._on_spin)
        self.slider.installEventFilter(self)
        self.spin.installEventFilter(self)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    # ── scrubbing ergonomics ───────────────────────────────────────────────────
    def _apply_steps(self) -> None:
        self.slider.setSingleStep(int(SLIDER_STEPS * NUDGE))
        self.slider.setPageStep(int(SLIDER_STEPS * NUDGE * 10))
        self.spin.setSingleStep(1 if self.is_int else (self.hi - self.lo) * NUDGE * 0.5)

    def nudge(self, fraction: float) -> None:
        """Move the value by ``fraction`` of the soft range (clamped to it)."""
        if self.locked and not self.slider.isEnabled():
            return
        span = self.hi - self.lo
        v = self.value() + fraction * span
        if self.is_int:
            v = self.value() + (1 if fraction > 0 else -1) * max(1, round(abs(fraction) * span))
        v = min(max(v, self.lo), self.hi)
        self.set_value(v)
        self._remember(v)
        self.valueChanged.emit(float(v))

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802 — Qt override
        if ev.type() == QEvent.Type.Wheel and obj in (self.slider, self.spin):
            if obj is self.spin and not self.spin.hasFocus():
                return False  # let the scroll area scroll; an unfocused spin box does not eat the wheel
            notches = ev.angleDelta().y() / 120.0
            if notches:
                self.nudge(notches * NUDGE * modifier_scale(ev.modifiers()))
            return True
        if ev.type() == QEvent.Type.KeyPress and obj is self.slider:
            key = ev.key()
            step = {Qt.Key.Key_Left: -1, Qt.Key.Key_Down: -1, Qt.Key.Key_Right: 1, Qt.Key.Key_Up: 1,
                    Qt.Key.Key_PageDown: -10, Qt.Key.Key_PageUp: 10}.get(key)
            if step is not None:
                self.nudge(step * NUDGE * modifier_scale(ev.modifiers()))
                return True
        return super().eventFilter(obj, ev)

    def _remember(self, v: float) -> None:
        v = float(v)
        if self.history and abs(self.history[-1] - v) <= 1e-12:
            return
        self.history.append(v)
        self.valueCommitted.emit(v)

    def seed_history(self, values) -> None:
        """Pre-fill the history (e.g. from a saved project) without emitting."""
        self.history.clear()
        self.history.extend(float(v) for v in values)

    def _on_release(self) -> None:
        self._remember(self.value())
        self.interactionEnded.emit()

    # ── mapping ────────────────────────────────────────────────────────────────
    def _to_slider(self, v: float) -> int:
        if self.log_scale:
            t = (math.log(max(v, 1e-300)) - math.log(self.lo)) / (math.log(self.hi) - math.log(self.lo))
        else:
            t = (v - self.lo) / (self.hi - self.lo)
        return int(round(min(max(t, 0.0), 1.0) * SLIDER_STEPS))

    def _from_slider(self, s: int) -> float:
        t = s / SLIDER_STEPS
        if self.log_scale:
            v = math.exp(math.log(self.lo) + t * (math.log(self.hi) - math.log(self.lo)))
        else:
            v = self.lo + t * (self.hi - self.lo)
        return float(round(v)) if self.is_int else v

    # ── API ─────────────────────────────────────────────────────────────────────
    def value(self) -> float:
        return float(self.spin.value())

    def set_value(self, v: float) -> None:
        self._updating = True
        try:
            if v < self.lo or v > self.hi:  # grow the soft range to include the value
                span = self.hi - self.lo
                self.lo, self.hi = min(self.lo, v - 0.1 * span), max(self.hi, v + 0.1 * span)
            self.spin.setValue(v)
            self.slider.setValue(self._to_slider(v))
        finally:
            self._updating = False

    def set_range(self, lo: float, hi: float) -> None:
        self.lo, self.hi = float(lo), float(hi)
        if self.hi <= self.lo:
            self.hi = self.lo + 1e-6
        self.log_scale = self.log_scale and self.lo > 0
        self._apply_steps()
        self.set_value(min(max(self.value(), self.lo), self.hi))

    # ── slots ───────────────────────────────────────────────────────────────────
    def _on_slider(self, s: int) -> None:
        if self._updating:
            return
        v = self._from_slider(s)
        self._updating = True
        self.spin.setValue(v)
        self._updating = False
        self.valueChanged.emit(v)

    def _on_spin(self, v: float) -> None:
        if self._updating:
            return
        if v < self.lo or v > self.hi:
            self.set_value(v)
        else:
            self._updating = True
            self.slider.setValue(self._to_slider(v))
            self._updating = False
        self._remember(v)
        self.valueChanged.emit(float(v))

    def _on_lock(self, on: bool) -> None:
        self.locked = on
        self.slider.setEnabled(not on)
        self.lockToggled.emit(on)

    def _menu(self, pos) -> None:
        m = QMenu(self)
        a_reset = QAction(f"Reset to {self.default:g}", m)
        a_reset.triggered.connect(self._reset)
        a_range = QAction(tr("Edit slider range…"), m)
        a_range.triggered.connect(self._edit_range)
        a_wide = QAction(tr("Widen range ×2"), m)
        a_wide.triggered.connect(lambda: self._scale_range(2.0))
        a_narrow = QAction(tr("Narrow range ×½ around value"), m)
        a_narrow.triggered.connect(lambda: self._scale_range(0.5))
        m.addActions([a_reset, a_range, a_wide, a_narrow])
        m.addSeparator()
        a_copy = QAction(tr("Copy value"), m)
        a_copy.triggered.connect(lambda: QGuiApplication.clipboard().setText(f"{self.value():.10g}"))
        a_paste = QAction(tr("Paste value"), m)
        a_paste.triggered.connect(self._paste)
        m.addActions([a_copy, a_paste])
        if self.history:
            sub = m.addMenu(tr("Recent values"))
            for v in reversed(list(self.history)):
                act = QAction(f"{v:.6g}", sub)
                act.triggered.connect(lambda _=False, val=v: self._apply_history(val))
                sub.addAction(act)
        if self.lock_btn.isVisible():
            a_lock = QAction(tr("Locked"), m)
            a_lock.setCheckable(True)
            a_lock.setChecked(self.locked)
            a_lock.toggled.connect(self.lock_btn.setChecked)
            m.addAction(a_lock)
        m.exec(self.mapToGlobal(pos))

    def _reset(self) -> None:
        self.set_value(self.default)
        self._remember(self.default)
        self.valueChanged.emit(self.default)
        self.resetRequested.emit()

    def _apply_history(self, v: float) -> None:
        self.set_value(v)
        self.valueChanged.emit(float(v))

    def _paste(self) -> None:
        try:
            v = float(QGuiApplication.clipboard().text().strip().replace(",", "."))
        except ValueError:
            return
        self.set_value(v)
        self._remember(v)
        self.valueChanged.emit(float(v))

    def _edit_range(self) -> None:
        d = RangeDialog(self.lo, self.hi, self)
        if d.exec() == QDialog.DialogCode.Accepted:
            self.set_range(d.lo.value(), d.hi.value())

    def _scale_range(self, f: float) -> None:
        c = self.value()
        half = (self.hi - self.lo) * 0.5 * f
        self.set_range(c - half, c + half)
