"""Attractor browser: thumbnails grouped by family with a search box."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from attractr.core.attractors.registry import registry
from attractr.core.attractors.spec import AttractorSpec
from attractr.core.render.pipeline import default_settings
from attractr.gui.controllers.worker_client import WorkerClient as ThumbnailWorker
from attractr.gui.state.document import Document

THUMB = 96


class AttractorBrowser(QWidget):
    attractorPicked = Signal(object)

    def __init__(self, doc: Document, thumbs: ThumbnailWorker, parent=None) -> None:
        super().__init__(parent)
        self.doc = doc
        self.thumbs = thumbs
        self._items: dict[str, QListWidgetItem] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search attractors…")
        self.search.setClearButtonEnabled(True)
        self.family = QComboBox()
        self.family.addItem("All families", "")
        top.addWidget(self.search, 1)
        top.addWidget(self.family)
        lay.addLayout(top)
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setIconSize(QSize(THUMB, THUMB))
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setSpacing(6)
        self.list.setWordWrap(True)
        self.list.setUniformItemSizes(True)
        lay.addWidget(self.list, 1)
        self.search.textChanged.connect(self._filter)
        self.family.currentIndexChanged.connect(self._filter)
        self.list.itemClicked.connect(self._on_click)
        self.thumbs.ready.connect(self._on_thumb)
        doc.attractorChanged.connect(self._highlight)
        self.populate()

    def populate(self) -> None:
        self.list.clear()
        self._items.clear()
        fams = registry.families()
        for fam in fams:
            if self.family.findData(fam) < 0:
                self.family.addItem(fam, fam)
        placeholder = QPixmap(THUMB, THUMB)
        placeholder.fill(Qt.GlobalColor.transparent)
        for spec in registry.all():
            item = QListWidgetItem(QIcon(placeholder), spec.name)
            item.setData(Qt.ItemDataRole.UserRole, spec.id)
            item.setData(Qt.ItemDataRole.UserRole + 1, spec.family)
            item.setToolTip(f"<b>{spec.name}</b> — {spec.kind}, {spec.dims}-D<br>{spec.description}")
            item.setSizeHint(QSize(THUMB + 16, THUMB + 34))
            self.list.addItem(item)
            self._items[spec.id] = item
            self.thumbs.request(self._key(spec), default_settings(spec))
        self._highlight(self.doc.spec)

    @staticmethod
    def _key(spec: AttractorSpec) -> str:
        return f"{spec.id}_{spec.content_hash}"

    def _on_thumb(self, key: str, img) -> None:
        sid = key.rsplit("_", 1)[0]
        item = self._items.get(sid)
        if item is not None:
            item.setIcon(QIcon(QPixmap.fromImage(img)))

    def _filter(self) -> None:
        text = self.search.text().lower().strip()
        fam = self.family.currentData()
        for sid, item in self._items.items():
            spec = registry.get(sid)
            ok = (not text or text in spec.name.lower() or text in sid or any(text in t for t in spec.tags)) and (not fam or spec.family == fam)
            item.setHidden(not ok)

    def _on_click(self, item: QListWidgetItem) -> None:
        sid = item.data(Qt.ItemDataRole.UserRole)
        spec = registry.get(sid)
        if spec.id != self.doc.spec.id or self.doc.settings.source:
            self.doc.set_attractor(spec)
        self.attractorPicked.emit(spec)

    def _highlight(self, spec: AttractorSpec) -> None:
        item = self._items.get(spec.id)
        if item is not None:
            self.list.setCurrentItem(item)
