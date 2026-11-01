"""Presets panel: curated + user presets with thumbnails, daily attractor, share codes."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from attractr.core.project.codes import settings_from_code, settings_to_code
from attractr.core.project.presets import Preset, presets
from attractr.gui.controllers.worker_client import WorkerClient as ThumbnailWorker
from attractr.gui.state.document import TAGS_ALL, Document

THUMB = 96


class PresetList(QListWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(THUMB, THUMB))
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setSpacing(6)
        self.setWordWrap(True)


class PresetsPanel(QWidget):
    def __init__(self, doc: Document, thumbs: ThumbnailWorker, parent=None) -> None:
        super().__init__(parent)
        self.doc = doc
        self.thumbs = thumbs
        self._items: dict[str, QListWidgetItem] = {}
        self._presets: dict[str, Preset] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)

        # daily card
        self.daily_label = QLabel("Attractor of the day: …")
        self.daily_label.setWordWrap(True)
        self.btn_daily = QPushButton("Open today's attractor")
        self.btn_daily.setEnabled(False)
        row = QHBoxLayout()
        row.addWidget(self.daily_label, 1)
        row.addWidget(self.btn_daily)
        lay.addLayout(row)

        self.tabs = QTabWidget()
        self.list_curated = PresetList()
        self.list_user = PresetList()
        self.tabs.addTab(self.list_curated, "Curated")
        self.tabs.addTab(self.list_user, "Mine")
        lay.addWidget(self.tabs, 1)

        btns = QHBoxLayout()
        self.btn_save = QPushButton("💾 Save current…")
        self.btn_delete = QPushButton("Delete")
        self.btn_copy = QPushButton("Copy code")
        self.btn_copy.setToolTip("Copy an ATR1: share code of the current settings to the clipboard")
        self.btn_paste = QPushButton("Paste code")
        self.btn_paste.setToolTip("Apply an ATR1: / CHS1: code from the clipboard")
        for b in (self.btn_save, self.btn_delete, self.btn_copy, self.btn_paste):
            btns.addWidget(b)
        lay.addLayout(btns)

        self.list_curated.itemActivated.connect(self._apply_item)
        self.list_curated.itemClicked.connect(self._apply_item)
        self.list_user.itemActivated.connect(self._apply_item)
        self.list_user.itemClicked.connect(self._apply_item)
        self.btn_save.clicked.connect(self._save)
        self.btn_delete.clicked.connect(self._delete)
        self.btn_copy.clicked.connect(self._copy_code)
        self.btn_paste.clicked.connect(self._paste_code)
        self.thumbs.ready.connect(self._on_thumb)
        self._daily_settings = None
        self.thumbs.dailyReady.connect(self._on_daily)
        self.btn_daily.clicked.connect(self._open_daily)
        self.populate()
        self.thumbs.daily()

    def populate(self) -> None:
        self.list_curated.clear()
        self.list_user.clear()
        self._items.clear()
        self._presets.clear()
        presets.load()
        placeholder = QPixmap(THUMB, THUMB)
        placeholder.fill(Qt.GlobalColor.transparent)
        for p in presets.curated():
            self._add(self.list_curated, p, placeholder)
        for p in presets.user():
            self._add(self.list_user, p, placeholder)

    def _add(self, lst: QListWidget, p: Preset, placeholder: QPixmap) -> None:
        item = QListWidgetItem(QIcon(placeholder), p.name)
        item.setData(Qt.ItemDataRole.UserRole, p.key)
        item.setToolTip(f"{p.name} — {p.attractor} ({p.source})")
        item.setSizeHint(QSize(THUMB + 16, THUMB + 34))
        lst.addItem(item)
        self._items[p.key] = item
        self._presets[p.key] = p
        try:
            self.thumbs.request("preset_" + _slug(p.key), p.apply())
        except Exception:  # noqa: BLE001 — a preset for a missing attractor
            pass

    def _on_thumb(self, key: str, img) -> None:
        if not key.startswith("preset_"):
            return
        for k, item in self._items.items():
            if "preset_" + _slug(k) == key:
                item.setIcon(QIcon(QPixmap.fromImage(img)))

    def _apply_item(self, item: QListWidgetItem) -> None:
        p = self._presets.get(item.data(Qt.ItemDataRole.UserRole))
        if p is None:
            return
        try:
            self.doc.apply(p.apply(self.doc.settings), f"Preset {p.name}", TAGS_ALL)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Preset", f"Could not apply preset: {exc}")

    def _save(self) -> None:
        name, ok = QInputDialog.getText(self, "Save preset", "Preset name:", text=self.doc.spec.name)
        if not ok or not name.strip():
            return
        p = Preset.from_settings(name.strip(), self.doc.settings)
        presets.save_user(p)
        self.populate()
        self.tabs.setCurrentIndex(1)

    def _delete(self) -> None:
        item = self.list_user.currentItem()
        if item is None:
            return
        p = self._presets.get(item.data(Qt.ItemDataRole.UserRole))
        if p and p.source == "user":
            presets.delete_user(p)
            self.populate()

    def _copy_code(self) -> None:
        QGuiApplication.clipboard().setText(settings_to_code(self.doc.settings))

    def _paste_code(self) -> None:
        text = QGuiApplication.clipboard().text()
        s = settings_from_code(text)
        if s is None:
            QMessageBox.information(self, "Paste code", "No ATR1: or CHS1: code found in the clipboard.")
            return
        self.doc.apply(s, "Paste code", TAGS_ALL)

    def _on_daily(self, preset, settings) -> None:
        if preset is None:
            self.daily_label.setText("Attractor of the day: unavailable")
            return
        self._daily_settings = settings
        self.daily_label.setText(f"✦ Attractor of the day: <b>{preset.name}</b> ({preset.attractor}, {preset.style})")
        self.btn_daily.setEnabled(True)

    def _open_daily(self) -> None:
        if self._daily_settings is not None:
            self.doc.apply(self._daily_settings, "Attractor of the day", TAGS_ALL)


def _slug(s: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
