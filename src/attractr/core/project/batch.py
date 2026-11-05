"""Batch rendering: every renderable file in a folder × one render preset.

Renderable files: ``.attractr`` projects, ``.atr`` formula files (rendered at their
defaults) and ``.png`` images with embedded Attractr settings (re-rendered, e.g. at a
larger size). Used by ``attractr batch`` and *Render → Batch render folder…*."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from attractr.core.attractors.spec import spec_from_source
from attractr.core.io.metadata import read_settings
from attractr.core.project.files import SUFFIX, load_project
from attractr.core.project.render_presets import RenderPreset
from attractr.core.render.pipeline import default_settings
from attractr.core.render.settings import RenderSettings

BATCH_SUFFIXES = (SUFFIX, ".atr", ".png")


@dataclass(frozen=True)
class BatchItem:
    """One renderable file and the settings derived from it."""
    path: Path
    settings: RenderSettings

    @property
    def stem(self) -> str:
        return self.path.stem


def load_target(path: Path) -> RenderSettings | None:
    """Settings for one file, or None when the file is not renderable."""
    suffix = path.suffix.lower()
    if suffix == SUFFIX:
        return load_project(path).settings
    if suffix == ".atr":
        return default_settings(spec_from_source(path.read_text(encoding="utf-8"), id=path.stem))
    if suffix == ".png":
        return read_settings(path)
    return None


def collect(folder: Path, recursive: bool = False) -> tuple[list[BatchItem], list[tuple[Path, str]]]:
    """Scan ``folder`` → (items, skipped) where skipped carries the reason per file."""
    items: list[BatchItem] = []
    skipped: list[tuple[Path, str]] = []
    files = sorted(folder.rglob("*") if recursive else folder.glob("*"))
    for p in files:
        if not p.is_file() or p.suffix.lower() not in BATCH_SUFFIXES:
            continue
        try:
            s = load_target(p)
        except Exception as exc:  # noqa: BLE001 — one bad file must not stop the batch
            skipped.append((p, f"{type(exc).__name__}: {exc}"))
            continue
        if s is None:
            skipped.append((p, "no Attractr settings embedded"))
            continue
        items.append(BatchItem(p, s))
    return items, skipped


def plan(folder: Path, preset: RenderPreset, recursive: bool = False) -> tuple[list[BatchItem], list[tuple[Path, str]]]:
    """Like :func:`collect` but with the preset's quality applied to every item."""
    items, skipped = collect(folder, recursive)
    return [BatchItem(i.path, preset.apply(i.settings)) for i in items], skipped
