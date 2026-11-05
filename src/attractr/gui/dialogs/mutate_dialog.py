"""Mutate grid: a 3×3 / 4×4 sheet of random perturbations of the current parameters."""

from __future__ import annotations

import random
from dataclasses import replace

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from attractr.core.analysis.search import random_params
from attractr.core.jobs.cancel import Cancelled, CancelToken
from attractr.core.render.develop.developer import develop
from attractr.core.render.engines import selector
from attractr.gui.controllers.develop_controller import to_qimage
from attractr.gui.state.document import Document
from attractr.i18n import tr

THUMB = 140


class _MutateThread(QThread):
    ready = Signal(int, object, object)  # index, params, QImage

    def __init__(self, settings, spec, n: int, radius: float, locked: set[str], seed: int, parent=None) -> None:
        super().__init__(parent)
        self.settings, self.spec, self.n, self.radius, self.locked, self.seed = settings, spec, n, radius, locked, seed
        self.cancel = CancelToken()

    def run(self) -> None:
        rng = random.Random(self.seed)
        base = self.settings.param_dict
        locked = {k: base[k] for k in self.locked if k in base}
        q = replace(self.settings.quality, width=THUMB, height=THUMB, points_per_pixel=5.0, supersample=1, splat_radius=0)
        for i in range(self.n):
            try:
                self.cancel.check()
                params = base if i == 0 else random_params(self.spec, rng, locked, base, self.radius)
                s = replace(self.settings, quality=q).with_param_dict(params)
                try:
                    res = selector.select("auto", "preview", self.spec).accumulate(s, self.spec, cancel=self.cancel)
                except Cancelled:
                    return
                except Exception:  # noqa: BLE001
                    res = selector.get_engine("cpu").accumulate(s, self.spec, cancel=self.cancel)
                self.ready.emit(i, params, to_qimage(develop(res, s.look)))
            except Cancelled:
                return


class MutateDialog(QDialog):
    def __init__(self, doc: Document, locked_provider, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Mutate — pick a variation"))
        self.setModal(False)
        self.doc = doc
        self.locked_provider = locked_provider
        self.thread: _MutateThread | None = None
        self._params: dict[int, dict] = {}
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Radius")))
        self.radius = QSlider(Qt.Orientation.Horizontal)
        self.radius.setRange(1, 100)
        self.radius.setValue(15)
        self.radius_label = QLabel("15 %")
        row.addWidget(self.radius, 1)
        row.addWidget(self.radius_label)
        self.grid = QComboBox()
        self.grid.addItems(["3 × 3", "4 × 4"])
        row.addWidget(self.grid)
        self.btn_again = QPushButton(tr("↻ Again"))
        row.addWidget(self.btn_again)
        lay.addLayout(row)
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setIconSize(QSize(THUMB, THUMB))
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setSpacing(6)
        lay.addWidget(self.list, 1)
        hint = QLabel(tr("The first tile is the current state. Click a tile to adopt its parameters, then mutate again to zoom in on a look."))
        hint.setStyleSheet("color:#888")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.radius.valueChanged.connect(lambda v: self.radius_label.setText(f"{v} %"))
        self.btn_again.clicked.connect(self.regenerate)
        self.grid.currentIndexChanged.connect(lambda _: self.regenerate())
        self.list.itemClicked.connect(self._adopt)
        self.resize(3 * (THUMB + 24) + 60, 3 * (THUMB + 40) + 120)
        self.regenerate()

    def regenerate(self) -> None:
        self._stop()
        self.list.clear()
        self._params.clear()
        n = 9 if self.grid.currentIndex() == 0 else 16
        placeholder = QPixmap(THUMB, THUMB)
        placeholder.fill(Qt.GlobalColor.transparent)
        for i in range(n):
            item = QListWidgetItem(QIcon(placeholder), "current" if i == 0 else f"#{i}")
            item.setSizeHint(QSize(THUMB + 16, THUMB + 28))
            self.list.addItem(item)
        self.thread = _MutateThread(self.doc.settings, self.doc.spec, n, self.radius.value() / 100.0, set(self.locked_provider()), random.randrange(1 << 30), self)
        self.thread.ready.connect(self._on_ready)
        self.thread.start()

    def _on_ready(self, i: int, params: dict, img) -> None:
        item = self.list.item(i)
        if item is not None:
            item.setIcon(QIcon(QPixmap.fromImage(img)))
            item.setToolTip("\n".join(f"{k} = {v:.4g}" for k, v in params.items()))
        self._params[i] = params

    def _adopt(self, item: QListWidgetItem) -> None:
        i = self.list.row(item)
        params = self._params.get(i)
        if params is not None and i != 0:
            self.doc.set_params(params, "Mutate")
            self.regenerate()

    def _stop(self) -> None:
        if self.thread is not None:
            self.thread.cancel.cancel()
            self.thread.wait(3000)
            self.thread = None

    def closeEvent(self, e) -> None:  # noqa: N802
        self._stop()
        super().closeEvent(e)
