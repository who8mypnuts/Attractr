"""Presets: curated (bundled JSON) and user-saved (``~/.attractr/presets``)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from attractr.core.attractors.registry import registry
from attractr.core.color.palettes import palettes
from attractr.core.io.paths import resources_dir, user_presets_dir
from attractr.core.render.camera import Camera
from attractr.core.render.pipeline import default_settings
from attractr.core.render.settings import RenderSettings


@dataclass
class Preset:
    name: str
    attractor: str
    params: dict[str, float] = field(default_factory=dict)
    camera: dict[str, float] = field(default_factory=dict)
    palette: str | None = None
    style: str | None = None
    color_source: str | None = None
    source: str = "user"
    settings: dict[str, Any] | None = None  # full settings for user presets
    path: Path | None = None

    @property
    def key(self) -> str:
        return f"{self.source}:{self.attractor}:{self.name}"

    def apply(self, base: RenderSettings | None = None) -> RenderSettings:
        """Settings for this preset (user presets carry full settings; curated ones are
        built on the attractor defaults)."""
        if self.settings:
            return RenderSettings.from_dict(self.settings)
        spec = registry.get(self.attractor)
        s = default_settings(spec, quality=base.quality if base else None)
        if self.params:
            s = s.with_params(**{k: v for k, v in self.params.items() if k in spec.param_names})
        cam = s.camera
        if self.camera:
            cam = Camera.from_euler(self.camera.get("yaw", 0.0), self.camera.get("pitch", 0.0), self.camera.get("roll", 0.0),
                                    zoom=self.camera.get("zoom", 1.0), fit=cam.fit)
        look = s.look
        if self.palette and self.palette in palettes:
            look = replace(look, gradient=palettes.get(self.palette))
        if self.style:
            look = replace(look, style=self.style)
        if self.color_source:
            look = replace(look, color_source=self.color_source)
        return replace(s, camera=cam, look=look)

    def to_dict(self) -> dict[str, Any]:
        d = {"name": self.name, "attractor": self.attractor, "params": self.params, "camera": self.camera,
             "palette": self.palette, "style": self.style, "color_source": self.color_source, "source": self.source}
        if self.settings:
            d["settings"] = self.settings
        return d

    @staticmethod
    def from_dict(d: dict[str, Any], path: Path | None = None) -> Preset:
        return Preset(d["name"], d["attractor"], dict(d.get("params", {})), dict(d.get("camera", {})), d.get("palette"),
                      d.get("style"), d.get("color_source"), d.get("source", "user"), d.get("settings"), path)

    @staticmethod
    def from_settings(name: str, settings: RenderSettings) -> Preset:
        yaw, pitch, roll = settings.camera.euler
        return Preset(name, settings.attractor, settings.param_dict,
                      {"yaw": yaw, "pitch": pitch, "roll": roll, "zoom": settings.camera.zoom},
                      settings.look.gradient.name, settings.look.style, settings.look.color_source, "user", settings.to_dict())


class PresetLibrary:
    def __init__(self) -> None:
        self._curated: list[Preset] = []
        self._user: list[Preset] = []
        self._loaded = False

    def load(self) -> None:
        self._curated.clear()
        self._user.clear()
        for path in sorted((resources_dir() / "presets").glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for d in data.get("presets", []):
                p = Preset.from_dict(d, path)
                if p.attractor in registry:
                    self._curated.append(p)
        for path in sorted(user_presets_dir().glob("*.json")):
            try:
                self._user.append(Preset.from_dict(json.loads(path.read_text(encoding="utf-8")), path))
            except (OSError, ValueError, KeyError):
                continue
        self._loaded = True

    def _ensure(self) -> None:
        if not self._loaded:
            self.load()

    def curated(self, attractor: str | None = None) -> list[Preset]:
        self._ensure()
        return [p for p in self._curated if attractor is None or p.attractor == attractor]

    def user(self) -> list[Preset]:
        self._ensure()
        return list(self._user)

    def all(self) -> list[Preset]:
        return self.curated() + self.user()

    def save_user(self, preset: Preset) -> Path:
        self._ensure()
        slug = re.sub(r"[^a-z0-9]+", "_", preset.name.lower()).strip("_") or "preset"
        path = user_presets_dir() / f"{slug}.json"
        preset.path = path
        preset.source = "user"
        path.write_text(json.dumps(preset.to_dict(), indent=1), encoding="utf-8")
        self._user = [p for p in self._user if p.path != path] + [preset]
        return path

    def delete_user(self, preset: Preset) -> None:
        if preset.path and preset.path.exists():
            preset.path.unlink()
        self._user = [p for p in self._user if p is not preset]


presets = PresetLibrary()
