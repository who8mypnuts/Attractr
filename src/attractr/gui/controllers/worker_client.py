"""QProcess client for :mod:`attractr.core.worker_server` (thumbnails, probes, daily)."""

from __future__ import annotations

import json
import logging
import sys
from collections import deque
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal
from PySide6.QtGui import QImage

from attractr.core.io.paths import cache_dir
from attractr.core.render.settings import RenderSettings

log = logging.getLogger(__name__)


def thumb_path(key: str, size: int) -> Path:
    return cache_dir("thumbs") / f"{key}_{size}.png"


class WorkerClient(QObject):
    ready = Signal(str, object)  # thumbnail key, QImage   (kept for ThumbnailWorker compatibility)
    probeReady = Signal(str, dict)  # token, result
    dailyReady = Signal(object, object)  # Preset, RenderSettings  (None, None on failure)
    failed = Signal(str, str)  # token, message

    def __init__(self, size: int = 96, parent=None) -> None:
        super().__init__(parent)
        self.size = size
        self._queue: deque[str] = deque()  # raw request lines (THUMB requests hold settings json)
        self._pending_keys: set[str] = set()
        self._inflight: str | None = None
        self._proc: QProcess | None = None
        self._buf = ""
        self._stopped = False

    # ── API ─────────────────────────────────────────────────────────────────────
    def start(self) -> None:
        self._ensure_process()

    def request(self, key: str, settings: RenderSettings, front: bool = False) -> bool:
        """Thumbnail request; True when served from the cache immediately."""
        p = thumb_path(key, self.size)
        if p.exists():
            img = QImage(str(p))
            if not img.isNull():
                self.ready.emit(key, img)
                return True
        if key in self._pending_keys or self._inflight == key:
            return False
        self._pending_keys.add(key)
        line = f"THUMB\t{key}\t{self.size}\t{json.dumps(settings.to_dict(), separators=(',', ':'))}"
        (self._queue.appendleft if front else self._queue.append)(line)
        self._pump()
        return False

    def probe(self, token: str, settings: RenderSettings) -> None:
        self._queue.appendleft(f"PROBE\t{token}\t{json.dumps(settings.to_dict(), separators=(',', ':'))}")
        self._pump()

    def daily(self, token: str = "daily") -> None:
        self._queue.append(f"DAILY\t{token}")
        self._pump()

    def stop(self) -> None:
        self._stopped = True
        self._queue.clear()
        if self._proc is not None and self._proc.state() != QProcess.ProcessState.NotRunning:
            self._proc.write(b"QUIT\n")
            self._proc.closeWriteChannel()
            if not self._proc.waitForFinished(2000):
                self._proc.kill()
                self._proc.waitForFinished(1000)
        self._proc = None

    # ── process management ─────────────────────────────────────────────────────
    def _ensure_process(self) -> None:
        if self._stopped or (self._proc is not None and self._proc.state() != QProcess.ProcessState.NotRunning):
            return
        proc = QProcess(self)
        proc.setProgram(sys.executable)
        proc.setArguments(["-m", "attractr.core.worker_server"])
        from PySide6.QtCore import QProcessEnvironment

        env = QProcessEnvironment.systemEnvironment()
        env.insert("NUMBA_NUM_THREADS", "2")  # leave cores for the interactive preview
        env.insert("ATTRACTR_CPU_BUDGET_MB", "256")
        proc.setProcessEnvironment(env)
        proc.readyReadStandardOutput.connect(self._on_stdout)
        proc.readyReadStandardError.connect(lambda: log.debug("worker: %s", bytes(proc.readAllStandardError()).decode(errors="replace").strip()))
        proc.finished.connect(self._on_finished)
        proc.start()
        self._proc = proc
        self._inflight = None
        self._ready = False

    def _on_finished(self, *_: object) -> None:
        self._inflight = None
        self._ready = False
        if not self._stopped and self._queue:
            self._proc = None
            self._ensure_process()

    def _pump(self) -> None:
        self._ensure_process()
        if self._proc is None or self._inflight is not None or not self._queue or not getattr(self, "_ready", False):
            return
        line = self._queue.popleft()
        self._inflight = line.split("\t")[1]
        self._proc.write((line + "\n").encode())

    def _on_stdout(self) -> None:
        if self._proc is None:
            return
        self._buf += bytes(self._proc.readAllStandardOutput()).decode(errors="replace")
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            if line == "READY":
                self._ready = True
                self._pump()
                continue
            parts = line.split("\t", 2)
            kind = parts[0]
            token = parts[1] if len(parts) > 1 else ""
            payload = parts[2] if len(parts) > 2 else ""
            try:
                if kind == "THUMB":
                    self._pending_keys.discard(token)
                    img = QImage(payload)
                    if not img.isNull():
                        self.ready.emit(token, img)
                elif kind == "PROBE":
                    self.probeReady.emit(token, json.loads(payload))
                elif kind == "DAILY":
                    d = json.loads(payload)
                    from attractr.core.project.presets import Preset

                    self.dailyReady.emit(Preset.from_dict(d["preset"]), RenderSettings.from_dict(d["settings"]))
                elif kind == "ERR":
                    self._pending_keys.discard(token)
                    log.warning("worker request %s failed: %s", token, payload)
                    if token == "daily":
                        self.dailyReady.emit(None, None)
                    self.failed.emit(token, payload)
            except Exception:  # noqa: BLE001
                log.exception("bad worker reply: %r", line)
            self._inflight = None
            self._pump()


ThumbnailWorker = WorkerClient  # backwards-compatible name
