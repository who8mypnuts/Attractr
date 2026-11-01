"""Gallery panel: your rendered images — open, re-open their settings, reveal in folder."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QImageReader, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget

from attractr.core.io.metadata import read_settings
from attractr.core.project.gallery import GalleryEntry, gallery
from attractr.gui.state.document import TAGS_ALL, Document

THUMB = 128


class GalleryPanel(QWidget):
    def __init__(self, doc: Document, parent=None) -> None:
        super().__init__(parent)
        self.doc = doc
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setIconSize(QSize(THUMB, THUMB))
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setSpacing(6)
        lay.addWidget(self.list, 1)
        btns = QHBoxLayout()
        self.btn_open = QPushButton("Open image")
        self.btn_settings = QPushButton("Re-open settings")
        self.btn_report = QPushButton("Open report")
        self.btn_folder = QPushButton("Show folder")
        self.btn_remove = QPushButton("Remove")
        for b in (self.btn_open, self.btn_settings, self.btn_report, self.btn_folder, self.btn_remove):
            btns.addWidget(b)
        lay.addLayout(btns)
        self.btn_open.clicked.connect(lambda: self._open(lambda e: QUrl.fromLocalFile(e.path)))
        self.btn_report.clicked.connect(lambda: self._open(lambda e: QUrl.fromLocalFile(e.report) if e.report else None))
        self.btn_folder.clicked.connect(lambda: self._open(lambda e: QUrl.fromLocalFile(str(Path(e.path).parent))))
        self.btn_settings.clicked.connect(self._reopen)
        self.btn_remove.clicked.connect(self._remove)
        self.list.itemActivated.connect(lambda _: self._open(lambda e: QUrl.fromLocalFile(e.path)))
        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        for e in gallery.entries():
            reader = QImageReader(e.path)
            reader.setScaledSize(reader.size().scaled(THUMB, THUMB, Qt.AspectRatioMode.KeepAspectRatio))
            img = reader.read()
            item = QListWidgetItem(QIcon(QPixmap.fromImage(img)) if not img.isNull() else QIcon(), Path(e.path).name)
            item.setToolTip(f"{e.attractor} · {e.width}×{e.height}\n{e.path}")
            item.setData(Qt.ItemDataRole.UserRole, e.path)
            item.setSizeHint(QSize(THUMB + 16, THUMB + 30))
            self.list.addItem(item)

    def _current(self) -> GalleryEntry | None:
        item = self.list.currentItem()
        if item is None:
            return None
        path = item.data(Qt.ItemDataRole.UserRole)
        return next((e for e in gallery.entries() if e.path == path), None)

    def _open(self, url_fn) -> None:
        e = self._current()
        if e is None:
            return
        url = url_fn(e)
        if url is not None:
            QDesktopServices.openUrl(url)

    def _reopen(self) -> None:
        e = self._current()
        if e is None:
            return
        s = read_settings(e.path)
        if s is None:
            QMessageBox.information(self, "Gallery", "No settings embedded in that image.")
            return
        self.doc.apply(s, "Re-open render settings", TAGS_ALL)

    def _remove(self) -> None:
        e = self._current()
        if e is None:
            return
        r = QMessageBox.question(self, "Remove", "Remove from the gallery only (Yes) or also delete the file (Discard)?",
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if r == QMessageBox.StandardButton.Cancel:
            return
        gallery.remove(e, delete_file=(r == QMessageBox.StandardButton.Discard))
        self.refresh()
