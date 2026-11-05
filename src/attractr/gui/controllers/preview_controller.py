"""Glue between Document changes, the preview worker and the develop controller."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from attractr.core.render.accumulators import needs_for
from attractr.core.render.result import RenderResult
from attractr.core.render.settings import RenderSettings
from attractr.gui.controllers.develop_controller import DevelopController
from attractr.gui.controllers.preview_worker import PreviewRequest, PreviewWorker, preview_quality
from attractr.gui.state.document import Document


class PreviewController(QObject):
    imageReady = Signal(object, object, object)  # QImage, Developed, RenderResult
    statusChanged = Signal(str)  # text for the status bar
    engineChanged = Signal(str)
    resultChanged = Signal(object)  # latest RenderResult (partial or final)

    def __init__(self, document: Document, parent=None) -> None:
        super().__init__(parent)
        self.doc = document
        self.worker = PreviewWorker(self)
        self.develop = DevelopController(self)
        self.view_size = (512, 512)
        self.max_side = 1024
        self.ppp = 2.0
        self.interactive_ppp = 0.4
        self.enabled = True
        self._generation = 0
        self._last_result: RenderResult | None = None
        self._pending_settings: RenderSettings | None = None
        self._refine_timer = QTimer(self)
        self._refine_timer.setSingleShot(True)
        self._refine_timer.timeout.connect(self._refine)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(15)
        self._debounce.timeout.connect(self._flush)

        self.worker.partialReady.connect(self._on_result)
        self.worker.finishedRender.connect(self._on_final)
        self.worker.failed.connect(lambda msg, gen: self.statusChanged.emit(f"preview failed: {msg}"))
        self.worker.engineChanged.connect(self.engineChanged)
        self.develop.imageReady.connect(self._on_image)
        self.develop.failed.connect(lambda m: self.statusChanged.emit(f"develop failed: {m}"))
        document.changed.connect(self.on_document_changed)
        document.interactionChanged.connect(self._on_interaction)
        self.worker.start()

    # ── inputs ─────────────────────────────────────────────────────────────────
    def set_view_size(self, w: int, h: int) -> None:
        if (w, h) != self.view_size:
            self.view_size = (w, h)
            self.restart()

    def set_engine(self, engine_id: str) -> None:
        self.worker.set_engine(engine_id)
        self.restart()

    def on_document_changed(self, settings: RenderSettings, tags: frozenset) -> None:
        if not self.enabled:
            return
        last = self._last_result
        # a look change only re-develops — unless it needs buffers the last accumulation
        # did not produce (colour source, depth/zmin for Liquid/Solid)
        if tags <= {"look"} and last is not None and needs_for(settings.look) == needs_for(last.settings.look):
            self.develop.request(last, settings.look)
            return
        self._pending_settings = settings
        self._debounce.start()

    def restart(self) -> None:
        self._pending_settings = self.doc.settings
        self._debounce.start()

    # ── internals ──────────────────────────────────────────────────────────────
    def _flush(self) -> None:
        settings = self._pending_settings
        if settings is None:
            return
        self._pending_settings = None
        self._generation += 1
        interactive = self.doc.interacting
        ps = preview_quality(settings, *self.view_size, interactive, self.max_side, self.ppp, self.interactive_ppp)
        self.worker.request(PreviewRequest(ps, self._generation, interactive))
        if interactive:
            self._refine_timer.start(250)

    def _refine(self) -> None:
        if not self.doc.interacting:
            self.restart()

    def _on_interaction(self, active: bool) -> None:
        if not active:
            self._refine_timer.start(120)

    def _on_result(self, result: RenderResult, gen: int) -> None:
        if gen != self._generation:
            return
        self._last_result = result
        self.resultChanged.emit(result)
        self.develop.request(result, self.doc.settings.look)

    def _on_final(self, result: RenderResult, gen: int) -> None:
        self._on_result(result, gen)
        st = result.stats
        self.statusChanged.emit(
            f"preview {result.width}×{result.height} · {st.iterations_done / 1e6:.1f} M pts in {st.accumulate_seconds:.2f} s"
            f" · {st.points_per_second / 1e6:.0f} Mpts/s · coverage {st.coverage * 100:.1f} % · {st.engine}"
        )

    def _on_image(self, img, dev, result) -> None:
        self.imageReady.emit(img, dev, result)

    @property
    def last_result(self) -> RenderResult | None:
        return self._last_result

    def shutdown(self) -> None:
        self.worker.stop()
