"""Render presets: named output recipes (size, quality, engine, file format, report) that
are independent of *what* is rendered — "Instagram 1080²", "A3 print 300 dpi 16-bit + PDF
report", … Used by the Render dialog, *Batch render folder…* and ``attractr batch``.

Built-ins live in ``resources/presets/render_presets.json``; user presets are stored in
``~/.attractr/render_presets.json`` (one file, because they are tiny)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from attractr.core.io.paths import resources_dir, user_dir
from attractr.core.render.settings import RenderSettings


@dataclass(frozen=True)
class RenderPreset:
    name: str
    width: int = 2048
    height: int = 2048
    points_per_pixel: float = 12.0
    supersample: int = 2
    splat_radius: int = 0
    engine: str = "auto"
    precision: str = "auto"
    fmt: str = "png"
    bit_depth: int = 8
    report_formats: tuple[str, ...] = ("md",)
    dynamics: bool = False
    builtin: bool = False

    def apply(self, settings: RenderSettings) -> RenderSettings:
        """The settings with this preset's quality (everything else untouched)."""
        q = replace(settings.quality, width=self.width, height=self.height, points_per_pixel=self.points_per_pixel,
                    supersample=self.supersample, splat_radius=self.splat_radius, engine=self.engine, precision=self.precision)
        return replace(settings, quality=q)

    @property
    def summary(self) -> str:
        rep = ",".join(self.report_formats) if self.report_formats else "no report"
        return f"{self.width}×{self.height} · {self.points_per_pixel:g} ppp · ss{self.supersample} · {self.fmt} {self.bit_depth}-bit · {rep}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("builtin", None)
        d["report_formats"] = list(self.report_formats)
        return d

    @staticmethod
    def from_dict(d: dict[str, Any], builtin: bool = False) -> RenderPreset:
        return RenderPreset(
            str(d["name"]), int(d.get("width", 2048)), int(d.get("height", 2048)), float(d.get("points_per_pixel", 12.0)),
            int(d.get("supersample", 2)), int(d.get("splat_radius", 0)), str(d.get("engine", "auto")), str(d.get("precision", "auto")),
            str(d.get("fmt", "png")), int(d.get("bit_depth", 8)), tuple(d.get("report_formats", ["md"])), bool(d.get("dynamics", False)),
            builtin,
        )


class RenderPresetLibrary:
    def __init__(self) -> None:
        self._items: dict[str, RenderPreset] | None = None

    # ── loading ────────────────────────────────────────────────────────────────
    def _ensure(self) -> dict[str, RenderPreset]:
        if self._items is None:
            self.reload()
        return self._items  # type: ignore[return-value]

    def reload(self) -> None:
        items: dict[str, RenderPreset] = {}
        for path, builtin in ((resources_dir() / "render_presets" / "builtin.json", True), (self.user_file, False)):
            if not path.exists():
                continue
            try:
                for d in json.loads(path.read_text(encoding="utf-8")).get("presets", []):
                    p = RenderPreset.from_dict(d, builtin)
                    items[p.name] = p
            except (OSError, ValueError, KeyError):
                continue
        self._items = items

    @property
    def user_file(self) -> Path:
        return user_dir() / "render_presets.json"

    # ── queries ────────────────────────────────────────────────────────────────
    def names(self) -> list[str]:
        return list(self._ensure().keys())

    def get(self, name: str) -> RenderPreset:
        items = self._ensure()
        if name not in items:
            raise KeyError(f"unknown render preset {name!r}; available: {', '.join(items)}")
        return items[name]

    def __contains__(self, name: str) -> bool:
        return name in self._ensure()

    def all(self) -> list[RenderPreset]:
        return list(self._ensure().values())

    # ── user presets ───────────────────────────────────────────────────────────
    def save(self, preset: RenderPreset) -> None:
        items = self._ensure()
        items[preset.name] = replace(preset, builtin=False)
        self._write_user()

    def delete(self, name: str) -> bool:
        items = self._ensure()
        p = items.get(name)
        if p is None or p.builtin:
            return False
        del items[name]
        self._write_user()
        return True

    def _write_user(self) -> None:
        user = [p.to_dict() for p in self._ensure().values() if not p.builtin]
        self.user_file.parent.mkdir(parents=True, exist_ok=True)
        self.user_file.write_text(json.dumps({"schema": 1, "presets": user}, indent=1), encoding="utf-8")


render_presets = RenderPresetLibrary()
