"""Persistent preview thread: renders the latest requested settings progressively.

A single long-lived QThread keeps the GPU context alive between previews.  Requests
supersede each other (latest wins); the running accumulation is cancelled cooperatively.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, replace

from PySide6.QtCore import QThread, Signal

from attractr.core.jobs.cancel import Cancelled, CancelToken
from attractr.core.jobs.progress import ProgressTracker
from attractr.core.render.engines import selector
from attractr.core.render.pipeline import resolve_spec
from attractr.core.render.result import RenderResult
from attractr.core.render.settings import RenderSettings

log = logging.getLogger(__name__)


@dataclass
class PreviewRequest:
    settings: RenderSettings
    generation: int
    interactive: bool


class PreviewWorker(QThread):
    partialReady = Signal(object, int)  # RenderResult, generation
    finishedRender = Signal(object, int)  # RenderResult, generation
    failed = Signal(str, int)
    engineChanged = Signal(str)  # engine id actually used

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cv = threading.Condition()
        self._pending: PreviewRequest | None = None
        self._cancel = CancelToken()
        self._stop = False
        self._engine_pref = "auto"
        self._fallback_cpu = False

    # ── API (GUI thread) ───────────────────────────────────────────────────────
    def request(self, req: PreviewRequest) -> None:
        with self._cv:
            self._pending = req
            self._cancel.cancel()  # interrupt the running one
            self._cv.notify()

    def set_engine(self, engine_id: str) -> None:
        self._engine_pref = engine_id
        self._fallback_cpu = False

    def stop(self) -> None:
        with self._cv:
            self._stop = True
            self._cancel.cancel()
            self._cv.notify()
        self.wait(5000)

    # ── thread body ────────────────────────────────────────────────────────────
    def run(self) -> None:
        while True:
            with self._cv:
                while self._pending is None and not self._stop:
                    self._cv.wait()
                if self._stop:
                    return
                req = self._pending
                self._pending = None
                self._cancel = CancelToken()
                cancel = self._cancel
            try:
                self._render(req, cancel)
            except Cancelled:
                continue
            except Exception as exc:  # noqa: BLE001
                log.exception("preview failed")
                self.failed.emit(f"{type(exc).__name__}: {exc}", req.generation)

    def _render(self, req: PreviewRequest, cancel: CancelToken) -> None:
        settings = req.settings
        spec = resolve_spec(settings)
        engine = selector.select("cpu" if self._fallback_cpu else self._engine_pref, "preview")
        self.engineChanged.emit(engine.id)
        last_emit = [0.0]

        def sink(result: RenderResult, fraction: float) -> None:
            now = time.perf_counter()
            if now - last_emit[0] >= 0.08 or fraction >= 1.0:
                last_emit[0] = now
                self.partialReady.emit(result, req.generation)

        try:
            result = engine.accumulate(settings, spec, sink=sink, cancel=cancel, tracker=ProgressTracker(None))
        except Cancelled:
            raise
        except Exception as exc:  # noqa: BLE001
            if engine.id != "cpu":
                log.warning("preview engine %s failed (%s) — using CPU", engine.id, exc)
                self._fallback_cpu = True
                self.engineChanged.emit("cpu")
                cpu = selector.get_engine("cpu")
                result = cpu.accumulate(settings, spec, sink=sink, cancel=cancel, tracker=ProgressTracker(None))
            else:
                raise
        self.finishedRender.emit(result, req.generation)


def preview_quality(settings: RenderSettings, view_w: int, view_h: int, interactive: bool,
                    max_side: int, ppp: float, interactive_ppp: float) -> RenderSettings:
    """Derive preview settings: viewport aspect, capped size, low iteration budget."""
    view_w, view_h = max(view_w, 16), max(view_h, 16)
    side = max_side if not interactive else max(128, max_side // 2)
    scale = min(side / view_w, side / view_h, 1.0)
    w, h = max(16, int(view_w * scale)), max(16, int(view_h * scale))
    q = settings.quality
    q = replace(q, width=w, height=h, points_per_pixel=interactive_ppp if interactive else ppp,
                supersample=1, splat_radius=0 if interactive else min(q.splat_radius, 1))
    return replace(settings, quality=q)
