"""Gallery index of exported renders (``~/.attractr/gallery/index.json``)."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from attractr.core.io.paths import subdir


@dataclass
class GalleryEntry:
    path: str
    timestamp: float
    attractor: str
    width: int
    height: int
    report: str | None = None
    kind: str = "image"  # image | video


class Gallery:
    def __init__(self) -> None:
        self._entries: list[GalleryEntry] | None = None

    @property
    def index_path(self) -> Path:
        return subdir("gallery") / "index.json"

    def load(self) -> list[GalleryEntry]:
        if self._entries is None:
            try:
                data = json.loads(self.index_path.read_text(encoding="utf-8"))
                self._entries = [GalleryEntry(**e) for e in data]
            except (OSError, ValueError, TypeError):
                self._entries = []
        return self._entries

    def save(self) -> None:
        self.index_path.write_text(json.dumps([asdict(e) for e in self.load()], indent=1), encoding="utf-8")

    def add(self, path: Path, attractor: str, width: int, height: int, report: Path | None = None, kind: str = "image") -> GalleryEntry:
        e = GalleryEntry(str(path), time.time(), attractor, width, height, str(report) if report else None, kind)
        self.load().insert(0, e)
        del self.load()[400:]
        self.save()
        return e

    def remove(self, entry: GalleryEntry, delete_file: bool = False) -> None:
        self.load().remove(entry)
        if delete_file:
            Path(entry.path).unlink(missing_ok=True)
        self.save()

    def entries(self) -> list[GalleryEntry]:
        return [e for e in self.load() if Path(e.path).exists()]


gallery = Gallery()
