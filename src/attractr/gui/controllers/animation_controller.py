"""Owns the Timeline, the playhead and the link between document state and keyframes."""

from __future__ import annotations

import time
from dataclasses import replace

from PySide6.QtCore import QObject, QTimer, Signal

from attractr.core.animation.timeline import ANIMATABLE, Timeline, get_path
from attractr.core.render.settings import RenderSettings
from attractr.gui.state.document import TAGS_ALL, Document


class AnimationController(QObject):
    timelineChanged = Signal()
    timeChanged = Signal(float)
    playingChanged = Signal(bool)

    def __init__(self, doc: Document, parent=None) -> None:
        super().__init__(parent)
        self.doc = doc
        self.timeline = Timeline.from_dict(doc.animation)
        self.time = 0.0
        self.base: RenderSettings = doc.settings
        self._applying = False
        self.auto_key = False
        self._play_timer = QTimer(self)
        self._play_timer.setInterval(33)
        self._play_timer.timeout.connect(self._tick)
        self._play_start = 0.0
        self._play_t0 = 0.0
        doc.changed.connect(self._on_doc_changed)
        doc.pathChanged.connect(lambda _p: self.reload_from_document())

    # ── persistence ────────────────────────────────────────────────────────────
    def reload_from_document(self) -> None:
        self.timeline = Timeline.from_dict(self.doc.animation)
        self.base = self.doc.settings
        self.time = 0.0
        self.timelineChanged.emit()
        self.timeChanged.emit(0.0)

    def store(self) -> None:
        self.timeline.remove_empty()
        self.doc.animation = self.timeline.to_dict() if self.timeline.tracks else None
        self.timelineChanged.emit()

    # ── time ───────────────────────────────────────────────────────────────────
    def set_time(self, t: float, apply: bool = True) -> None:
        t = min(max(t, 0.0), self.timeline.duration)
        self.time = t
        if apply and self.timeline.tracks:
            self._apply_time()
        self.timeChanged.emit(t)

    def _apply_time(self) -> None:
        s = self.timeline.evaluate(self.base, self.time)
        if s != self.doc.settings:
            self._applying = True
            try:
                self.doc._set(s, TAGS_ALL - {"attractor"})
            finally:
                self._applying = False

    def _on_doc_changed(self, settings: RenderSettings, tags: frozenset) -> None:
        if self._applying:
            return
        if "attractor" in tags and settings.attractor != self.base.attractor:
            # a different attractor invalidates parameter tracks
            self.timeline.tracks = {p: tr for p, tr in self.timeline.tracks.items() if not p.startswith("params.")}
            self.base = settings
            self.store()
            return
        if self.auto_key and self.timeline.tracks:
            # record changed animated properties as keys at the playhead
            for path in self._changed_paths(self.timeline.evaluate(self.base, self.time), settings):
                self.timeline.set_key(path, self.time, get_path(settings, path))
            self.store()
        # non-animated properties (and the rest) become the new base
        self._update_base(settings)

    def _update_base(self, settings: RenderSettings) -> None:
        base = settings
        for path, tr in self.timeline.tracks.items():
            if tr.keys:
                try:
                    from attractr.core.animation.timeline import set_path

                    base = set_path(base, path, get_path(self.base, path))
                except Exception:  # noqa: BLE001
                    continue
        self.base = base

    @staticmethod
    def _changed_paths(a: RenderSettings, b: RenderSettings) -> list[str]:
        out = []
        for name in b.param_dict:
            if a.param_dict.get(name) != b.param_dict.get(name):
                out.append(f"params.{name}")
        for path in ANIMATABLE:
            try:
                if get_path(a, path) != get_path(b, path):
                    out.append(path)
            except AttributeError:
                continue
        return out

    # ── keys ───────────────────────────────────────────────────────────────────
    def key_paths(self, paths: list[str]) -> None:
        s = self.doc.settings
        for p in paths:
            self.timeline.set_key(p, self.time, get_path(s, p))
        self.store()

    def key_params(self) -> None:
        self.key_paths([f"params.{k}" for k in self.doc.settings.param_dict])

    def key_camera(self) -> None:
        self.key_paths(["camera.rotation", "camera.zoom", "camera.pan_u", "camera.pan_v", "camera.perspective"])

    def key_look(self) -> None:
        self.key_paths(["look.phase", "look.gamma", "look.percentile", "look.depth_cue", "look.gradient"])

    def key_all(self) -> None:
        self.key_params()
        self.key_camera()
        self.key_paths(["look.phase"])

    def remove_keys_at(self, t: float, paths: list[str] | None = None) -> None:
        for p, tr in list(self.timeline.tracks.items()):
            if paths is None or p in paths:
                tr.remove_key_at(t, tol=0.5 / self.timeline.fps)
        self.store()

    def remove_track(self, path: str) -> None:
        self.timeline.tracks.pop(path, None)
        self.store()

    def clear(self) -> None:
        self.timeline.tracks.clear()
        self.store()

    def set_timeline(self, tl: Timeline, base: RenderSettings | None = None) -> None:
        self.timeline = tl
        if base is not None:
            self.base = base
        self.store()
        self.set_time(0.0)

    def set_duration(self, d: float) -> None:
        self.timeline.duration = max(0.1, d)
        self.store()

    def set_fps(self, fps: int) -> None:
        self.timeline.fps = max(1, fps)
        self.store()

    def set_loop(self, mode: str) -> None:
        self.timeline.loop = mode
        self.store()

    # ── playback (preview) ─────────────────────────────────────────────────────
    @property
    def playing(self) -> bool:
        return self._play_timer.isActive()

    def play(self) -> None:
        if self.playing:
            return
        self._play_t0 = self.time if self.time < self.timeline.duration else 0.0
        self._play_start = time.perf_counter()
        self.doc.begin_interaction()
        self._play_timer.start()
        self.playingChanged.emit(True)

    def pause(self) -> None:
        if not self.playing:
            return
        self._play_timer.stop()
        self.doc.end_interaction()
        self.playingChanged.emit(False)

    def stop(self) -> None:
        self.pause()
        self.set_time(0.0)

    def _tick(self) -> None:
        elapsed = time.perf_counter() - self._play_start
        t = self._play_t0 + elapsed
        if self.timeline.loop == "none" and t >= self.timeline.duration:
            self.set_time(self.timeline.duration)
            self.pause()
            return
        from attractr.core.animation.easing import loop_time

        self.set_time(loop_time(t, self.timeline.duration, self.timeline.loop) if self.timeline.loop != "none" else t)

    def settings_at(self, t: float) -> RenderSettings:
        return self.timeline.evaluate(self.base, t)

    def base_for_render(self) -> RenderSettings:
        return replace(self.base)
