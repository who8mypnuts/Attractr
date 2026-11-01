"""Search panel: random parameter search filtered by chaos, with thumbnails."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from attractr.core.analysis.search import SearchHit, search
from attractr.core.jobs.cancel import Cancelled, CancelToken
from attractr.core.render.develop.developer import develop
from attractr.core.render.engines import selector
from attractr.core.render.settings import RenderSettings
from attractr.gui.controllers.develop_controller import to_qimage
from attractr.gui.state.document import Document

THUMB = 112


class SearchThread(QThread):
    hit = Signal(object, object)  # SearchHit, QImage
    progress = Signal(int, int)
    done = Signal()

    def __init__(self, settings: RenderSettings, spec, count: int, radius: float, locked: dict, parent=None) -> None:
        super().__init__(parent)
        self.settings, self.spec, self.count, self.radius, self.locked = settings, spec, count, radius, locked
        self.cancel = CancelToken()

    def run(self) -> None:
        try:
            around = self.settings.param_dict if self.radius < 1.0 else None
            for h in search(self.spec, count=self.count, dt=self.settings.quality.dt, locked=self.locked, around=around,
                            radius=self.radius, cancel=self.cancel, on_progress=lambda i, f: self.progress.emit(i, f)):
                q = replace(self.settings.quality, width=THUMB, height=THUMB, points_per_pixel=5.0, supersample=1, splat_radius=0)
                s = replace(self.settings, quality=q).with_param_dict(h.params)
                try:
                    engine = selector.select("auto", "preview")
                    res = engine.accumulate(s, self.spec, cancel=self.cancel)
                except Cancelled:
                    raise
                except Exception:  # noqa: BLE001
                    res = selector.get_engine("cpu").accumulate(s, self.spec, cancel=self.cancel)
                if res.stats.coverage < 0.01:
                    continue
                self.hit.emit(h, to_qimage(develop(res, s.look)))
        except Cancelled:
            pass
        finally:
            self.done.emit()


class SearchPanel(QWidget):
    def __init__(self, doc: Document, parent=None) -> None:
        super().__init__(parent)
        self.doc = doc
        self.thread: SearchThread | None = None
        self._hits: dict[int, SearchHit] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        row = QHBoxLayout()
        row.addWidget(QLabel("Results"))
        self.count = QSpinBox()
        self.count.setRange(1, 64)
        self.count.setValue(12)
        row.addWidget(self.count)
        row.addWidget(QLabel("Radius"))
        self.radius = QDoubleSpinBox()
        self.radius.setRange(0.01, 1.0)
        self.radius.setSingleStep(0.05)
        self.radius.setValue(1.0)
        self.radius.setToolTip("1 = anywhere in the parameter ranges; smaller = mutate around the current values")
        row.addWidget(self.radius)
        self.use_locks = QCheckBox("Keep locked")
        self.use_locks.setChecked(True)
        row.addWidget(self.use_locks)
        lay.addLayout(row)
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setIconSize(QSize(THUMB, THUMB))
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setSpacing(6)
        lay.addWidget(self.list, 1)
        btns = QHBoxLayout()
        self.btn_go = QPushButton("🔍 Search")
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setEnabled(False)
        self.btn_clear = QPushButton("Clear")
        self.status = QLabel("")
        btns.addWidget(self.btn_go)
        btns.addWidget(self.btn_stop)
        btns.addWidget(self.btn_clear)
        btns.addWidget(self.status, 1)
        lay.addLayout(btns)
        self.btn_go.clicked.connect(self.start)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_clear.clicked.connect(self.list.clear)
        self.list.itemClicked.connect(self._apply)
        self.list.itemActivated.connect(self._apply)
        self.locked_provider = lambda: set()

    def start(self) -> None:
        if self.thread is not None:
            return
        locked = {}
        if self.use_locks.isChecked():
            vals = self.doc.settings.param_dict
            locked = {n: vals[n] for n in self.locked_provider() if n in vals}
        self.thread = SearchThread(self.doc.settings, self.doc.spec, self.count.value(), self.radius.value(), locked, self)
        self.thread.hit.connect(self._on_hit)
        self.thread.progress.connect(lambda i, f: self.status.setText(f"tried {i} · found {f}"))
        self.thread.done.connect(self._on_done)
        self.btn_go.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.thread.start()

    def stop(self) -> None:
        if self.thread is not None:
            self.thread.cancel.cancel()

    def _on_done(self) -> None:
        if self.thread is not None:
            self.thread.wait(2000)
            self.thread.deleteLater()
            self.thread = None
        self.btn_go.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.status.setText(self.status.text() + " · done")

    def _on_hit(self, hit: SearchHit, img) -> None:
        item = QListWidgetItem(QIcon(QPixmap.fromImage(img)), f"λ₁ {hit.lyapunov:.3f}")
        item.setToolTip("\n".join(f"{k} = {v:.4g}" for k, v in hit.params.items()))
        item.setSizeHint(QSize(THUMB + 16, THUMB + 28))
        key = id(hit)
        item.setData(Qt.ItemDataRole.UserRole, key)
        self._hits[key] = hit
        self.list.addItem(item)

    def _apply(self, item: QListWidgetItem) -> None:
        hit = self._hits.get(item.data(Qt.ItemDataRole.UserRole))
        if hit is not None:
            self.doc.set_params(hit.params, "Search result")

    def shutdown(self) -> None:
        self.stop()
        if self.thread is not None:
            self.thread.wait(3000)
