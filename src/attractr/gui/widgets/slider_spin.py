"""SliderSpin: label + slider + spin box with an editable soft range, lock and reset."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
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

SLIDER_STEPS = 20000


class RangeDialog(QDialog):
    def __init__(self, lo: float, hi: float, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Slider range")
        form = QFormLayout(self)
        self.lo = QDoubleSpinBox()
        self.hi = QDoubleSpinBox()
        for sb, v in ((self.lo, lo), (self.hi, hi)):
            sb.setDecimals(6)
            sb.setRange(-1e9, 1e9)
            sb.setValue(v)
        form.addRow("Minimum", self.lo)
        form.addRow("Maximum", self.hi)
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
        self.lock_btn.setToolTip("Lock (excluded from randomize)")
        self.lock_btn.setVisible(show_lock)
        self.lock_btn.toggled.connect(self._on_lock)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(self.label)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.spin)
        lay.addWidget(self.lock_btn)

        self.set_value(value)
        self.slider.valueChanged.connect(self._on_slider)
        self.slider.sliderPressed.connect(self.interactionStarted)
        self.slider.sliderReleased.connect(self.interactionEnded)
        self.spin.valueChanged.connect(self._on_spin)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

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
        self.spin.setSingleStep(1 if self.is_int else (self.hi - self.lo) / 200.0)
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
        self.valueChanged.emit(float(v))

    def _on_lock(self, on: bool) -> None:
        self.locked = on
        self.slider.setEnabled(not on)
        self.lockToggled.emit(on)

    def _menu(self, pos) -> None:
        m = QMenu(self)
        a_reset = QAction(f"Reset to {self.default:g}", m)
        a_reset.triggered.connect(self._reset)
        a_range = QAction("Edit slider range…", m)
        a_range.triggered.connect(self._edit_range)
        a_wide = QAction("Widen range ×2", m)
        a_wide.triggered.connect(lambda: self._scale_range(2.0))
        a_narrow = QAction("Narrow range ×½ around value", m)
        a_narrow.triggered.connect(lambda: self._scale_range(0.5))
        m.addActions([a_reset, a_range, a_wide, a_narrow])
        if self.lock_btn.isVisible():
            a_lock = QAction("Locked", m)
            a_lock.setCheckable(True)
            a_lock.setChecked(self.locked)
            a_lock.toggled.connect(self.lock_btn.setChecked)
            m.addAction(a_lock)
        m.exec(self.mapToGlobal(pos))

    def _reset(self) -> None:
        self.set_value(self.default)
        self.valueChanged.emit(self.default)
        self.resetRequested.emit()

    def _edit_range(self) -> None:
        d = RangeDialog(self.lo, self.hi, self)
        if d.exec() == QDialog.DialogCode.Accepted:
            self.set_range(d.lo.value(), d.hi.value())

    def _scale_range(self, f: float) -> None:
        c = self.value()
        half = (self.hi - self.lo) * 0.5 * f
        self.set_range(c - half, c + half)
