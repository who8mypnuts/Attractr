"""Gradient editor: interactive stop bar + colour picker + library, applied live."""

from __future__ import annotations

import random
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from attractr.core.color.generate import SCHEMES, random_gradient
from attractr.core.color.gradient import Gradient, Stop
from attractr.core.color.interpolation import SPACES
from attractr.core.color.palettes import palettes
from attractr.gui.widgets.gradient_bar import gradient_image

HANDLE_H = 14


class StopBar(QWidget):
    """Gradient preview with draggable stop handles underneath."""

    gradientChanged = Signal(object)  # Gradient (continuous)
    selectionChanged = Signal(int)
    editingFinished = Signal()

    def __init__(self, gradient: Gradient, parent=None) -> None:
        super().__init__(parent)
        self.gradient = gradient
        self.selected = 0
        self._drag = False
        self.setMinimumHeight(64)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def bar_rect(self) -> QRectF:
        return QRectF(8, 4, self.width() - 16, self.height() - HANDLE_H - 12)

    def set_gradient(self, g: Gradient, keep_selection: bool = True) -> None:
        self.gradient = g
        if not keep_selection or self.selected >= len(g.stops):
            self.selected = min(self.selected, len(g.stops) - 1)
        self.update()

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.bar_rect()
        # checkerboard for alpha
        p.fillRect(r, QColor(40, 40, 48))
        for x in range(int(r.left()), int(r.right()), 8):
            for y in range(int(r.top()), int(r.bottom()), 8):
                if ((x // 8) + (y // 8)) % 2 == 0:
                    p.fillRect(QRectF(x, y, 8, 8), QColor(70, 70, 80))
        img = gradient_image(self.gradient, max(int(r.width()), 2), 1)
        p.drawImage(r, img)
        p.setPen(QColor(90, 90, 110))
        p.drawRect(r)
        for i, s in enumerate(self.gradient.stops):
            x = r.left() + s.pos * r.width()
            y = r.bottom() + 2
            tri = QPolygonF([QPointF(x, y), QPointF(x - 6, y + HANDLE_H - 2), QPointF(x + 6, y + HANDLE_H - 2)])
            p.setBrush(QColor.fromRgbF(s.r, s.g, s.b))
            p.setPen(QPen(QColor(255, 255, 255) if i == self.selected else QColor(20, 20, 28), 1.5))
            p.drawPolygon(tri)
        p.end()

    def _stop_at(self, pos: QPointF) -> int:
        r = self.bar_rect()
        best, bd = -1, 9.0
        for i, s in enumerate(self.gradient.stops):
            x = r.left() + s.pos * r.width()
            d = abs(pos.x() - x)
            if d < bd and pos.y() >= r.bottom() - 4:
                best, bd = i, d
        return best

    def mousePressEvent(self, e) -> None:  # noqa: N802
        i = self._stop_at(e.position())
        if i >= 0:
            self.selected = i
            self._drag = True
            self.selectionChanged.emit(i)
            self.update()
        self.setFocus()

    def mouseDoubleClickEvent(self, e) -> None:  # noqa: N802
        r = self.bar_rect()
        if r.contains(e.position()) or e.position().y() < r.bottom():
            t = min(max((e.position().x() - r.left()) / r.width(), 0.0), 1.0)
            c = self.gradient.sample_at(t)
            g = self.gradient.add_stop(Stop(t, c.r, c.g, c.b, c.a))
            self.gradient = g
            self.selected = [s.pos for s in g.stops].index(t) if t in [s.pos for s in g.stops] else 0
            self.gradientChanged.emit(g)
            self.selectionChanged.emit(self.selected)
            self.editingFinished.emit()
            self.update()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if not self._drag:
            return
        r = self.bar_rect()
        t = min(max((e.position().x() - r.left()) / r.width(), 0.0), 1.0)
        stops = list(self.gradient.stops)
        s = stops[self.selected]
        stops[self.selected] = replace(s, pos=t)
        g = Gradient(tuple(stops), self.gradient.space, self.gradient.cyclic, self.gradient.name)
        # sorting may move the index
        self.selected = [st.pos for st in g.stops].index(t)
        self.gradient = g
        self.gradientChanged.emit(g)
        self.update()

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if self._drag:
            self._drag = False
            self.editingFinished.emit()

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and len(self.gradient.stops) > 2:
            self.gradient = self.gradient.remove_stop(self.selected)
            self.selected = min(self.selected, len(self.gradient.stops) - 1)
            self.gradientChanged.emit(self.gradient)
            self.selectionChanged.emit(self.selected)
            self.editingFinished.emit()
            self.update()
        else:
            super().keyPressEvent(e)


class GradientEditor(QDialog):
    gradientChanged = Signal(object)  # live
    editingFinished = Signal()

    def __init__(self, gradient: Gradient, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gradient editor")
        self.setModal(False)
        self._updating = False
        lay = QHBoxLayout(self)

        # ── left: editor ───────────────────────────────────────────────────────
        left = QVBoxLayout()
        self.bar = StopBar(gradient)
        left.addWidget(self.bar)
        row = QHBoxLayout()
        self.pos = QDoubleSpinBox()
        self.pos.setRange(0.0, 1.0)
        self.pos.setDecimals(4)
        self.pos.setSingleStep(0.01)
        self.alpha = QDoubleSpinBox()
        self.alpha.setRange(0.0, 1.0)
        self.alpha.setDecimals(3)
        self.alpha.setSingleStep(0.05)
        self.btn_add = QPushButton("+ stop")
        self.btn_remove = QPushButton("− stop")
        row.addWidget(QLabel("Position"))
        row.addWidget(self.pos)
        row.addWidget(QLabel("Alpha"))
        row.addWidget(self.alpha)
        row.addStretch(1)
        row.addWidget(self.btn_add)
        row.addWidget(self.btn_remove)
        left.addLayout(row)
        self.picker = QColorDialog()
        self.picker.setOptions(QColorDialog.ColorDialogOption.NoButtons | QColorDialog.ColorDialogOption.DontUseNativeDialog)
        self.picker.setWindowFlags(Qt.WindowType.Widget)
        left.addWidget(self.picker)
        form = QFormLayout()
        self.space = QComboBox()
        self.space.addItems(list(SPACES))
        self.space.setToolTip("Interpolation colour space between stops")
        self.cyclic = QCheckBox("Cyclic (wraps for Plasma / phase)")
        form.addRow("Interpolate in", self.space)
        form.addRow(self.cyclic)
        left.addLayout(form)
        tools = QHBoxLayout()
        self.btn_reverse = QPushButton("Reverse")
        self.btn_distribute = QPushButton("Distribute")
        self.scheme = QComboBox()
        self.scheme.addItems(list(SCHEMES))
        self.btn_random = QPushButton("🎲 Random")
        for w in (self.btn_reverse, self.btn_distribute, self.scheme, self.btn_random):
            tools.addWidget(w)
        left.addLayout(tools)
        lay.addLayout(left, 3)

        # ── right: library ─────────────────────────────────────────────────────
        right = QVBoxLayout()
        right.addWidget(QLabel("Library"))
        self.library = QListWidget()
        self.library.setIconSize(self.library.iconSize())
        right.addWidget(self.library, 1)
        lb = QHBoxLayout()
        self.btn_save = QPushButton("Save as…")
        self.btn_import = QPushButton("Import…")
        self.btn_export = QPushButton("Export…")
        for b in (self.btn_save, self.btn_import, self.btn_export):
            lb.addWidget(b)
        right.addLayout(lb)
        self.btn_close = QPushButton("Close")
        right.addWidget(self.btn_close)
        lay.addLayout(right, 2)

        # ── wiring ─────────────────────────────────────────────────────────────
        self.bar.gradientChanged.connect(self._from_bar)
        self.bar.selectionChanged.connect(self._sync_selection)
        self.bar.editingFinished.connect(self.editingFinished)
        self.pos.valueChanged.connect(self._on_pos)
        self.alpha.valueChanged.connect(self._on_alpha)
        self.picker.currentColorChanged.connect(self._on_color)
        self.space.currentTextChanged.connect(lambda t: self._emit(replace(self.bar.gradient, space=t), final=True))
        self.cyclic.toggled.connect(lambda b: self._emit(replace(self.bar.gradient, cyclic=b), final=True))
        self.btn_add.clicked.connect(self._add_stop)
        self.btn_remove.clicked.connect(self._remove_stop)
        self.btn_reverse.clicked.connect(lambda: self._emit(self.bar.gradient.reversed(), final=True))
        self.btn_distribute.clicked.connect(lambda: self._emit(self.bar.gradient.distributed(), final=True))
        self.btn_random.clicked.connect(self._random)
        self.library.itemActivated.connect(self._load_from_library)
        self.library.itemClicked.connect(self._load_from_library)
        self.btn_save.clicked.connect(self._save)
        self.btn_import.clicked.connect(self._import)
        self.btn_export.clicked.connect(self._export)
        self.btn_close.clicked.connect(self.close)
        self._fill_library()
        self.set_gradient(gradient)
        self.resize(860, 560)

    # ── state ──────────────────────────────────────────────────────────────────
    def set_gradient(self, g: Gradient) -> None:
        self._updating = True
        self.bar.set_gradient(g)
        self.space.setCurrentText(g.space)
        self.cyclic.setChecked(g.cyclic)
        self._updating = False
        self._sync_selection(self.bar.selected)

    def _sync_selection(self, i: int) -> None:
        g = self.bar.gradient
        if not g.stops:
            return
        s = g.stops[min(i, len(g.stops) - 1)]
        self._updating = True
        self.pos.setValue(s.pos)
        self.alpha.setValue(s.a)
        self.picker.setCurrentColor(QColor.fromRgbF(s.r, s.g, s.b))
        self._updating = False

    def _emit(self, g: Gradient, final: bool = False) -> None:
        self.bar.set_gradient(g)
        self.gradientChanged.emit(g)
        if final:
            self.editingFinished.emit()

    def _from_bar(self, g: Gradient) -> None:
        self._sync_selection(self.bar.selected)
        self.gradientChanged.emit(g)

    def _edit_selected(self, **kw) -> None:
        if self._updating:
            return
        g = self.bar.gradient
        i = self.bar.selected
        s = replace(g.stops[i], **kw)
        g2 = g.with_stop(i, s)
        if "pos" in kw:
            self.bar.selected = [st.pos for st in g2.stops].index(s.pos)
        self._emit(g2)

    def _on_pos(self, v: float) -> None:
        self._edit_selected(pos=v)

    def _on_alpha(self, v: float) -> None:
        self._edit_selected(a=v)

    def _on_color(self, c: QColor) -> None:
        self._edit_selected(r=c.redF(), g=c.greenF(), b=c.blueF())

    def _add_stop(self) -> None:
        g = self.bar.gradient
        i = self.bar.selected
        nxt = g.stops[i + 1].pos if i + 1 < len(g.stops) else 1.0
        t = (g.stops[i].pos + nxt) / 2 if i + 1 < len(g.stops) else max(0.0, g.stops[i].pos - 0.1)
        c = g.sample_at(t)
        g2 = g.add_stop(Stop(t, c.r, c.g, c.b, c.a))
        self.bar.selected = [s.pos for s in g2.stops].index(t)
        self._emit(g2, final=True)
        self._sync_selection(self.bar.selected)

    def _remove_stop(self) -> None:
        g = self.bar.gradient
        if len(g.stops) > 2:
            g2 = g.remove_stop(self.bar.selected)
            self.bar.selected = min(self.bar.selected, len(g2.stops) - 1)
            self._emit(g2, final=True)
            self._sync_selection(self.bar.selected)

    def _random(self) -> None:
        g = random_gradient(self.scheme.currentText(), rng=random.Random())
        self.set_gradient(g)
        self._emit(g, final=True)

    # ── library ────────────────────────────────────────────────────────────────
    def _fill_library(self) -> None:
        from PySide6.QtGui import QIcon, QPixmap

        self.library.clear()
        for pid, g in palettes.items():
            img = gradient_image(g, 96, 14)
            item = QListWidgetItem(QIcon(QPixmap.fromImage(img)), g.name)
            item.setData(Qt.ItemDataRole.UserRole, pid)
            meta = palettes.meta(pid)
            item.setToolTip(f"{g.name} — {meta.get('desc', '')} ({meta.get('source', '')})")
            self.library.addItem(item)

    def _load_from_library(self, item: QListWidgetItem) -> None:
        g = palettes.get(item.data(Qt.ItemDataRole.UserRole))
        self.set_gradient(g)
        self._emit(g, final=True)

    def _save(self) -> None:
        name, ok = QInputDialog.getText(self, "Save palette", "Name:", text=self.bar.gradient.name)
        if not ok or not name.strip():
            return
        pid = name.strip().lower().replace(" ", "_")
        g = replace(self.bar.gradient, name=name.strip())
        palettes.save_user(pid, g)
        self._fill_library()
        self._emit(g, final=True)

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import gradient", "", "Gradients (*.ggr *.json)")
        if not path:
            return
        try:
            if path.lower().endswith(".ggr"):
                from attractr.core.color.ggr_io import read_ggr

                g = read_ggr(path)
            else:
                import json

                g = Gradient.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Import gradient", str(exc))
            return
        self.set_gradient(g)
        self._emit(g, final=True)

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export gradient", f"{self.bar.gradient.name}.ggr", "GIMP gradient (*.ggr);;JSON (*.json)")
        if not path:
            return
        if path.lower().endswith(".ggr"):
            from attractr.core.color.ggr_io import write_ggr

            write_ggr(self.bar.gradient, path)
        else:
            import json

            Path(path).write_text(json.dumps(self.bar.gradient.to_dict(), indent=1), encoding="utf-8")

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(e)
