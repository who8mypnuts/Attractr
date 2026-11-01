"""Develops RenderResults into QImages off the GUI thread, coalescing requests."""

from __future__ import annotations

import logging
import time

import numpy as np
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage

from attractr.core.render.develop.developer import Developed, develop
from attractr.core.render.result import RenderResult
from attractr.core.render.settings import Look

log = logging.getLogger(__name__)


def to_qimage(dev: Developed) -> QImage:
    rgba = dev.to_uint8(dither=False)
    h, w = rgba.shape[:2]
    buf = np.ascontiguousarray(rgba)
    img = QImage(buf.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
    return img.copy()  # detach from the numpy buffer


class _DevelopTask(QRunnable):
    def __init__(self, ctrl: DevelopController, result: RenderResult, look: Look, token: int) -> None:
        super().__init__()
        self.ctrl, self.result, self.look, self.token = ctrl, result, look, token

    def run(self) -> None:
        try:
            t0 = time.perf_counter()
            dev = develop(self.result, self.look)
            img = to_qimage(dev)
            self.ctrl._done.emit(img, dev, self.result, self.token, time.perf_counter() - t0)
        except RuntimeError:  # controller deleted during shutdown
            return
        except Exception as exc:  # noqa: BLE001
            log.exception("develop failed")
            try:
                self.ctrl.failed.emit(str(exc))
            except RuntimeError:
                return


class DevelopController(QObject):
    imageReady = Signal(object, object, object)  # QImage, Developed, RenderResult
    failed = Signal(str)
    _done = Signal(object, object, object, int, float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.pool = QThreadPool.globalInstance()
        self._running = False
        self._latest: tuple[RenderResult, Look] | None = None
        self._token = 0
        self.last_develop_seconds = 0.0
        self._done.connect(self._on_done)

    def request(self, result: RenderResult, look: Look) -> None:
        self._latest = (result, look)
        if not self._running:
            self._start()

    def _start(self) -> None:
        if self._latest is None:
            return
        result, look = self._latest
        self._latest = None
        self._running = True
        self._token += 1
        self.pool.start(_DevelopTask(self, result, look, self._token))

    def _on_done(self, img, dev, result, token, seconds) -> None:
        self._running = False
        self.last_develop_seconds = seconds
        if token == self._token:
            self.imageReady.emit(img, dev, result)
        if self._latest is not None:
            self._start()
