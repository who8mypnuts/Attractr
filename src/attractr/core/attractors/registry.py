"""Discovery of built-in (``resources/attractors``) and user (``~/.attractr/attractors``)
attractor definitions."""

from __future__ import annotations

import logging
from pathlib import Path

from attractr.core.attractors.spec import AttractorSpec, spec_from_file, spec_from_source
from attractr.core.formula.lexer import FormulaError
from attractr.core.io.paths import resources_dir, user_attractors_dir

log = logging.getLogger(__name__)


class AttractorRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, AttractorSpec] = {}
        self._errors: dict[str, str] = {}
        self._loaded = False

    # ── loading ─────────────────────────────────────────────────────────────────
    def load(self, builtin_dir: Path | None = None, user_dir: Path | None = None) -> None:
        self._specs.clear()
        self._errors.clear()
        for path in sorted((builtin_dir or resources_dir() / "attractors").rglob("*.atr")):
            self._load_file(path, builtin=True)
        udir = user_dir or user_attractors_dir()
        if udir.exists():
            for path in sorted(udir.rglob("*.atr")):
                self._load_file(path, builtin=False)
        self._apply_locale_overlay()
        self._loaded = True

    def _apply_locale_overlay(self) -> None:
        """Translate descriptions / parameter hints when an overlay for the locale exists."""
        from attractr.core.attractors.overlays import apply_overlay, load_overlay

        overlay = load_overlay()
        for sid, entry in overlay.items():
            if sid in self._specs and isinstance(entry, dict):
                self._specs[sid] = apply_overlay(self._specs[sid], entry)

    def _load_file(self, path: Path, builtin: bool) -> None:
        try:
            spec = spec_from_file(path, builtin=builtin)
        except (FormulaError, OSError, ValueError) as exc:
            self._errors[str(path)] = str(exc)
            log.warning("skipping %s: %s", path, exc)
            return
        if spec.id in self._specs and not builtin:
            spec = spec_from_source(spec.source, id=f"user_{spec.id}", path=path, builtin=False)
        self._specs[spec.id] = spec

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    # ── queries ─────────────────────────────────────────────────────────────────
    def get(self, spec_id: str) -> AttractorSpec:
        self.ensure_loaded()
        try:
            return self._specs[spec_id]
        except KeyError:
            raise KeyError(f"unknown attractor {spec_id!r}; try `attractr list attractors`") from None

    def __contains__(self, spec_id: str) -> bool:
        self.ensure_loaded()
        return spec_id in self._specs

    def all(self) -> list[AttractorSpec]:
        self.ensure_loaded()
        return sorted(self._specs.values(), key=lambda s: (s.family, s.name.lower()))

    def ids(self) -> list[str]:
        return [s.id for s in self.all()]

    def families(self) -> dict[str, list[AttractorSpec]]:
        out: dict[str, list[AttractorSpec]] = {}
        for s in self.all():
            out.setdefault(s.family, []).append(s)
        return out

    @property
    def errors(self) -> dict[str, str]:
        return dict(self._errors)

    # ── user attractors ─────────────────────────────────────────────────────────
    def add_user(self, spec: AttractorSpec) -> AttractorSpec:
        self.ensure_loaded()
        self._specs[spec.id] = spec
        return spec

    def save_user(self, source: str, spec_id: str | None = None) -> AttractorSpec:
        spec = spec_from_source(source, id=spec_id, builtin=False)
        path = user_attractors_dir() / f"{spec.id}.atr"
        path.write_text(source, encoding="utf-8")
        spec = spec_from_source(source, id=spec.id, path=path, builtin=False)
        return self.add_user(spec)


registry = AttractorRegistry()
