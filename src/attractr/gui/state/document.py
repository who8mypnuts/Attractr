"""The Document: current RenderSettings + resolved AttractorSpec + undo stack.

Every change goes through :meth:`Document.apply` so it is undoable and broadcast with a
set of *tags* (``attractor``, ``params``, ``camera``, ``quality``, ``look``) that tell the
controllers what to recompute (look-only changes never re-iterate).
"""

from __future__ import annotations

import random
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from attractr.core.attractors.registry import registry
from attractr.core.attractors.spec import AttractorSpec
from attractr.core.color.palettes import palettes
from attractr.core.project.files import Project, load_project, save_project
from attractr.core.render.camera import Camera
from attractr.core.render.pipeline import default_settings, resolve_spec
from attractr.core.render.settings import Look, Quality, RenderSettings

TAGS_ALL = frozenset({"attractor", "params", "camera", "quality", "look"})


class SettingsCommand(QUndoCommand):
    def __init__(self, doc: Document, old: RenderSettings, new: RenderSettings, text: str,
                 tags: frozenset, merge_key: str | None, generation: int) -> None:
        super().__init__(text)
        self.doc, self.old, self.new, self.tags = doc, old, new, tags
        self.merge_key, self.generation = merge_key, generation

    def id(self) -> int:
        return 1 if self.merge_key else -1

    def mergeWith(self, other: QUndoCommand) -> bool:  # noqa: N802
        if not isinstance(other, SettingsCommand) or other.merge_key != self.merge_key or other.generation != self.generation:
            return False
        self.new = other.new
        self.tags = self.tags | other.tags
        return True

    def redo(self) -> None:
        self.doc._set(self.new, self.tags)

    def undo(self) -> None:
        self.doc._set(self.old, self.tags)


class Document(QObject):
    changed = Signal(object, object)  # RenderSettings, frozenset[str]
    attractorChanged = Signal(object)  # AttractorSpec
    pathChanged = Signal(object)  # Path | None
    dirtyChanged = Signal(bool)
    interactionChanged = Signal(bool)

    def __init__(self, settings: RenderSettings | None = None, parent=None) -> None:
        super().__init__(parent)
        self.undo_stack = QUndoStack(self)
        self.undo_stack.cleanChanged.connect(self._on_clean_changed)
        self._merge_gen = 0
        self._interacting = False
        self.path: Path | None = None
        self.animation: dict | None = None
        self.notes = ""
        self.param_history: dict[str, dict[str, list[float]]] = {}  # attractor id → param → last values (saved with the project)
        if settings is None:
            settings = default_settings(registry.get("lorenz"))
        self.settings: RenderSettings = settings
        self.spec: AttractorSpec = resolve_spec(settings)

    def _on_clean_changed(self, clean: bool) -> None:
        try:
            self.dirtyChanged.emit(not clean)
        except RuntimeError:  # being destroyed
            pass

    # ── core mutation ──────────────────────────────────────────────────────────
    def apply(self, new: RenderSettings, text: str, tags: frozenset | set, merge_key: str | None = None) -> None:
        if new == self.settings:
            return
        cmd = SettingsCommand(self, self.settings, new, text, frozenset(tags), merge_key, self._merge_gen)
        self.undo_stack.push(cmd)

    def _set(self, settings: RenderSettings, tags: frozenset) -> None:
        old = self.settings
        self.settings = settings
        if "attractor" in tags or settings.attractor != old.attractor or settings.source != old.source:
            self.spec = resolve_spec(settings)
            self.attractorChanged.emit(self.spec)
            tags = tags | {"attractor"}
        self.changed.emit(settings, tags)

    def end_merge(self) -> None:
        """Close the current undo merge group (call on slider release)."""
        self._merge_gen += 1

    def begin_interaction(self) -> None:
        if not self._interacting:
            self._interacting = True
            self.interactionChanged.emit(True)

    def end_interaction(self) -> None:
        self.end_merge()
        if self._interacting:
            self._interacting = False
            self.interactionChanged.emit(False)

    @property
    def interacting(self) -> bool:
        return self._interacting

    # ── convenience setters ────────────────────────────────────────────────────
    def set_param(self, name: str, value: float, interactive: bool = False) -> None:
        self.apply(self.settings.with_params(**{name: value}), f"Set {name}", {"params"}, merge_key=f"param:{name}" if interactive else None)

    def set_params(self, values: dict[str, float], text: str = "Set parameters") -> None:
        self.apply(self.settings.with_param_dict({**self.settings.param_dict, **values}), text, {"params"})

    def set_camera(self, cam: Camera, interactive: bool = False, text: str = "Camera") -> None:
        self.apply(replace(self.settings, camera=cam), text, {"camera"}, merge_key="camera" if interactive else None)

    def set_look(self, look: Look, text: str = "Look", merge_key: str | None = None) -> None:
        self.apply(replace(self.settings, look=look), text, {"look"}, merge_key=merge_key)

    def set_quality(self, q: Quality, text: str = "Quality") -> None:
        self.apply(replace(self.settings, quality=q), text, {"quality"})

    def set_attractor(self, spec: AttractorSpec, keep_look: bool = True) -> None:
        """Switch attractor: fresh defaults (params, camera) but keep the current look."""
        new = default_settings(spec, quality=self.settings.quality)
        if keep_look:
            new = replace(new, look=self.settings.look)
        self.apply(new, f"Attractor → {spec.name}", TAGS_ALL)

    def set_source(self, source: str) -> None:
        """Apply edited formula text (from the formula editor) keeping params where names match."""
        from attractr.core.attractors.spec import spec_from_source

        spec = spec_from_source(source, id=self.spec.id if not self.spec.builtin else None, builtin=False)
        old_params = self.settings.param_dict
        params = {p.name: old_params.get(p.name, p.default) for p in spec.params}
        new = replace(self.settings, attractor=spec.id, source=source, params=tuple(params.items()))
        self.apply(new, "Edit formula", TAGS_ALL)

    def reset_params(self) -> None:
        self.apply(self.settings.with_param_dict(self.spec.default_params()), "Reset parameters", {"params"})

    def reset_camera(self) -> None:
        yaw, pitch, roll, zoom = self.spec.camera
        self.set_camera(Camera.from_euler(yaw, pitch, roll, zoom=zoom, fit=self.settings.camera.fit), text="Reset camera")

    def randomize_params(self, locked: set[str] | None = None, rng: random.Random | None = None) -> None:
        rng = rng or random.Random()
        locked = locked or set()
        vals = dict(self.settings.param_dict)
        for p in self.spec.params:
            if p.name in locked:
                continue
            v = rng.uniform(p.lo, p.hi)
            vals[p.name] = round(v) if p.is_int else v
        self.apply(self.settings.with_param_dict(vals), "Randomize parameters", {"params"})

    def randomize_all(self, rng: random.Random | None = None) -> None:
        rng = rng or random.Random()
        spec = rng.choice(registry.all())
        new = default_settings(spec, quality=self.settings.quality)
        vals = {p.name: (round(rng.uniform(p.lo, p.hi)) if p.is_int else rng.uniform(p.lo, p.hi)) for p in spec.params}
        cam = new.camera
        if spec.is_3d:
            cam = cam.with_euler(rng.uniform(-180, 180), rng.uniform(-90, 90), 0.0)
        pid = rng.choice(palettes.ids())
        look = replace(self.settings.look, gradient=palettes.get(pid))
        self.apply(replace(new, params=tuple(vals.items()), camera=cam, look=look), "Surprise me", TAGS_ALL)

    # ── parameter value history (persisted in the project) ────────────────────
    def remember_param(self, name: str, value: float, limit: int = 20) -> None:
        hist = self.param_history.setdefault(self.spec.id, {}).setdefault(name, [])
        if hist and abs(hist[-1] - value) <= 1e-12:
            return
        hist.append(float(value))
        del hist[:-limit]

    def history_for(self, name: str) -> list[float]:
        return list(self.param_history.get(self.spec.id, {}).get(name, []))

    # ── files ──────────────────────────────────────────────────────────────────
    def load(self, path: str | Path) -> None:
        proj = load_project(path)
        self.animation = proj.animation
        self.notes = proj.notes
        self.param_history = proj.history
        self.undo_stack.clear()
        self._set(proj.settings, TAGS_ALL)
        self.path = Path(path)
        self.undo_stack.setClean()
        self.pathChanged.emit(self.path)

    def save(self, path: str | Path | None = None) -> Path:
        path = Path(path) if path else self.path
        if path is None:
            raise ValueError("no path")
        proj = Project(self.settings, self.animation, self.notes, path, self.param_history)
        out = save_project(proj, path)
        self.path = out
        self.undo_stack.setClean()
        self.pathChanged.emit(out)
        return out

    def new(self, spec_id: str = "lorenz") -> None:
        self.undo_stack.clear()
        self.path = None
        self.animation = None
        self.param_history = {}
        self._set(default_settings(registry.get(spec_id)), TAGS_ALL)
        self.undo_stack.setClean()
        self.pathChanged.emit(None)

    @property
    def dirty(self) -> bool:
        return not self.undo_stack.isClean()
