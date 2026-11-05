"""``.attractr`` project files (JSON)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from attractr.core.render.settings import RenderSettings
from attractr.version import __version__

SCHEMA = 1
SUFFIX = ".attractr"


@dataclass
class Project:
    settings: RenderSettings = field(default_factory=RenderSettings)
    animation: dict[str, Any] | None = None  # timeline (see core/animation/timeline.py)
    notes: str = ""
    path: Path | None = None
    history: dict[str, dict[str, list[float]]] = field(default_factory=dict)  # attractor id → param → recent values

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "app": "Attractr",
            "version": __version__,
            "settings": self.settings.to_dict(),
            "animation": self.animation,
            "notes": self.notes,
            "history": self.history,
        }

    @staticmethod
    def from_dict(d: dict[str, Any], path: Path | None = None) -> Project:
        if d.get("schema", 1) > SCHEMA:
            raise ValueError(f"project schema {d['schema']} is newer than this Attractr ({SCHEMA})")
        return Project(RenderSettings.from_dict(d["settings"]), d.get("animation"), d.get("notes", ""), path,
                       {k: {n: [float(x) for x in v] for n, v in pv.items()} for k, pv in d.get("history", {}).items()})


def save_project(project: Project, path: str | Path) -> Path:
    path = Path(path)
    if path.suffix != SUFFIX:
        path = path.with_suffix(SUFFIX)
    path.write_text(json.dumps(project.to_dict(), indent=1), encoding="utf-8")
    project.path = path
    return path


def load_project(path: str | Path) -> Project:
    path = Path(path)
    return Project.from_dict(json.loads(path.read_text(encoding="utf-8")), path)
